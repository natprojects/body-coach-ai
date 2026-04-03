from sqlalchemy import func

from app.core.ai import build_base_system, complete
from .models import LoggedExercise, LoggedSet, WorkoutExercise, WorkoutSession


def generate_post_workout_feedback(session: WorkoutSession, user_id: int) -> str:
    from app.core.models import User
    from app.extensions import db

    user = db.session.get(User, user_id)
    lang = (getattr(user, 'app_language', 'en') or 'en')
    lang_note = "Write ALL output in Ukrainian." if lang == 'uk' else "Write ALL output in English."

    high_rpe_exercises = []
    prs = []
    log_lines = []

    for le in session.logged_exercises:
        if not le.logged_sets:
            continue

        weights = [s.actual_weight_kg or 0 for s in le.logged_sets]
        rpes = [s.actual_rpe or 0 for s in le.logged_sets]
        avg_rpe = sum(rpes) / len(rpes)
        max_weight = max(weights) if weights else 0

        if avg_rpe >= 9:
            high_rpe_exercises.append(le.exercise.name)

        # PR check: compare max weight this session vs all previous sessions
        prev_max = (
            db.session.query(func.max(LoggedSet.actual_weight_kg))
            .join(LoggedExercise, LoggedSet.logged_exercise_id == LoggedExercise.id)
            .join(WorkoutSession, LoggedExercise.session_id == WorkoutSession.id)
            .filter(
                WorkoutSession.user_id == user_id,
                WorkoutSession.status == 'completed',
                WorkoutSession.id != session.id,
                LoggedExercise.exercise_id == le.exercise_id,
            )
            .scalar() or 0
        )
        if max_weight > 0 and max_weight > prev_max:
            prs.append(f"{le.exercise.name}: {max_weight}kg (previous best: {prev_max}kg)")

        # Planned vs actual annotation
        planned_note = ''
        if session.workout_id:
            we = WorkoutExercise.query.filter_by(
                workout_id=session.workout_id,
                exercise_id=le.exercise_id,
            ).first()
            if we and we.planned_sets:
                p = we.planned_sets[0]
                planned_note = f" [PLANNED: {p.target_reps} reps @ {p.target_weight_kg}kg]"

        sets_text = '; '.join(
            f"Set {s.set_number}: {s.actual_reps}r × {s.actual_weight_kg}kg RPE{s.actual_rpe}"
            for s in le.logged_sets
        )
        log_lines.append(f"- {le.exercise.name}{planned_note}: {sets_text} | avg RPE {avg_rpe:.1f}")

    overload_flag = len(high_rpe_exercises) >= 2
    has_prs = bool(prs)

    sections = ["## ЩО ПРОЙШЛО ДОБРЕ", "## ВІДХИЛЕННЯ ВІД ПЛАНУ"]
    if overload_flag:
        sections.append("## ⚠️ ПЕРЕВАНТАЖЕННЯ")
    if has_prs:
        sections.append("## 🏆 НОВИЙ РЕКОРД")
    sections.append("## ПОРАДА НА НАСТУПНЕ ТРЕНУВАННЯ")

    rules = [
        "- ЩО ПРОЙШЛО ДОБРЕ: cite exact exercises + numbers. 'bench press up 2.5kg = progress', not 'good job'.",
        "- ВІДХИЛЕННЯ ВІД ПЛАНУ: compare actual vs planned sets/weight. State if deviation is OK or needs attention.",
        (f"- ⚠️ ПЕРЕВАНТАЖЕННЯ: name the {len(high_rpe_exercises)} exercises with avg RPE≥9. Recommend recovery." if overload_flag else ""),
        ("- 🏆 НОВИЙ РЕКОРД: celebrate each PR with exact numbers." if has_prs else ""),
        "- ПОРАДА НА НАСТУПНЕ ТРЕНУВАННЯ: exactly ONE concrete actionable tip, not generic advice.",
        "Use '- ' bullet points under each section. Keep each bullet under 15 words.",
    ]

    system = (
        build_base_system(user_id)
        + f"\n\n{lang_note}\n"
        + "Post-workout feedback. Be SPECIFIC and data-driven — no generic praise.\n"
        + "Output EXACTLY these markdown sections:\n"
        + '\n'.join(sections) + "\n\n"
        + '\n'.join(r for r in rules if r)
    )

    extra = ""
    if overload_flag:
        extra += f"\nHigh RPE (≥9): {', '.join(high_rpe_exercises)}"
    if has_prs:
        extra += f"\nNew PRs: {'; '.join(prs)}"

    return complete(
        system,
        "Workout log:\n" + '\n'.join(log_lines) + extra,
        max_tokens=1024,
        model='claude-haiku-4-5-20251001',
    )


