from app.core.ai import build_base_system, complete
from .models import WorkoutSession


def generate_post_workout_feedback(session: WorkoutSession, user_id: int) -> str:
    system = (
        build_base_system(user_id)
        + "\n\nYou are reviewing a completed workout. Be encouraging, specific, and concise (3-5 sentences)."
    )

    lines = ["## Completed Workout Log"]
    for le in session.logged_exercises:
        sets_text = ', '.join(
            f"Set {s.set_number}: {s.actual_reps} reps @ {s.actual_weight_kg}kg RPE {s.actual_rpe}"
            for s in le.logged_sets
        )
        lines.append(f"- {le.exercise.name}: {sets_text or 'no sets logged'}")

    if session.workout_id:
        from .models import Workout
        workout = Workout.query.get(session.workout_id)
        if workout:
            lines.append(f"\nPlanned workout: {workout.name}")

    return complete(system, '\n'.join(lines))


def generate_weekly_report(user_id: int, week_sessions: list) -> str:
    from datetime import date, timedelta
    from app.core.models import PainJournal

    system = (
        build_base_system(user_id)
        + "\n\nGenerate a weekly training report. Include: performance trends, volume analysis, "
          "pain/recovery notes, and 2-3 actionable recommendations for next week."
    )

    lines = [f"## Weekly Report — {date.today().isoformat()}"]
    for session in week_sessions:
        lines.append(f"\n### Session {session.date.isoformat()}")
        for le in session.logged_exercises:
            sets_text = ', '.join(f"{s.actual_reps}x{s.actual_weight_kg}kg" for s in le.logged_sets)
            lines.append(f"- {le.exercise.name}: {sets_text}")

    since = date.today() - timedelta(days=7)
    pain_entries = PainJournal.query.filter(
        PainJournal.user_id == user_id, PainJournal.date >= since
    ).all()
    if pain_entries:
        lines.append("\n## Pain Journal This Week")
        for p in pain_entries:
            lines.append(f"- {p.date}: {p.body_part} ({p.pain_type}, intensity {p.intensity})")

    return complete(system, '\n'.join(lines))


