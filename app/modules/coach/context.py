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


NUTRITIONIST_SYSTEM_ADDENDUM = """

## Nutritionist mode for this conversation
You are acting as the user's personal sports nutritionist for this thread.
- Anchor advice to the user's actual targets (calories, protein, fat, carbs) and dietary restrictions
- Coordinate with their training: pre/post-workout timing, recovery nutrition for hard sessions
- Coordinate with their cycle phase if available: iron-rich foods around menstruation, magnesium luteal phase
- When the user describes a meal or daily intake, give concrete macro estimates and gap analysis vs targets
- When the user asks "what should I eat", give 2-3 concrete options with rough macro splits — not just principles
- Stay practical: assume basic kitchen + their stated cooking_skill and budget"""


def build_coach_context(user_id: int) -> str:
    from app.core.models import PainJournal, User
    from app.extensions import db
    from app.modules.training.models import Program, WorkoutSession, Exercise

    parts = [build_base_system(user_id)]

    user = db.session.get(User, user_id)
    if user:
        parts.append(f"\n## Active module: {user.active_module}")

    # ── GYM ──
    gym_program = (Program.query
                   .filter_by(user_id=user_id, status='active', module='gym')
                   .first())
    if gym_program:
        parts.append(f"\n## Gym Program: {gym_program.name} ({gym_program.periodization_type}, {gym_program.total_weeks} weeks)")

    last_gym_session = (WorkoutSession.query
                        .filter_by(user_id=user_id, status='completed', module='gym')
                        .order_by(WorkoutSession.date.desc())
                        .first())
    if last_gym_session:
        parts.append(f"\n### Last Gym Workout ({last_gym_session.date.isoformat()})")
        for le in last_gym_session.logged_exercises:
            sets_text = ', '.join(
                f"{s.actual_reps}r×{s.actual_weight_kg}kg RPE{s.actual_rpe}"
                for s in le.logged_sets
            )
            parts.append(f"- {le.exercise.name}: {sets_text or 'no sets'}")

    # ── CALISTHENICS ──
    cali_program = (Program.query
                    .filter_by(user_id=user_id, status='active', module='calisthenics')
                    .first())
    if cali_program:
        parts.append(f"\n## Calisthenics Program: {cali_program.name} ({cali_program.periodization_type}, {cali_program.total_weeks} weeks)")

    try:
        from app.modules.calisthenics.models import CalisthenicsProfile, CalisthenicsAssessment
        cali_profile = CalisthenicsProfile.query.filter_by(user_id=user_id).first()
        if cali_profile:
            parts.append(
                f"\n### Calisthenics Profile\n"
                f"- Goals: {cali_profile.goals}, Equipment: {cali_profile.equipment}\n"
                f"- {cali_profile.days_per_week}/week × {cali_profile.session_duration_min}min, "
                f"Injuries: {cali_profile.injuries}, Motivation: {cali_profile.motivation}"
            )
        last_assess = (CalisthenicsAssessment.query
                       .filter_by(user_id=user_id)
                       .order_by(CalisthenicsAssessment.assessed_at.desc())
                       .first())
        if last_assess:
            parts.append(
                f"\n### Last Calisthenics Assessment ({last_assess.assessed_at.date().isoformat()})\n"
                f"- pullups: {last_assess.pullups}, australian: {last_assess.australian_pullups}, "
                f"pushups: {last_assess.pushups}, pike: {last_assess.pike_pushups}\n"
                f"- squats: {last_assess.squats}, lunges: {last_assess.lunges}\n"
                f"- plank: {last_assess.plank}s, hollow body: {last_assess.hollow_body}s, "
                f"superman: {last_assess.superman_hold}s"
            )
    except ImportError:
        pass

    last_cali_session = (WorkoutSession.query
                         .filter_by(user_id=user_id, status='completed', module='calisthenics')
                         .order_by(WorkoutSession.date.desc())
                         .first())
    if last_cali_session:
        parts.append(f"\n### Last Calisthenics Workout ({last_cali_session.date.isoformat()})")
        for le in last_cali_session.logged_exercises:
            ex = db.session.get(Exercise, le.exercise_id)
            unit = (ex.unit if ex else 'reps')
            sets_text_parts = []
            for s in le.logged_sets:
                if unit == 'seconds' and s.actual_seconds is not None:
                    sets_text_parts.append(f"{s.actual_seconds}s")
                elif s.actual_reps is not None:
                    sets_text_parts.append(f"{s.actual_reps}r")
            ex_name = ex.name if ex else (le.exercise.name if le.exercise else '?')
            parts.append(f"- {ex_name}: {', '.join(sets_text_parts) or 'no sets'}")

    # ── NUTRITION ──
    try:
        from app.modules.nutrition.models import NutritionProfile, MealLog
        nutr = NutritionProfile.query.filter_by(user_id=user_id).first()
        if nutr:
            allergies_str = ', '.join(nutr.allergies) if nutr.allergies else 'none'
            parts.append(
                f"\n## Nutrition Profile\n"
                f"- Diet: {nutr.diet_type}, Allergies: {allergies_str}, "
                f"Cooking skill: {nutr.cooking_skill}, Budget: {nutr.budget}\n"
                f"- Targets: {int(nutr.calorie_target or 0)} kcal | "
                f"P {int(nutr.protein_g or 0)}g | F {int(nutr.fat_g or 0)}g | "
                f"C {int(nutr.carbs_g or 0)}g"
            )
        meal_since = date.today() - timedelta(days=7)
        meals = (MealLog.query
                 .filter(MealLog.user_id == user_id, MealLog.date >= meal_since)
                 .order_by(MealLog.date.desc())
                 .limit(20)
                 .all())
        if meals:
            parts.append("\n### Recent meals (last 7 days)")
            for m in meals:
                parts.append(f"- {m.date}: {m.description}")
    except ImportError:
        pass

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


def build_cross_thread_history(user_id: int, current_thread_id: int, limit: int = 25) -> str:
    """Snapshot of recent messages from the user's OTHER threads — added to system
    so AI has shared memory across the unified chat."""
    from .models import ChatThread, ChatMessage

    other_threads = (ChatThread.query
                     .filter(ChatThread.user_id == user_id,
                             ChatThread.id != current_thread_id)
                     .order_by(ChatThread.updated_at.desc())
                     .limit(8)
                     .all())
    if not other_threads:
        return ''
    thread_ids = [t.id for t in other_threads]
    msgs = (ChatMessage.query
            .filter(ChatMessage.thread_id.in_(thread_ids))
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
            .all())[::-1]
    if not msgs:
        return ''

    titles = {t.id: t.title for t in other_threads}
    lines = ["## Recent activity in your other threads (for shared memory)"]
    last_thread = None
    for m in msgs:
        if m.thread_id != last_thread:
            lines.append(f"\n### {titles.get(m.thread_id, '?')}")
            last_thread = m.thread_id
        prefix = 'You' if m.role == 'user' else 'Coach'
        snippet = (m.content or '').strip().replace('\n', ' ')
        if len(snippet) > 220:
            snippet = snippet[:220] + '…'
        lines.append(f"- {prefix}: {snippet}")
    return '\n'.join(lines)
