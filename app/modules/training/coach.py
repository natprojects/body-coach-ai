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
    system_prompt = """You are an expert strength and conditioning coach.
Generate a periodized training program as JSON only — no prose, no markdown, just valid JSON.
CRITICAL LIMITS to stay within token budget:
- Maximum 2 mesocycles
- Each mesocycle: maximum 2 weeks (representative weeks only)
- Each workout: maximum 5 exercises
- Each exercise: exactly 3 sets
- All notes fields must be null (no text)

Structure (follow exactly):
{
  "name": "...",
  "periodization_type": "linear",
  "total_weeks": 8,
  "mesocycles": [
    {
      "name": "Accumulation",
      "order_index": 0,
      "weeks_count": 4,
      "weeks": [
        {
          "week_number": 1,
          "notes": null,
          "workouts": [
            {
              "day_of_week": 0,
              "name": "Upper A",
              "order_index": 0,
              "exercises": [
                {
                  "exercise_name": "Bench Press",
                  "order_index": 0,
                  "notes": null,
                  "sets": [
                    {"set_number": 1, "target_reps": "8-10", "target_weight_kg": 60.0, "target_rpe": 7.0, "rest_seconds": 120},
                    {"set_number": 2, "target_reps": "8-10", "target_weight_kg": 60.0, "target_rpe": 7.5, "rest_seconds": 120},
                    {"set_number": 3, "target_reps": "8-10", "target_weight_kg": 60.0, "target_rpe": 8.0, "rest_seconds": 120}
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}"""

    user_prompt = f"""Create a training program for:
- Name: {user.name}, Gender: {user.gender}, Age: {user.age}
- Weight: {user.weight_kg}kg, Height: {user.height_cm}cm, Body fat: {user.body_fat_pct}%
- Primary goal: {user.goal_primary}, Secondary: {user.goal_secondary}
- Level: {user.level}
- Training: {user.training_days_per_week} days/week, {user.session_duration_min} min/session
- Equipment: {user.equipment}
- Current injuries: {user.injuries_current}
- Postural issues: {user.postural_issues}
- Mobility issues: {user.mobility_issues}
- Likes: {user.training_likes}, Dislikes: {user.training_dislikes}

Return compact JSON only. Respect injuries/mobility. Max 2 mesocycles, 2 representative weeks each, 5 exercises/workout, 3 sets/exercise, all notes null."""

    result = complete(system_prompt, user_prompt, max_tokens=8192, model='claude-sonnet-4-6')
    # Strip markdown code fences that the model sometimes wraps around JSON
    result = re.sub(r'^```(?:json)?\s*', '', result.strip())
    result = re.sub(r'\s*```$', '', result).strip()
    try:
        return json.loads(result)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI returned invalid JSON for program generation: {e}") from e
