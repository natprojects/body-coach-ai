# tests/calisthenics/test_routes.py
from datetime import datetime, timedelta
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


# ── Profile endpoints ──────────────────────────────────────────────────────────

def test_get_profile_no_profile(app, client, db):
    user = _make_user(db, telegram_id=60007)
    r = client.get('/api/calisthenics/profile', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['data'] is None


def test_post_profile_creates(app, client, db):
    user = _make_user(db, telegram_id=60008)
    body = {
        'goals': ['muscle', 'strength'],
        'equipment': ['floor', 'bands', 'dumbbells'],
        'days_per_week': 4,
        'session_duration_min': 45,
        'injuries': [],
        'motivation': 'look',
    }
    r = client.post('/api/calisthenics/profile', json=body, headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['goals'] == ['muscle', 'strength']
    assert data['equipment'] == ['floor', 'bands', 'dumbbells']
    assert data['days_per_week'] == 4
    assert data['motivation'] == 'look'


def test_post_profile_updates_existing(app, client, db):
    from app.modules.calisthenics.models import CalisthenicsProfile
    user = _make_user(db, telegram_id=60009)
    existing = CalisthenicsProfile(user_id=user.id, goals=['muscle'], motivation='look')
    db.session.add(existing)
    db.session.commit()
    r = client.post(
        '/api/calisthenics/profile',
        json={'goals': ['strength', 'endurance'], 'motivation': 'achieve',
              'equipment': ['bands'], 'days_per_week': 3, 'session_duration_min': 30,
              'injuries': []},
        headers=_h(app, user.id),
    )
    assert r.status_code == 200
    assert r.get_json()['data']['goals'] == ['strength', 'endurance']
    assert CalisthenicsProfile.query.filter_by(user_id=user.id).count() == 1


def test_post_profile_invalid_days(app, client, db):
    user = _make_user(db, telegram_id=60010)
    r = client.post(
        '/api/calisthenics/profile',
        json={'goals': ['muscle'], 'equipment': [], 'days_per_week': 0,
              'session_duration_min': 45, 'injuries': [], 'motivation': 'look'},
        headers=_h(app, user.id),
    )
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'INVALID_FIELD'


def test_post_profile_invalid_motivation(app, client, db):
    user = _make_user(db, telegram_id=60011)
    r = client.post(
        '/api/calisthenics/profile',
        json={'goals': ['muscle'], 'equipment': [], 'days_per_week': 3,
              'session_duration_min': 45, 'injuries': [], 'motivation': 'money'},
        headers=_h(app, user.id),
    )
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'INVALID_FIELD'


def test_get_profile_returns_data(app, client, db):
    from app.modules.calisthenics.models import CalisthenicsProfile
    user = _make_user(db, telegram_id=60017)
    profile = CalisthenicsProfile(
        user_id=user.id, goals=['muscle'], equipment=['floor'],
        days_per_week=3, session_duration_min=45, injuries=[], motivation='look',
    )
    db.session.add(profile)
    db.session.commit()
    r = client.get('/api/calisthenics/profile', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['goals'] == ['muscle']
    assert data['equipment'] == ['floor']
    assert data['motivation'] == 'look'


def test_get_profile_requires_auth(app, client, db):
    r = client.get('/api/calisthenics/profile')
    assert r.status_code == 401


def test_post_profile_requires_auth(app, client, db):
    r = client.post('/api/calisthenics/profile', json={})
    assert r.status_code == 401


# ── Assessment endpoints ───────────────────────────────────────────────────────

def _make_profile(db, user_id):
    from app.modules.calisthenics.models import CalisthenicsProfile
    p = CalisthenicsProfile(
        user_id=user_id, goals=['muscle'], equipment=['floor', 'bands', 'dumbbells'],
        days_per_week=4, session_duration_min=45, injuries=[], motivation='look',
    )
    db.session.add(p)
    db.session.commit()
    return p


def test_post_assessment_saves_results(app, client, db):
    user = _make_user(db, telegram_id=60012)
    _make_profile(db, user.id)
    body = {
        'pullups': None,
        'australian_pullups': 8,
        'pushups': 15,
        'pike_pushups': 10,
        'squats': 25,
        'superman_hold': 30,
        'plank': 45,
        'hollow_body': 20,
        'lunges': 12,
        'notes': 'First assessment',
    }
    r = client.post('/api/calisthenics/assessment', json=body, headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['id'] is not None
    assert data['pullups'] is None
    assert data['pushups'] == 15
    assert data['plank'] == 45
    assert data['notes'] == 'First assessment'


def test_post_assessment_requires_profile(app, client, db):
    user = _make_user(db, telegram_id=60013)
    r = client.post(
        '/api/calisthenics/assessment',
        json={'pushups': 10, 'squats': 20, 'plank': 30, 'hollow_body': 15,
              'lunges': 10, 'australian_pullups': 5, 'pike_pushups': 8,
              'superman_hold': 20},
        headers=_h(app, user.id),
    )
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'PROFILE_REQUIRED'


def test_post_assessment_invalid_field(app, client, db):
    user = _make_user(db, telegram_id=60014)
    _make_profile(db, user.id)
    r = client.post(
        '/api/calisthenics/assessment',
        json={'pushups': -1, 'squats': 20, 'plank': 30, 'hollow_body': 15,
              'lunges': 10, 'australian_pullups': 5, 'pike_pushups': 8,
              'superman_hold': 20},
        headers=_h(app, user.id),
    )
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'INVALID_FIELD'


def test_get_assessment_history_returns_all(app, client, db):
    from app.modules.calisthenics.models import CalisthenicsAssessment
    user = _make_user(db, telegram_id=60015)
    _make_profile(db, user.id)
    now = datetime.utcnow()
    for i in range(3):
        a = CalisthenicsAssessment(
            user_id=user.id, pushups=10 + i, squats=20, plank=30,
            hollow_body=15, lunges=10, australian_pullups=5,
            pike_pushups=8, superman_hold=20,
            assessed_at=now - timedelta(seconds=2 - i),
        )
        db.session.add(a)
    db.session.commit()
    r = client.get('/api/calisthenics/assessment/history', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert len(data) == 3
    # Verify newest-first ordering across all three entries
    assert data[0]['pushups'] > data[1]['pushups'] > data[2]['pushups']


def test_get_assessment_history_empty(app, client, db):
    user = _make_user(db, telegram_id=60016)
    r = client.get('/api/calisthenics/assessment/history', headers=_h(app, user.id))
    assert r.status_code == 200
    assert r.get_json()['data'] == []


def test_post_assessment_requires_auth(app, client, db):
    r = client.post('/api/calisthenics/assessment', json={})
    assert r.status_code == 401


def test_get_assessment_history_requires_auth(app, client, db):
    r = client.get('/api/calisthenics/assessment/history')
    assert r.status_code == 401


def test_post_profile_accepts_optional_target(app, client, db):
    user = _make_user(db, telegram_id=70080)
    body = {
        'goals': ['muscle'], 'equipment': ['floor'],
        'days_per_week': 4, 'session_duration_min': 45,
        'injuries': [], 'motivation': 'look',
        'optional_target_per_week': 2,
    }
    r = client.post('/api/calisthenics/profile', json=body, headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['optional_target_per_week'] == 2


def test_post_profile_default_optional_target_zero(app, client, db):
    user = _make_user(db, telegram_id=70081)
    body = {
        'goals': ['muscle'], 'equipment': ['floor'],
        'days_per_week': 4, 'session_duration_min': 45,
        'injuries': [], 'motivation': 'look',
    }
    r = client.post('/api/calisthenics/profile', json=body, headers=_h(app, user.id))
    assert r.status_code == 200
    assert r.get_json()['data']['optional_target_per_week'] == 0


def test_post_profile_invalid_optional_target(app, client, db):
    user = _make_user(db, telegram_id=70082)
    body = {
        'goals': ['muscle'], 'equipment': ['floor'],
        'days_per_week': 4, 'session_duration_min': 45,
        'injuries': [], 'motivation': 'look',
        'optional_target_per_week': 8,
    }
    r = client.post('/api/calisthenics/profile', json=body, headers=_h(app, user.id))
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'INVALID_FIELD'
