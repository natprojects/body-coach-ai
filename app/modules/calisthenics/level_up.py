"""Deterministic level-up suggestion logic for calisthenics programs."""
from typing import Optional
from app.modules.training.models import (
    Program, Mesocycle, ProgramWeek, Workout, Exercise,
    WorkoutExercise, PlannedSet, WorkoutSession, LoggedExercise, LoggedSet,
)
from app.extensions import db


def _parse_reps_upper(target_reps: Optional[str]) -> Optional[int]:
    """Extract upper bound from '8-12' style range. Return None if not parseable."""
    if not target_reps:
        return None
    if '-' in target_reps:
        parts = target_reps.split('-')
        try:
            return int(parts[1].strip())
        except (ValueError, IndexError):
            return None
    try:
        return int(target_reps.strip())
    except ValueError:
        return None


def _last_n_amrap_values(user_id: int, exercise_id: int, n: int = 3) -> list:
    """Return last N completed-session AMRAP-set logged values, newest first."""
    sessions = (WorkoutSession.query
                .filter_by(user_id=user_id, module='calisthenics', status='completed')
                .order_by(WorkoutSession.date.desc(), WorkoutSession.id.desc())
                .limit(20)
                .all())

    results = []
    for s in sessions:
        le = LoggedExercise.query.filter_by(
            session_id=s.id, exercise_id=exercise_id
        ).first()
        if not le:
            continue
        last_log = (LoggedSet.query
                    .filter_by(logged_exercise_id=le.id)
                    .order_by(LoggedSet.set_number.desc())
                    .first())
        if not last_log:
            continue
        value = last_log.actual_reps if last_log.actual_reps is not None else last_log.actual_seconds
        if value is None:
            continue
        results.append(value)
        if len(results) == n:
            break
    return results


def compute_level_up_suggestions(user_id: int, program: Program) -> list:
    """Return list of level-up suggestions for the active program."""
    suggestions = []

    workouts = (Workout.query
                .join(ProgramWeek).join(Mesocycle)
                .filter(Mesocycle.program_id == program.id)
                .all())

    seen_pairs = set()
    for workout in workouts:
        for we in workout.workout_exercises:
            ex = db.session.get(Exercise, we.exercise_id)
            if not ex or not ex.progression_chain:
                continue
            next_level = (ex.progression_level or 0) + 1
            next_ex = Exercise.query.filter_by(
                module='calisthenics',
                progression_chain=ex.progression_chain,
                progression_level=next_level,
            ).first()
            if not next_ex:
                continue

            if (ex.id, next_ex.id) in seen_pairs:
                continue
            seen_pairs.add((ex.id, next_ex.id))

            amrap_set = (PlannedSet.query
                         .filter_by(workout_exercise_id=we.id, is_amrap=True)
                         .first())
            if not amrap_set:
                amrap_set = (PlannedSet.query
                             .filter_by(workout_exercise_id=we.id)
                             .order_by(PlannedSet.set_number.desc())
                             .first())
            if not amrap_set:
                continue

            if ex.unit == 'seconds':
                target_value = amrap_set.target_seconds
                threshold_bonus = 10
            else:
                target_value = _parse_reps_upper(amrap_set.target_reps)
                threshold_bonus = 3
            if not target_value:
                continue
            threshold = target_value + threshold_bonus

            recent = _last_n_amrap_values(user_id, ex.id, n=3)
            if len(recent) < 3:
                continue
            if all(v >= threshold for v in recent):
                suggestions.append({
                    'workout_exercise_id': we.id,
                    'exercise_id_current': ex.id,
                    'exercise_name_current': ex.name,
                    'exercise_id_next': next_ex.id,
                    'exercise_name_next': next_ex.name,
                    'chain': ex.progression_chain,
                    'sessions_count': 3,
                })
    return suggestions
