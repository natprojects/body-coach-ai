from datetime import datetime, date, timedelta
import pytest
from app.core.models import User
from app.core.auth import create_jwt
from app.modules.calisthenics.models import CalisthenicsProfile, CalisthenicsAssessment
from app.modules.training.models import (
    Program, Mesocycle, ProgramWeek, Workout, Exercise, WorkoutExercise, PlannedSet,
    WorkoutSession,
)


def _make_user(db, telegram_id=70200, days_per_week=4, optional_target=2):
    u = User(
        telegram_id=telegram_id, name='Stats', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['floor'], onboarding_completed_at=datetime.utcnow(),
        active_module='calisthenics',
    )
    db.session.add(u); db.session.commit()
    p = CalisthenicsProfile(
        user_id=u.id, goals=['muscle'], equipment=['floor'],
        days_per_week=days_per_week, session_duration_min=45,
        injuries=[], motivation='look',
        optional_target_per_week=optional_target,
    )
    db.session.add(p); db.session.commit()
    return u, p


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


def _add_session(db, user, kind, dow_offset_from_monday):
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    s = WorkoutSession(
        user_id=user.id, module='calisthenics', status='completed',
        date=monday + timedelta(days=dow_offset_from_monday),
        kind=kind,
    )
    db.session.add(s); db.session.commit()
    return s


