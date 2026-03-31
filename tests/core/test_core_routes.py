import json
import hashlib
import hmac
import urllib.parse
from datetime import date
from app.core.models import User, DailyCheckin, PainJournal, BodyMeasurement
from app.core.auth import create_jwt


def _auth_header(app, user_id):
    token = create_jwt(user_id, app.config['SECRET_KEY'])
    return {'Authorization': f'Bearer {token}'}


def _make_init_data(bot_token, telegram_id=123456):
    user_json = json.dumps({"id": telegram_id, "first_name": "Natalie"})
    params = {"user": user_json, "auth_date": "1700000000"}
    data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
    params['hash'] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(params)


def test_auth_validate_creates_user(client, app, db):
    init_data = _make_init_data(app.config['TELEGRAM_BOT_TOKEN'])
    resp = client.post('/api/auth/validate', json={'init_data': init_data})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'token' in data['data']
    assert User.query.filter_by(telegram_id=123456).first() is not None


def test_auth_validate_invalid(client):
    resp = client.post('/api/auth/validate', json={'init_data': 'bad=data&hash=wrong'})
    assert resp.status_code == 401


def test_create_checkin(client, app, db):
    user = User(telegram_id=30001)
    db.session.add(user)
    db.session.commit()
    resp = client.post('/api/checkin', json={
        'energy_level': 7, 'sleep_quality': 6, 'stress_level': 4,
        'motivation': 8, 'soreness_level': 3
    }, headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    assert DailyCheckin.query.filter_by(user_id=user.id).count() == 1


def test_get_checkin_today(client, app, db):
    user = User(telegram_id=30002)
    db.session.add(user)
    db.session.commit()
    checkin = DailyCheckin(user_id=user.id, date=date.today(), energy_level=9, sleep_quality=8,
                           stress_level=2, motivation=10, soreness_level=1)
    db.session.add(checkin)
    db.session.commit()
    resp = client.get('/api/checkin/today', headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    assert resp.get_json()['data']['energy_level'] == 9


def test_create_pain_entry(client, app, db):
    user = User(telegram_id=30003)
    db.session.add(user)
    db.session.commit()
    resp = client.post('/api/pain', json={
        'body_part': 'left knee', 'pain_type': 'sharp',
        'intensity': 6, 'when_occurs': 'during'
    }, headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    assert PainJournal.query.filter_by(user_id=user.id).count() == 1


def test_create_measurement(client, app, db):
    user = User(telegram_id=30004)
    db.session.add(user)
    db.session.commit()
    resp = client.post('/api/measurements', json={
        'weight_kg': 62.5, 'waist_cm': 72.0, 'hips_cm': 95.0
    }, headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    assert BodyMeasurement.query.filter_by(user_id=user.id).count() == 1


def test_get_user_me(client, app, db):
    from app.core.models import User
    user = User(telegram_id=40001, name='Natalie', gender='female', age=26,
                weight_kg=58.0, height_cm=163.0, goal_primary='hypertrophy',
                level='intermediate', training_days_per_week=4)
    db.session.add(user)
    db.session.commit()
    resp = client.get('/api/users/me', headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['name'] == 'Natalie'
    assert data['data']['goal_primary'] == 'hypertrophy'
    assert 'telegram_id' not in data['data']
    assert 'password_hash' not in data['data']


def test_patch_user_me(client, app, db):
    from app.core.models import User
    user = User(telegram_id=40002, name='Old Name', age=25)
    db.session.add(user)
    db.session.commit()
    resp = client.patch('/api/users/me',
                        json={'name': 'New Name', 'age': 27, 'weight_kg': 60.5},
                        headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['name'] == 'New Name'
    assert data['data']['age'] == 27
    assert data['data']['weight_kg'] == 60.5


def test_patch_user_me_ignores_protected_fields(client, app, db):
    from app.core.models import User
    user = User(telegram_id=40003)
    db.session.add(user)
    db.session.commit()
    resp = client.patch('/api/users/me',
                        json={'telegram_id': 99999, 'password_hash': 'hacked'},
                        headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    db.session.refresh(user)
    assert user.telegram_id == 40003
    assert user.password_hash is None


def test_get_user_me_requires_auth(client):
    resp = client.get('/api/users/me')
    assert resp.status_code == 401


def test_app_language_in_profile(client, app, db):
    from app.core.models import User
    user = User(telegram_id=50001, name='LangTest')
    db.session.add(user)
    db.session.commit()
    # GET returns app_language
    resp = client.get('/api/users/me', headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'app_language' in data['data']

    # PATCH updates app_language
    resp2 = client.patch('/api/users/me',
                         json={'app_language': 'uk'},
                         headers=_auth_header(app, user.id))
    assert resp2.status_code == 200
    assert resp2.get_json()['data']['app_language'] == 'uk'