def generate_weekly_report(user_id: int, week_sessions: list) -> str:
    from datetime import date, timedelta
    from app.core.models import DailyCheckin, PainJournal, User
    from app.extensions import db
    from .models import ExerciseRecommendation

    user = db.session.get(User, user_id)
    lang = (getattr(user, 'app_language', 'en') or 'en')
    lang_note = "Write ALL output in Ukrainian." if lang == 'uk' else "Write ALL output in English."

    since = date.today() - timedelta(days=7)

    # Volume per muscle group (total sets per mg this week)
    volume: dict = {}
    for sess in week_sessions:
        for le in sess.logged_exercises:
            mg = (getattr(le.exercise, 'muscle_group', None) or 'Інші').strip()
            volume[mg] = volume.get(mg, 0) + len(le.logged_sets)

    vol_lines = []
    for mg, sets in sorted(volume.items()):
        if sets < 10:
            tag = '⚠️ нижче норми (10-20)'
        elif sets > 20:
            tag = '⚠️ вище норми (10-20)'
        else:
            tag = '✓ оптимально'
        vol_lines.append(f"- {mg}: {sets} серій — {tag}")

    # Check-ins
    checkins = (DailyCheckin.query
                .filter(DailyCheckin.user_id == user_id, DailyCheckin.date >= since)
                .all())
    poor_sleep = sum(1 for c in checkins if c.sleep_quality and c.sleep_quality < 5)
    low_energy = sum(1 for c in checkins if c.energy_level and c.energy_level < 5)
    energy_vals = [c.energy_level for c in checkins if c.energy_level]
    avg_energy = sum(energy_vals) / len(energy_vals) if energy_vals else None
    checkin_lines = []
    if poor_sleep:
        checkin_lines.append(f"- Poor sleep quality (<5/10) on {poor_sleep} days this week")
    if low_energy:
        checkin_lines.append(f"- Low energy (<5/10) on {low_energy} days")
    if avg_energy is not None:
        checkin_lines.append(f"- Average energy: {avg_energy:.1f}/10")

    # Progressive overload summary
    recs = (ExerciseRecommendation.query
            .filter(ExerciseRecommendation.user_id == user_id,
                    ExerciseRecommendation.created_at >= since)
            .all())
    progressing = [r.exercise.name for r in recs if r.recommendation_type in ('increase_weight', 'increase_reps')]
    stagnating = [r.exercise.name for r in recs if r.recommendation_type == 'stagnation']

    # Pain journal
    pain_entries = (PainJournal.query
                    .filter(PainJournal.user_id == user_id, PainJournal.date >= since)
                    .all())

    # Deload check
    deload = check_deload_needed(user_id)

    # Build session log
    sess_lines = []
    for sess in week_sessions:
        sess_lines.append(f"\n### {sess.date.isoformat()}")
        for le in sess.logged_exercises:
            sets_text = ', '.join(f"{s.actual_reps}×{s.actual_weight_kg}kg" for s in le.logged_sets)
            sess_lines.append(f"- {le.exercise.name}: {sets_text}")

    sections = [
        "## ЗАГАЛЬНИЙ ОБ'ЄМ ПО М'ЯЗАХ",
        "## ПРОГРЕС ТА СТАГНАЦІЯ",
        "## ВІДНОВЛЕННЯ ТА САМОПОЧУТТЯ",
    ]
    if deload:
        sections.append("## ⚠️ ПОТРІБНЕ РОЗВАНТАЖЕННЯ")
    sections.append("## ПЛАН НА НАСТУПНИЙ ТИЖДЕНЬ")

    rules = [
        "- ЗАГАЛЬНИЙ ОБ'ЄМ: use the pre-computed volume data. Flag muscle groups outside 10-20 set range.",
        "- ПРОГРЕС: list specific exercises with actual numbers. Separate progressing vs stagnating.",
        "- ВІДНОВЛЕННЯ: reference sleep + energy data; say concretely how it affected training.",
        ("- ⚠️ РОЗВАНТАЖЕННЯ: explain exactly why deload is needed with specific evidence." if deload else ""),
        "- ПЛАН НА НАСТУПНИЙ ТИЖДЕНЬ: 2-3 concrete adjustments with specific numbers.",
        "Use '- ' bullets. Keep each bullet concise (under 20 words).",
    ]

    system = (
        build_base_system(user_id)
        + f"\n\n{lang_note}\n"
        + "Weekly training report. Be SPECIFIC — cite actual numbers, exercise names, dates.\n"
        + "Output EXACTLY these sections:\n"
        + '\n'.join(sections) + "\n\n"
        + '\n'.join(r for r in rules if r)
    )

    user_msg = (
        f"Sessions this week ({len(week_sessions)} completed):"
        + '\n'.join(sess_lines)
        + "\n\nVolume per muscle group:\n"
        + ('\n'.join(vol_lines) or '- No volume data')
        + "\n\nCheck-ins:\n"
        + ('\n'.join(checkin_lines) or '- No check-in data this week')
        + (f"\n\nProgressive overload:\n- Progressing: {', '.join(progressing) or 'none'}\n- Stagnating: {', '.join(stagnating) or 'none'}" if recs else "")
        + (f"\n\nPain journal:\n" + '\n'.join(f"- {p.date}: {p.body_part} ({p.pain_type}, intensity {p.intensity})" for p in pain_entries) if pain_entries else "")
        + ("\n\n⚠️ DELOAD INDICATORS DETECTED" if deload else "")
    )

    return complete(system, user_msg, max_tokens=1500, model='claude-haiku-4-5-20251001')


