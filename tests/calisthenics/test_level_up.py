from datetime import datetime, timedelta, date
import pytest
from app.core.models import User
from app.modules.training.models import (
    Program, Mesocycle, ProgramWeek, Workout, Exercise, WorkoutExercise,
    PlannedSet, WorkoutSession, LoggedExercise, LoggedSet,
)
from app.core.auth import create_jwt


def _setup(db, telegram_id=93001):
    u = User(telegram_id=telegram_id, name='LU', gender='female', age=25,
            weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
            level='beginner', training_days_per_week=3, session_duration_min=45,
            equipment=['floor'], onboarding_completed_at=datetime.utcnow(),
            active_module='calisthenics')
    db.session.add(u); db.session.commit()
    p = Program(user_id=u.id, name='C', periodization_type='hypertrophy',
                total_weeks=4, status='active', module='calisthenics')
    db.session.add(p); db.session.flush()
    m = Mesocycle(program_id=p.id, name='m', order_index=0, weeks_count=1)
    db.session.add(m); db.session.flush()
    w = ProgramWeek(mesocycle_id=m.id, week_number=1)
    db.session.add(w); db.session.flush()
    wo = Workout(program_week_id=w.id, day_of_week=0, name='Push', order_index=0)
    db.session.add(wo); db.session.flush()
    full_pushup = Exercise.query.filter_by(module='calisthenics', name='full pushup').first()
    we = WorkoutExercise(workout_id=wo.id, exercise_id=full_pushup.id, order_index=0)
    db.session.add(we); db.session.flush()
    for n in (1, 2, 3):
        ps = PlannedSet(workout_exercise_id=we.id, set_number=n,
                        target_reps='8-12', target_rpe=8.0, rest_seconds=90,
                        is_amrap=(n == 3))
        db.session.add(ps)
    db.session.commit()
    return u, p, wo, we, full_pushup


def _log_session(db, user, workout, exercise, amrap_value, dow_offset):
    s = WorkoutSession(user_id=user.id, workout_id=workout.id,
                       module='calisthenics', status='completed',
                       date=date.today() - timedelta(days=dow_offset))
    db.session.add(s); db.session.flush()
    le = LoggedExercise(session_id=s.id, exercise_id=exercise.id, order_index=0)
    db.session.add(le); db.session.flush()
    db.session.add(LoggedSet(logged_exercise_id=le.id, set_number=1, actual_reps=10))
    db.session.add(LoggedSet(logged_exercise_id=le.id, set_number=2, actual_reps=10))
    db.session.add(LoggedSet(logged_exercise_id=le.id, set_number=3, actual_reps=amrap_value))
    db.session.commit()
    return s


def test_level_up_three_strong_sessions_promotes(app, db):
    from app.modules.calisthenics.level_up import compute_level_up_suggestions
    user, program, wo, we, full = _setup(db, telegram_id=93001)
    for d in (3, 2, 1):
        _log_session(db, user, wo, full, amrap_value=15, dow_offset=d)
    suggestions = compute_level_up_suggestions(user.id, program)
    assert len(suggestions) == 1
    assert suggestions[0]['exercise_name_current'] == 'full pushup'
    assert suggestions[0]['exercise_name_next'] == 'diamond pushup'


def test_level_up_two_strong_one_weak_no_suggestion(app, db):
    from app.modules.calisthenics.level_up import compute_level_up_suggestions
    user, program, wo, we, full = _setup(db, telegram_id=93002)
    _log_session(db, user, wo, full, amrap_value=15, dow_offset=3)
    _log_session(db, user, wo, full, amrap_value=14, dow_offset=2)
    _log_session(db, user, wo, full, amrap_value=10, dow_offset=1)
    assert compute_level_up_suggestions(user.id, program) == []


def test_level_up_only_two_sessions_no_suggestion(app, db):
    from app.modules.calisthenics.level_up import compute_level_up_suggestions
    user, program, wo, we, full = _setup(db, telegram_id=93003)
    _log_session(db, user, wo, full, amrap_value=20, dow_offset=2)
    _log_session(db, user, wo, full, amrap_value=20, dow_offset=1)
    assert compute_level_up_suggestions(user.id, program) == []


def test_level_up_no_next_level_skipped(app, db):
    from app.modules.calisthenics.level_up import compute_level_up_suggestions
    user, program, wo, we, full = _setup(db, telegram_id=93004)
    one_arm = Exercise.query.filter_by(module='calisthenics', name='one-arm pushup').first()
    we.exercise_id = one_arm.id
    db.session.commit()
    for d in (3, 2, 1):
        _log_session(db, user, wo, one_arm, amrap_value=20, dow_offset=d)
    assert compute_level_up_suggestions(user.id, program) == []


def test_level_up_seconds_unit(app, db):
    from app.modules.calisthenics.level_up import compute_level_up_suggestions
    user, program, wo, we, full = _setup(db, telegram_id=93005)
    plank = Exercise.query.filter_by(module='calisthenics', name='forearm plank').first()
    we.exercise_id = plank.id
    for ps in PlannedSet.query.filter_by(workout_exercise_id=we.id).all():
        ps.target_reps = None
        ps.target_seconds = 30
    db.session.commit()

    for d in (3, 2, 1):
        s = WorkoutSession(user_id=user.id, workout_id=wo.id, module='calisthenics',
                           status='completed', date=date.today() - timedelta(days=d))
        db.session.add(s); db.session.flush()
        le = LoggedExercise(session_id=s.id, exercise_id=plank.id, order_index=0)
        db.session.add(le); db.session.flush()
        db.session.add(LoggedSet(logged_exercise_id=le.id, set_number=3, actual_seconds=45))
        db.session.commit()

    suggestions = compute_level_up_suggestions(user.id, program)
    assert len(suggestions) == 1
    assert suggestions[0]['exercise_name_next'] == 'hollow body hold'


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


def test_apply_level_up_swaps_exercise(app, client, db):
    user, program, wo, we, full = _setup(db, telegram_id=93010)
    for d in (3, 2, 1):
        _log_session(db, user, wo, full, amrap_value=15, dow_offset=d)
    diamond = Exercise.query.filter_by(module='calisthenics', name='diamond pushup').first()
    r = client.post(f'/api/calisthenics/program/{program.id}/level-up',
                    json={'from_exercise_id': full.id, 'to_exercise_id': diamond.id},
                    headers=_h(app, user.id))
    assert r.status_code == 200
    db.session.refresh(we)
    assert we.exercise_id == diamond.id


def test_apply_level_up_rejects_when_criteria_not_met(app, client, db):
    user, program, wo, we, full = _setup(db, telegram_id=93011)
    diamond = Exercise.query.filter_by(module='calisthenics', name='diamond pushup').first()
    r = client.post(f'/api/calisthenics/program/{program.id}/level-up',
                    json={'from_exercise_id': full.id, 'to_exercise_id': diamond.id},
                    headers=_h(app, user.id))
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'LEVEL_UP_NOT_READY'
