from app.core.models import User
from app.core.auth import create_jwt


def _headers(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


def _make_user(db, telegram_id=50001):
    user = User(telegram_id=telegram_id)
    db.session.add(user)
    db.session.commit()
    return user


def test_onboarding_status_not_completed(client, app, db):
    user = _make_user(db)
    resp = client.get('/api/onboarding/status', headers=_headers(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['data']['completed'] is False
    assert data['data']['next_step'] == 'basic_data'


def test_basic_data_step(client, app, db):
    user = _make_user(db, 50002)
    resp = client.post('/api/onboarding/step', json={
        'step': 'basic_data',
        'data': {'name': 'Natalie', 'gender': 'female', 'age': 26, 'weight_kg': 58.0, 'height_cm': 163.0}
    }, headers=_headers(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['data']['next_step'] == 'goals'
    user = User.query.get(user.id)
    assert user.name == 'Natalie'
    assert user.weight_kg == 58.0


def test_goals_step(client, app, db):
    user = _make_user(db, 50003)
    user.name = 'Test'
    db.session.commit()
    resp = client.post('/api/onboarding/step', json={
        'step': 'goals',
        'data': {'goal_primary': 'hypertrophy', 'goal_secondary': ['health']}
    }, headers=_headers(app, user.id))
    assert resp.status_code == 200
    updated = User.query.get(user.id)
    assert updated.goal_primary == 'hypertrophy'


def test_complete_onboarding(client, app, db):
    user = _make_user(db, 50004)
    resp = client.post('/api/onboarding/complete', headers=_headers(app, user.id))
    assert resp.status_code == 200
    updated = User.query.get(user.id)
    assert updated.onboarding_completed_at is not None


def test_invalid_step_name(client, app, db):
    user = _make_user(db, 50005)
    resp = client.post('/api/onboarding/step', json={
        'step': 'nonexistent_step', 'data': {}
    }, headers=_headers(app, user.id))
    assert resp.status_code == 400