def _check_is_deload_period(user_id: int) -> bool:
    """True if deload is needed AND no deload rec was created in the last 7 days."""
    if not check_deload_needed(user_id):
        return False
    from datetime import date, timedelta
    from .models import ExerciseRecommendation
    cutoff = date.today() - timedelta(days=7)
    recent_deload = ExerciseRecommendation.query.filter(
        ExerciseRecommendation.user_id == user_id,
        ExerciseRecommendation.recommendation_type == 'deload',
        ExerciseRecommendation.created_at >= cutoff,
    ).first()
    return recent_deload is None


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

    # Check deload once per session, not per exercise
    _is_deload_period = _check_is_deload_period(user_id)

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

        # Decision tree
        rec_type = 'maintain'
        rec_weight = last_weight
        rec_min = target_min or 8
        rec_max = target_max or 10
        reason = ''

        # Branch 1: Deload period
        if _is_deload_period:
            rec_type = 'deload'
            rec_weight = round(last_weight * 0.6 / 2.5) * 2.5
            reason = (
                f'Deload тиждень. Знижуємо вагу до {rec_weight:.1f}kg (60% від робочої '
                f'{last_weight:.1f}kg). Об\'єм −50%: виконуй половину підходів. '
                'Мета — відновлення, а не прогрес.'
            )

        # Branch 2: RPE≥9 + pain
        elif avg_rpe >= 9 and pain_today:
            rec_type = 'decrease'
            rec_weight = round(last_weight * 0.9 / 2.5) * 2.5
            reason = (
                f'RPE {avg_rpe:.0f} + біль сьогодні. '
                f'Знизь вагу на 10% → {rec_weight:.1f}kg. '
                'Якщо біль не проходить — замін вправу на варіацію.'
            )

        # Branch 3: Stagnation
        elif stagnation:
            rec_type = 'stagnation'
            reason = (
                'Прогрес зупинився 3+ сесії поспіль. '
                'Зміни одну змінну: сповільни темп (3-1-3), '
                'збільши амплітуду, або додай підхід замість ваги.'
            )

        # Branch 4: All sets at max reps + low RPE → increase weight
        elif target_max and avg_reps >= target_max and avg_rpe <= 8:
            rec_type = 'increase_weight'
            rec_weight = last_weight + increment
            reason = (
                f'Всі підходи на максимумі повторів ({target_max}) при RPE {avg_rpe:.0f}. '
                f'+{increment}kg → {rec_weight:.1f}kg наступного разу.'
            )
            if level in ('intermediate', 'advanced'):
                reason += ' (Хвильове: застосовуй тільки на важкому тижні.)'

        # Branch 5: In range + moderate RPE → increase reps
        elif target_min and target_max and target_min <= avg_reps < target_max and avg_rpe <= 8:
            rec_type = 'increase_reps'
            rec_max = (target_max or 10) + 1
            reason = (
                f'В діапазоні ({avg_reps:.0f} повт) при RPE {avg_rpe:.0f}. '
                f'Додай 1 повтор → ціль {rec_min}–{rec_max}. '
                'Змінюй лише одну змінну за раз.'
            )

        # Branch 6: High RPE or below target → maintain
        else:
            rec_type = 'maintain'
            reason = (
                f'RPE {avg_rpe:.0f} — повтори ту ж вагу та кількість повторів. '
                'Стабільність зараз важливіша за прогрес.'
            )

        if stretch_flag:
            reason += ' Stretch-mediated: пріоритет повній амплітуді.'

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
