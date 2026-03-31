import json
import re
from app.core.ai import complete
from app.core.models import User
from app.extensions import db
from .models import (
    Exercise, Mesocycle, PlannedSet,
    Program, ProgramWeek, Workout, WorkoutExercise, WorkoutSession
)


def build_training_context(user_id: int, session_id: int = None) -> str:
    parts = []
    program = Program.query.filter_by(user_id=user_id, status='active').first()
    if program:
        parts.append(f"\n## Active Program: {program.name} ({program.periodization_type})")
        parts.append(f"Total weeks: {program.total_weeks}")

    if session_id:
        from .models import LoggedExercise
        session = WorkoutSession.query.get(session_id)
        if session and session.status == 'in_progress':
            parts.append("\n## Current Workout Session (in progress)")
            for le in session.logged_exercises:
                sets_text = ', '.join(
                    f"{s.actual_reps}x{s.actual_weight_kg}kg@RPE{s.actual_rpe}"
                    for s in le.logged_sets
                )
                parts.append(f"- {le.exercise.name}: {sets_text or 'no sets yet'}")

    return '\n'.join(parts) if parts else ''


def save_program_from_dict(user_id: int, program_dict: dict) -> Program:
    """Parse AI-generated program JSON and persist to DB."""
    # Deactivate any existing active program
    Program.query.filter_by(user_id=user_id, status='active').update({'status': 'paused'})

    program = Program(
        user_id=user_id,
        name=program_dict['name'],
        periodization_type=program_dict['periodization_type'],
        total_weeks=program_dict['total_weeks'],
    )
    db.session.add(program)
    db.session.flush()

    for meso_data in program_dict.get('mesocycles', []):
        meso = Mesocycle(
            program_id=program.id,
            name=meso_data['name'],
            order_index=meso_data['order_index'],
            weeks_count=meso_data['weeks_count'],
        )
        db.session.add(meso)
        db.session.flush()

        for week_data in meso_data.get('weeks', []):
            week = ProgramWeek(
                mesocycle_id=meso.id,
                week_number=week_data['week_number'],
                notes=week_data.get('notes'),
            )
            db.session.add(week)
            db.session.flush()

            for wo_data in week_data.get('workouts', []):
                workout = Workout(
                    program_week_id=week.id,
                    day_of_week=wo_data['day_of_week'],
                    name=wo_data['name'],
                    order_index=wo_data['order_index'],
                )
                db.session.add(workout)
                db.session.flush()

                for ex_data in wo_data.get('exercises', []):
                    exercise = _get_or_create_exercise(ex_data['exercise_name'])
                    we = WorkoutExercise(
                        workout_id=workout.id,
                        exercise_id=exercise.id,
                        order_index=ex_data['order_index'],
                        notes=ex_data.get('notes'),
                    )
                    db.session.add(we)
                    db.session.flush()

                    for set_data in ex_data.get('sets', []):
                        ps = PlannedSet(
                            workout_exercise_id=we.id,
                            set_number=set_data['set_number'],
                            target_reps=set_data.get('target_reps'),
                            target_weight_kg=set_data.get('target_weight_kg'),
                            target_rpe=set_data.get('target_rpe'),
                            rest_seconds=set_data.get('rest_seconds'),
                        )
                        db.session.add(ps)

    db.session.commit()
    return program


def _get_or_create_exercise(name: str) -> Exercise:
    exercise = Exercise.query.filter_by(name=name).first()
    if not exercise:
        exercise = Exercise(name=name)
        db.session.add(exercise)
        db.session.flush()
    return exercise


