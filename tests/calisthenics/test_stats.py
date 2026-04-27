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