def test_weekly_stats_zero_when_no_sessions(app, client, db):
    user, _ = _make_user(db, telegram_id=70200)
    r = client.get('/api/calisthenics/stats/weekly', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['main_done'] == 0
    assert data['mini_done'] == 0
    assert data['main_target'] == 4
    assert data['mini_target'] == 2


def test_weekly_stats_counts_main_and_mini(app, client, db):
    user, _ = _make_user(db, telegram_id=70201)
    _add_session(db, user, 'main', 0)
    _add_session(db, user, 'main', 1)
    _add_session(db, user, 'mini', 2)
    r = client.get('/api/calisthenics/stats/weekly', headers=_h(app, user.id))
    data = r.get_json()['data']
    assert data['main_done'] == 2
    assert data['mini_done'] == 1


def test_weekly_stats_excludes_other_modules(app, client, db):
    user, _ = _make_user(db, telegram_id=70202)
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    db.session.add(WorkoutSession(
        user_id=user.id, module='gym', status='completed',
        date=monday, kind='main',
    ))
    db.session.commit()
    r = client.get('/api/calisthenics/stats/weekly', headers=_h(app, user.id))
    assert r.get_json()['data']['main_done'] == 0


def test_weekly_stats_excludes_in_progress(app, client, db):
    user, _ = _make_user(db, telegram_id=70203)
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    db.session.add(WorkoutSession(
        user_id=user.id, module='calisthenics', status='in_progress',
        date=monday, kind='main',
    ))
    db.session.commit()
    r = client.get('/api/calisthenics/stats/weekly', headers=_h(app, user.id))
    assert r.get_json()['data']['main_done'] == 0


def test_weekly_stats_no_profile_returns_zero_targets(app, client, db):
    u = User(telegram_id=70204, name='NoProf', gender='female', age=25,
             weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
             level='beginner', training_days_per_week=3, session_duration_min=45,
             equipment=['floor'], onboarding_completed_at=datetime.utcnow(),
             active_module='calisthenics')
    db.session.add(u); db.session.commit()
    r = client.get('/api/calisthenics/stats/weekly', headers=_h(app, u.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['main_target'] == 0
    assert data['mini_target'] == 0


def test_weekly_stats_requires_auth(app, client):
    r = client.get('/api/calisthenics/stats/weekly')
    assert r.status_code == 401


def test_history_returns_recent_sessions(app, client, db):
    user, _ = _make_user(db, telegram_id=70210)
    today = date.today()
    p = Program(user_id=user.id, name='C', periodization_type='hypertrophy',
                total_weeks=4, status='active', module='calisthenics')
    db.session.add(p); db.session.flush()
    m = Mesocycle(program_id=p.id, name='m', order_index=0, weeks_count=1)
    db.session.add(m); db.session.flush()
    w = ProgramWeek(mesocycle_id=m.id, week_number=1)
    db.session.add(w); db.session.flush()
    main_w = Workout(program_week_id=w.id, day_of_week=0, name='Push A', order_index=0)
    db.session.add(main_w); db.session.flush()

    db.session.add(WorkoutSession(user_id=user.id, workout_id=main_w.id, module='calisthenics',
                                   status='completed', date=today - timedelta(days=2), kind='main'))
    mini_w = Workout(program_week_id=None, mini_kind='stretch', day_of_week=0,
                     name='10хв стретч', order_index=0)
    db.session.add(mini_w); db.session.flush()
    db.session.add(WorkoutSession(user_id=user.id, workout_id=mini_w.id, module='calisthenics',
                                   status='completed', date=today, kind='mini'))
    db.session.commit()

    r = client.get('/api/calisthenics/sessions/history', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert len(data) == 2
    assert data[0]['kind'] == 'mini'
    assert data[0]['workout_name'] == '10хв стретч'
    assert data[1]['kind'] == 'main'


def test_history_limit_param(app, client, db):
    user, _ = _make_user(db, telegram_id=70211)
    today = date.today()
    for i in range(5):
        db.session.add(WorkoutSession(
            user_id=user.id, module='calisthenics', status='completed',
            date=today - timedelta(days=i), kind='main',
        ))
    db.session.commit()
    r = client.get('/api/calisthenics/sessions/history?limit=3', headers=_h(app, user.id))
    assert len(r.get_json()['data']) == 3


def test_session_detail_returns_logged_sets(app, client, db):
    from app.modules.training.models import LoggedExercise, LoggedSet
    user, _ = _make_user(db, telegram_id=70212)
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
    pushup = Exercise.query.filter_by(module='calisthenics', name='full pushup').first()
    we = WorkoutExercise(workout_id=workout.id, exercise_id=pushup.id, order_index=0)
    db.session.add(we); db.session.commit()

    s = WorkoutSession(user_id=user.id, workout_id=workout.id, module='calisthenics',
                       status='completed', date=today, kind='main')
    db.session.add(s); db.session.flush()
    le = LoggedExercise(session_id=s.id, exercise_id=pushup.id, order_index=0)
    db.session.add(le); db.session.flush()
    db.session.add(LoggedSet(logged_exercise_id=le.id, set_number=1, actual_reps=10))
    db.session.add(LoggedSet(logged_exercise_id=le.id, set_number=2, actual_reps=12))
    db.session.commit()

    r = client.get(f'/api/calisthenics/sessions/{s.id}/detail', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['workout_name'] == 'Push A'
    assert data['kind'] == 'main'
    assert len(data['exercises']) == 1
    assert data['exercises'][0]['exercise_name'] == 'full pushup'
    assert len(data['exercises'][0]['logged_sets']) == 2
    assert data['exercises'][0]['logged_sets'][0]['actual_reps'] == 10


def test_session_detail_404_for_other_user(app, client, db):
    user1, _ = _make_user(db, telegram_id=70213)
    user2, _ = _make_user(db, telegram_id=70214)
    s = WorkoutSession(user_id=user1.id, module='calisthenics',
                       status='completed', date=date.today(), kind='main')
    db.session.add(s); db.session.commit()
    r = client.get(f'/api/calisthenics/sessions/{s.id}/detail', headers=_h(app, user2.id))
    assert r.status_code == 404


def test_history_requires_auth(app, client):
    r = client.get('/api/calisthenics/sessions/history')
    assert r.status_code == 401


def test_session_detail_requires_auth(app, client):
    r = client.get('/api/calisthenics/sessions/1/detail')
    assert r.status_code == 401
