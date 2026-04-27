from datetime import datetime, date, timedelta
import pytest
from app.core.models import User
from app.modules.calisthenics.models import CalisthenicsProfile, CalisthenicsAssessment
from app.modules.training.models import (
    Program, Mesocycle, ProgramWeek, Workout, Exercise, WorkoutExercise,
    PlannedSet, WorkoutSession, LoggedExercise, LoggedSet,
)


def _make_user(db, telegram_id=70300):
    u = User(
        telegram_id=telegram_id, name='CtxTest', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['floor'], onboarding_completed_at=datetime.utcnow(),
        active_module='calisthenics',
    )
    db.session.add(u); db.session.commit()
    return u


def test_context_no_calisthenics_data_shows_empty_message(app, db):
    from app.modules.coach.context import build_coach_context
    user = _make_user(db, telegram_id=70300)
    ctx = build_coach_context(user.id)
    assert 'No recent calisthenics sessions' in ctx


def test_context_includes_30d_session_counts(app, db):
    from app.modules.coach.context import build_coach_context
    user = _make_user(db, telegram_id=70301)
    today = date.today()
    for d in range(5):
        db.session.add(WorkoutSession(
            user_id=user.id, module='calisthenics', status='completed',
            date=today - timedelta(days=d * 2), kind='main',
        ))
    for d in range(2):
        db.session.add(WorkoutSession(
            user_id=user.id, module='calisthenics', status='completed',
            date=today - timedelta(days=d), kind='mini',
        ))
    db.session.commit()
    ctx = build_coach_context(user.id)
    assert '7 sessions' in ctx
    assert '5 main' in ctx
    assert '2 mini' in ctx


def test_context_old_sessions_excluded_from_30d_window(app, db):
    from app.modules.coach.context import build_coach_context
    user = _make_user(db, telegram_id=70302)
    db.session.add(WorkoutSession(
        user_id=user.id, module='calisthenics', status='completed',
        date=date.today() - timedelta(days=60), kind='main',
    ))
    db.session.commit()
    ctx = build_coach_context(user.id)
    assert 'No recent calisthenics sessions' in ctx


def test_context_groups_by_chain(app, db):
    from app.modules.coach.context import build_coach_context
    user = _make_user(db, telegram_id=70303)
    p = Program(user_id=user.id, name='C', periodization_type='hypertrophy',
                total_weeks=4, status='active', module='calisthenics')
    db.session.add(p); db.session.flush()
    m = Mesocycle(program_id=p.id, name='m', order_index=0, weeks_count=1)
    db.session.add(m); db.session.flush()
    w = ProgramWeek(mesocycle_id=m.id, week_number=1)
    db.session.add(w); db.session.flush()
    push_workout = Workout(program_week_id=w.id, day_of_week=0,
                           name='Push A', order_index=0)
    db.session.add(push_workout); db.session.flush()
    full_pushup = Exercise.query.filter_by(module='calisthenics', name='full pushup').first()
    db.session.add(WorkoutExercise(workout_id=push_workout.id, exercise_id=full_pushup.id, order_index=0))
    db.session.commit()

    db.session.add(WorkoutSession(
        user_id=user.id, workout_id=push_workout.id, module='calisthenics',
        status='completed', date=date.today() - timedelta(days=1), kind='main',
    ))
    db.session.commit()

    ctx = build_coach_context(user.id)
    assert 'push' in ctx.lower()


def test_context_includes_amrap_trends(app, db):
    from app.modules.coach.context import build_coach_context
    user = _make_user(db, telegram_id=70304)
    today = date.today()
    p = Program(user_id=user.id, name='C', periodization_type='hypertrophy',
                total_weeks=4, status='active', module='calisthenics')
    db.session.add(p); db.session.flush()
    m = Mesocycle(program_id=p.id, name='m', order_index=0, weeks_count=1)
    db.session.add(m); db.session.flush()
    w = ProgramWeek(mesocycle_id=m.id, week_number=1)
    db.session.add(w); db.session.flush()
    workout = Workout(program_week_id=w.id, day_of_week=0, name='Push A', order_index=0)
    db.session.add(workout); db.session.flush()
    full_pushup = Exercise.query.filter_by(module='calisthenics', name='full pushup').first()
    we = WorkoutExercise(workout_id=workout.id, exercise_id=full_pushup.id, order_index=0)
    db.session.add(we); db.session.commit()

    # 3 sessions with rising AMRAP values
    for i, val in enumerate([10, 12, 15]):
        s = WorkoutSession(user_id=user.id, workout_id=workout.id, module='calisthenics',
                           status='completed', date=today - timedelta(days=10 - i*3), kind='main')
        db.session.add(s); db.session.flush()
        le = LoggedExercise(session_id=s.id, exercise_id=full_pushup.id, order_index=0)
        db.session.add(le); db.session.flush()
        db.session.add(LoggedSet(logged_exercise_id=le.id, set_number=1, actual_reps=val))
        db.session.commit()

    ctx = build_coach_context(user.id)
    # Expect trend line like "full pushup: 10 → 12 → 15"
    assert 'full pushup' in ctx
    assert '10' in ctx and '12' in ctx and '15' in ctx
    assert '→' in ctx