def analyze_session_and_recommend(session_id: int, user_id: int) -> list:
    """Apply evidence-based progressive overload rules after each session.
    Returns list of ExerciseRecommendation objects created."""
    from datetime import date
    from app.core.models import PainJournal, User
    from app.extensions import db
    from .models import (
        WorkoutSession, LoggedExercise, ExerciseRecommendation,
        WorkoutExercise,
    )

    session = WorkoutSession.query.get(session_id)
    if not session:
        return []

    user = User.query.get(user_id)
    goal = (getattr(user, 'goal_primary', '') or '').lower()
    level = (getattr(user, 'level', '') or '').lower()
    is_strength_goal = 'strength' in goal

    pain_today = PainJournal.query.filter(
        PainJournal.user_id == user_id,
        PainJournal.date == date.today(),
    ).count() > 0

    recommendations = []

    for le in session.logged_exercises:
        current_sets = le.logged_sets
        if not current_sets:
            continue

        exercise_id = le.exercise_id

        # Planned targets for this exercise
        planned_reps_str = None
        planned_weight = None
        if session.workout_id:
            we = WorkoutExercise.query.filter_by(
                workout_id=session.workout_id,
                exercise_id=exercise_id,
            ).first()
            if we and we.planned_sets:
                planned_reps_str = we.planned_sets[0].target_reps
                planned_weight = we.planned_sets[0].target_weight_kg

        # Parse target rep range e.g. "8-10" → (8, 10)
        target_min = target_max = None
        if planned_reps_str:
            parts = str(planned_reps_str).split('-')
            try:
                target_min = int(parts[0])
                target_max = int(parts[-1])
            except (ValueError, IndexError):
                pass

        # Current session metrics
        avg_rpe = sum(s.actual_rpe or 0 for s in current_sets) / len(current_sets)
        avg_reps = sum(s.actual_reps or 0 for s in current_sets) / len(current_sets)
        last_weight = current_sets[0].actual_weight_kg or (planned_weight or 0)

        # Last 3 completed sessions for this exercise (excluding current)
        prev_les = (LoggedExercise.query
                    .join(WorkoutSession)
                    .filter(
                        LoggedExercise.exercise_id == exercise_id,
                        WorkoutSession.user_id == user_id,
                        WorkoutSession.status == 'completed',
                        WorkoutSession.id != session_id,
                    )
                    .order_by(WorkoutSession.date.desc())
                    .limit(3)
                    .all())

        # 2-for-2 rule: current AND previous session each had avg_reps >= target_max + 2
        two_for_two = False
        if target_max and prev_les:
            current_exceeded = avg_reps >= target_max + 2
            prev_sets = prev_les[0].logged_sets
            if prev_sets and current_exceeded:
                prev_avg = sum(s.actual_reps or 0 for s in prev_sets) / len(prev_sets)
                two_for_two = prev_avg >= target_max + 2

        # Stagnation: same weight AND same total reps for 3 consecutive sessions
        stagnation = False
        if len(prev_les) >= 2:
            weights = [last_weight] + [
                (le2.logged_sets[0].actual_weight_kg or 0)
                for le2 in prev_les[:2] if le2.logged_sets
            ]
            reps = [sum(s.actual_reps or 0 for s in le.logged_sets)] + [
                sum(s.actual_reps or 0 for s in le2.logged_sets)
                for le2 in prev_les[:2]
            ]
            if len(weights) == 3 and len(set(weights)) == 1 and len(set(reps)) == 1:
                stagnation = True

        # Lower-body exercises get +5kg, upper +2.5kg
        lower_kw = ('squat', 'deadlift', 'lunge', 'leg', 'hip', 'glute', 'calf', 'rdl', 'romanian', 'press (leg)')
        is_lower = any(kw in le.exercise.name.lower() for kw in lower_kw)
        increment = 5.0 if is_lower else 2.5

        # Stretch-mediated flag
        stretch_flag = getattr(le.exercise, 'muscle_position', None) == 'stretched'

        # Decision tree (Chaves 2024 / Plotkin 2022 / Schoenfeld 2023)
        rec_type = 'maintain'
        rec_weight = last_weight
        rec_min = target_min or 8
        rec_max = target_max or 10
        reason = ''

        if stagnation:
            rec_type = 'stagnation'
            reason = ('No progress for 3+ sessions. Change strategy: adjust tempo, '
                      'range of motion, or rep scheme — do NOT just add weight.')
        elif avg_rpe >= 9 and pain_today:
            rec_type = 'decrease'
            rec_weight = round(last_weight * 0.9 / 2.5) * 2.5
            reason = (f'RPE {avg_rpe:.0f} + pain logged today. '
                      f'Decrease weight 10% → {rec_weight:.1f}kg.')
        elif avg_rpe >= 9:
            rec_type = 'maintain'
            reason = (f'RPE {avg_rpe:.0f} — too close to failure for volume work. '
                      'Maintain same weight next session.')
        elif two_for_two and avg_rpe <= 8:
            rec_type = 'increase_weight'
            rec_weight = last_weight + increment
            prog_note = 'Load progression (strength goal).' if is_strength_goal else 'Load progression.'
            reason = (f'2-for-2 rule triggered. {prog_note} '
                      f'RPE {avg_rpe:.0f} → +{increment}kg next session.')
        elif avg_rpe <= 8:
            rec_type = 'increase_reps'
            rec_max = (target_max or 10) + 1
            reason = (f'RPE {avg_rpe:.0f} — productive zone. '
                      'Add 1 rep before increasing weight (only change ONE variable).')
        else:
            rec_type = 'maintain'
            reason = f'RPE {avg_rpe:.0f} — on track. Repeat same weight and reps.'

        # Periodization note by level
        if level in ('intermediate', 'advanced') and rec_type == 'increase_weight':
            reason += ' (Wave loading: apply on heavy week only.)'

        if stretch_flag:
            reason += ' Stretch-mediated stimulus — prioritise full ROM for max hypertrophy.'

        rec = ExerciseRecommendation(
            user_id=user_id,
            exercise_id=exercise_id,
            session_id=session_id,
            recommended_weight_kg=rec_weight,
            recommended_reps_min=rec_min,
            recommended_reps_max=rec_max,
            recommendation_type=rec_type,
            reason_text=reason,
        )
        db.session.add(rec)
        recommendations.append(rec)

    db.session.commit()
    return recommendations


def check_deload_needed(user_id: int) -> bool:
    """Return True if a deload week is recommended for this user."""
    from datetime import date, timedelta
    from app.core.models import DailyCheckin
    from .models import ExerciseRecommendation

    three_weeks_ago = date.today() - timedelta(weeks=3)

    total = ExerciseRecommendation.query.filter(
        ExerciseRecommendation.user_id == user_id,
        ExerciseRecommendation.created_at >= three_weeks_ago,
    ).count()

    if total > 0:
        stagnating = ExerciseRecommendation.query.filter(
            ExerciseRecommendation.user_id == user_id,
            ExerciseRecommendation.recommendation_type == 'stagnation',
            ExerciseRecommendation.created_at >= three_weeks_ago,
        ).count()
        if stagnating / total >= 0.6:
            return True

    # 5+ consecutive days with energy < 5
    recent = (DailyCheckin.query
              .filter(
                  DailyCheckin.user_id == user_id,
                  DailyCheckin.energy_level.isnot(None),
              )
              .order_by(DailyCheckin.date.desc())
              .limit(7)
              .all())

    consecutive_low = 0
    for c in recent:
        if (c.energy_level or 10) < 5:
            consecutive_low += 1
        else:
            break

    return consecutive_low >= 5
