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
