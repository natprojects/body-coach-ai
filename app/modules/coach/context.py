from datetime import date, timedelta

from app.core.ai import build_base_system

COACH_SYSTEM = """You are an elite personal coach combining expertise of:
physical therapist, rehabilitation therapist, biomechanics specialist,
sports nutritionist, registered dietitian, sport psychologist,
exercise psychologist, strength & conditioning coach, wellness coach.

Rules:
- Always respond in the user's language (Ukrainian if app_language='uk', else English)
- Be specific — reference the user's actual data (program, last workout, check-in numbers)
- Never give generic advice. Say "Your bench press was 60kg at RPE 8 yesterday" not "keep training hard"
- Keep responses concise: 3-5 bullet points or short paragraphs
- If asked about pain or injury: give guidance AND recommend seeing a doctor for diagnosis
- Use markdown headers (##) and bullets (-) — they render correctly in the app
- Never say "I'm just an AI" — you are their coach"""


def build_coach_context(user_id: int) -> str:
    from app.core.models import PainJournal
    from app.extensions import db
    from app.modules.training.models import (
        WorkoutSession,
    )

    parts = [build_base_system(user_id)]

    # Active program
    from app.modules.training.models import Program
    program = Program.query.filter_by(user_id=user_id, status='active').first()
    if program:
        parts.append(f"\n## Active Program: {program.name} ({program.periodization_type})")
        parts.append(f"Total weeks: {program.total_weeks}")

    # Last completed workout
    last_session = (WorkoutSession.query
                    .filter_by(user_id=user_id, status='completed')
                    .order_by(WorkoutSession.date.desc())
                    .first())
    if last_session:
        parts.append(f"\n## Last Workout ({last_session.date.isoformat()})")
        for le in last_session.logged_exercises:
            sets_text = ', '.join(
                f"{s.actual_reps}r×{s.actual_weight_kg}kg RPE{s.actual_rpe}"
                for s in le.logged_sets
            )
            parts.append(f"- {le.exercise.name}: {sets_text or 'no sets'}")

    # Recent pain journal (last 14 days, max 3 entries)
    since = date.today() - timedelta(days=14)
    pain_entries = (PainJournal.query
                    .filter(PainJournal.user_id == user_id, PainJournal.date >= since)
                    .order_by(PainJournal.date.desc())
                    .limit(3)
                    .all())
    if pain_entries:
        parts.append("\n## Recent Pain Journal")
        for p in pain_entries:
            parts.append(f"- {p.date}: {p.body_part} ({p.pain_type}, intensity {p.intensity}/10)")

    return '\n'.join(parts)