def generate_program(user: User) -> dict:
    days = user.training_days_per_week or 3
    system_prompt = f"""You are an expert strength and conditioning coach.
Generate a training program as compact JSON only — no prose, no markdown, just valid JSON.

STRICT OUTPUT CONSTRAINTS (mandatory, no exceptions):
- Exactly 1 mesocycle
- Exactly 1 week inside that mesocycle (week_number: 1) — this is the repeating template
- Exactly {days} workouts in that week (one per training day)
- Exactly 4 exercises per workout
- Exactly 3 sets per exercise
- All "notes" fields must be null

Return ONLY the JSON object. No explanation."""

    user_prompt = f"""Create a training program for:
- Name: {user.name}, Gender: {user.gender}, Age: {user.age}
- Weight: {user.weight_kg}kg, Height: {user.height_cm}cm, Body fat: {user.body_fat_pct}%
- Primary goal: {user.goal_primary}, Secondary: {user.goal_secondary}
- Level: {user.level}
- Training: {days} days/week, {user.session_duration_min} min/session
- Equipment: {user.equipment}
- Current injuries: {user.injuries_current}
- Postural issues: {user.postural_issues}
- Mobility issues: {user.mobility_issues}
- Likes: {user.training_likes}, Dislikes: {user.training_dislikes}

JSON structure:
{{"name":"...","periodization_type":"linear","total_weeks":8,"mesocycles":[{{"name":"Accumulation","order_index":0,"weeks_count":8,"weeks":[{{"week_number":1,"notes":null,"workouts":[{{"day_of_week":0,"name":"...","order_index":0,"exercises":[{{"exercise_name":"...","order_index":0,"notes":null,"sets":[{{"set_number":1,"target_reps":"8-10","target_weight_kg":60.0,"target_rpe":7.0,"rest_seconds":90}}]}}]}}]}}]}}]}}

Use day_of_week 0=Mon,1=Tue,2=Wed,3=Thu,4=Fri,5=Sat,6=Sun. Respect injuries/mobility."""

    result = complete(system_prompt, user_prompt, max_tokens=8192, model='claude-sonnet-4-6')
    # Strip markdown code fences that the model sometimes wraps around JSON
    result = re.sub(r'^```(?:json)?\s*', '', result.strip())
    result = re.sub(r'\s*```$', '', result).strip()
    try:
        return json.loads(result)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI returned invalid JSON for program generation: {e}") from e


def generate_exercise_insights(program, user) -> int:
    """Generate selection_reason, expected_outcome, modifications_applied for all
    WorkoutExercises in the program. Returns count of exercises updated."""
    from .models import WorkoutExercise, Workout, ProgramWeek, Mesocycle

    wes = (WorkoutExercise.query
           .join(Workout)
           .join(ProgramWeek)
           .join(Mesocycle)
           .filter(Mesocycle.program_id == program.id)
           .order_by(Mesocycle.order_index, ProgramWeek.week_number,
                     Workout.order_index, WorkoutExercise.order_index)
           .all())

    if not wes:
        return 0

    exercises_data = [{
        'workout_exercise_id': we.id,
        'exercise_name': we.exercise.name,
        'workout_name': we.workout.name,
        'day_of_week': we.workout.day_of_week,
    } for we in wes]

    system_prompt = (
        "You are an expert strength and conditioning coach. "
        "Return a JSON array only — no prose, no markdown fences. "
        "For each exercise explain why it was chosen for this specific user, "
        "what outcome to expect, and any modification made due to injuries/limitations. "
        "If no modification was needed, set modifications_applied to null. "
        "Return exactly one object per input exercise, in the same order."
    )

    user_prompt = (
        f"User profile:\n"
        f"- Goal: {user.goal_primary}, Level: {user.level}\n"
        f"- Equipment: {user.equipment}\n"
        f"- Injuries: {user.injuries_current}\n"
        f"- Postural issues: {user.postural_issues}\n"
        f"- Mobility issues: {user.mobility_issues}\n"
        f"- Muscle imbalances: {user.muscle_imbalances}\n\n"
        f"Exercises:\n{json.dumps(exercises_data, ensure_ascii=False)}\n\n"
        "Return JSON array with fields: workout_exercise_id, selection_reason, "
        "expected_outcome, modifications_applied"
    )

    raw = complete(system_prompt, user_prompt, max_tokens=4096, model='claude-sonnet-4-6')
    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw).strip()

    insights = json.loads(raw)

    we_map = {we.id: we for we in wes}
    for item in insights:
        we = we_map.get(item.get('workout_exercise_id'))
        if we:
            we.selection_reason = item.get('selection_reason')
            we.expected_outcome = item.get('expected_outcome')
            we.modifications_applied = item.get('modifications_applied')

    db.session.commit()
    return len(insights)
