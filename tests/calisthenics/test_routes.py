# tests/calisthenics/test_routes.py
from datetime import datetime
import pytest
from app.core.models import User
from app.core.auth import create_jwt


def _make_user(db, telegram_id=60001):
    u = User(
        telegram_id=telegram_id, name='CaliTest', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['bands', 'dumbbells'], onboarding_completed_at=datetime.utcnow(),
    )
    db.session.add(u)
    db.session.commit()
    return u


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


# ── Model tests ────────────────────────────────────────────────────────────────

def test_calisthenics_profile_creation(app, db):
    from app.modules.calisthenics.models import CalisthenicsProfile
    user = _make_user(db)
    profile = CalisthenicsProfile(
        user_id=user.id,
        goals=['muscle', 'strength'],
        equipment=['floor', 'bands', 'dumbbells'],
        days_per_week=4,
        session_duration_min=45,
        injuries=[],
        motivation='look',
    )
    db.session.add(profile)
    db.session.commit()
    fetched = CalisthenicsProfile.query.filter_by(user_id=user.id).first()
    assert fetched is not None
    assert fetched.goals == ['muscle', 'strength']
    assert fetched.motivation == 'look'


def test_calisthenics_assessment_creation(app, db):
    from app.modules.calisthenics.models import CalisthenicsAssessment
    user = _make_user(db, telegram_id=60002)
    a = CalisthenicsAssessment(
        user_id=user.id,
        pullups=None,
        australian_pullups=8,
        pushups=15,
        pike_pushups=10,
        squats=25,
        superman_hold=30,
        plank=45,
        hollow_body=20,
        lunges=12,
    )
    db.session.add(a)
    db.session.commit()
    fetched = CalisthenicsAssessment.query.filter_by(user_id=user.id).first()
    assert fetched is not None
    assert fetched.pullups is None
    assert fetched.pushups == 15
    assert fetched.plank == 45


def test_user_active_module_default(app, db):
    user = _make_user(db, telegram_id=60003)
    assert user.active_module == 'gym'


# ── active-module endpoint ─────────────────────────────────────────────────────

def test_patch_active_module_to_calisthenics(app, client, db):
    user = _make_user(db, telegram_id=60004)
    assert user.active_module == 'gym'
    r = client.patch(
        '/api/user/active-module',
        json={'module': 'calisthenics'},
        headers=_h(app, user.id),
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['data']['active_module'] == 'calisthenics'
    db.session.refresh(user)
    assert user.active_module == 'calisthenics'


def test_patch_active_module_back_to_gym(app, client, db):
    user = _make_user(db, telegram_id=60005)
    user.active_module = 'calisthenics'
    db.session.commit()
    r = client.patch(
        '/api/user/active-module',
        json={'module': 'gym'},
        headers=_h(app, user.id),
    )
    assert r.status_code == 200
    assert r.get_json()['data']['active_module'] == 'gym'


def test_patch_active_module_invalid_value(app, client, db):
    user = _make_user(db, telegram_id=60006)
    r = client.patch(
        '/api/user/active-module',
        json={'module': 'yoga'},
        headers=_h(app, user.id),
    )
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'INVALID_MODULE'


def test_patch_active_module_requires_auth(app, client, db):
    r = client.patch('/api/user/active-module', json={'module': 'calisthenics'})
    assert r.status_code == 401
