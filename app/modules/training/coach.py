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
                    target_muscle_groups=wo_data.get('target_muscle_groups'),
                    estimated_duration_min=wo_data.get('estimated_duration_min'),
                    warmup_notes=wo_data.get('warmup_notes'),
                )
                db.session.add(workout)
                db.session.flush()

                for ex_data in wo_data.get('exercises', []):
                    exercise = _get_or_create_exercise(ex_data['exercise_name'])
                    we = WorkoutExercise(
                        workout_id=workout.id,
                        exercise_id=exercise.id,
                        order_index=ex_data['order_index'],
                        notes=ex_data.get('coaching_notes') or ex_data.get('notes'),
                        tempo=ex_data.get('tempo'),
                        is_mandatory=ex_data.get('is_mandatory', True),
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
- 4-5 exercises per workout (compound first, isolation last)
- Exactly 3 sets per exercise
Return ONLY the JSON object. No explanation.

EXERCISE SELECTION RULES — APPLY TO EVERY PROGRAM GENERATION:

1. CONTRAINDICATIONS CHECK:
- Shoulder impingement → NO overhead press, NO upright row, NO behind-the-neck press. YES landmine press, YES neutral grip
- Disc herniation → NO axial load during pain, NO weighted hyperextension, CAREFUL with flexion under load
- Knee pain during squat → check depth, stance width, toe direction, ankle mobility

2. ANTHROPOMETRY:
- Long femurs + short torso → front squat or goblet better than back squat
- Long arms → floor press may be safer than full ROM bench press
- Wide hips → wider stance for squats and deadlifts

3. MUSCLE IMBALANCES:
- Anterior pelvic tilt → less hip flexor work, more glute activation and hamstring, iliopsoas stretching
- Quad dominant → more hip hinge (RDL, hip thrust), less quad-dominant
- Rounded shoulders → more rowing and face pulls, less chest press, pec minor stretching

4. MOBILITY:
- Limited dorsiflexion → heel elevation for squat, or goblet squat instead of barbell
- Limited overhead mobility → landmine press instead of overhead press
- Limited hip rotation → wider stance, possibly sumo instead of conventional

5. REHAB PHASE (if injury present):
- Acute (pain >5/10) → pain-free ROM only, isometrics, no load
- Subacute (pain 3-5/10) → light load in pain-free ROM, eccentric focus
- Chronic/remission (pain <3/10) → gradual return to full load
- ALWAYS: if exercise causes pain >3/10 → stop, modify or replace

6. HYPERTROPHY OPTIMIZATION (Schoenfeld 2023):
For each muscle group include exercises covering:
- Stretched position: flyes, incline curls, Romanian deadlift
- Shortened position: cable crossover, leg curl, concentration curl
- Multiple angles/force vectors

7. CORRECTIVE EXERCISES — mandatory when imbalances present:
- Anterior pelvic tilt → dead bug, glute bridge, plank
- Rounded shoulders → band pull-apart, face pull, external rotation, prone Y-raise
- Forward head → chin tuck, deep neck flexor activation
Include 2-3 corrective exercises as the first items in the workout (order_index 0, 1, 2).

PROGRAM STRUCTURE REQUIREMENTS:
- Program name and type (hypertrophy / strength / deload / home)
- Split type in program name (Push/Pull/Legs, Upper/Lower, Full Body)
- Block duration 4-6 weeks (total_weeks field)
- Every workout: target_muscle_groups, estimated_duration_min, warmup_notes specific to that day
- Every exercise: tempo in "E-P-C-P" format (e.g. "3-1-2-0"), coaching_notes ("focus on stretch at bottom"), is_mandatory (true/false)
- Compound exercises first, isolation last
- Beginners: simpler movements, master basics. Intermediate/Advanced: periodization, advanced techniques."""

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
- Muscle imbalances: {user.muscle_imbalances}
- Likes: {user.training_likes}, Dislikes: {user.training_dislikes}

JSON structure:
{{"name":"...","periodization_type":"hypertrophy","total_weeks":6,"mesocycles":[{{"name":"Accumulation","order_index":0,"weeks_count":6,"weeks":[{{"week_number":1,"notes":null,"workouts":[{{"day_of_week":0,"name":"Push A","order_index":0,"target_muscle_groups":"Chest, Triceps, Shoulders","estimated_duration_min":60,"warmup_notes":"...","exercises":[{{"exercise_name":"...","order_index":0,"tempo":"3-1-2-0","is_mandatory":true,"coaching_notes":"...","sets":[{{"set_number":1,"target_reps":"8-10","target_weight_kg":60.0,"target_rpe":7.0,"rest_seconds":90}}]}}]}}]}}]}}]}}

Use day_of_week 0=Mon,1=Tue,2=Wed,3=Thu,4=Fri,5=Sat,6=Sun."""

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

    lang = getattr(user, 'app_language', None) or 'en'
    lang_instruction = " Write all text fields in Ukrainian." if lang == 'uk' else ""
    system_prompt = (
        "You are an expert strength and conditioning coach. "
        "Return a JSON array only — no prose, no markdown fences. "
        "For each exercise explain why it was chosen for this specific user, "
        "what outcome to expect, and any modification made due to injuries/limitations. "
        "If no modification was needed, set modifications_applied to null. "
        f"Return exactly one object per input exercise, in the same order.{lang_instruction}"
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

    raw = complete(system_prompt, user_prompt, max_tokens=8192, model='claude-sonnet-4-6')
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
