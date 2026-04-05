# tests/nutrition/test_routes.py
from datetime import date, datetime, timedelta
import pytest
from unittest.mock import MagicMock, patch
from app.core.models import User
from app.core.auth import create_jwt
from app.modules.nutrition.models import NutritionProfile, MealLog


def _make_user(db):
    u = User(
        telegram_id=50001, name='NutrTest', gender='female', age=28,
        weight_kg=65.0, height_cm=168.0, goal_primary='fat_loss',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['home'], onboarding_completed_at=datetime.utcnow(),
    )
    db.session.add(u)
    db.session.commit()
    return u


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


# ── Model tests (from Task 3) ──────────────────────────────────────────────────

def test_nutrition_profile_creation(app, db):
    user = _make_user(db)
    profile = NutritionProfile(
        user_id=user.id, diet_type='omnivore', allergies=['lactose'],
        cooking_skill='beginner', budget='medium', activity_outside='sedentary',
        bmr=1500.0, tdee=1800.0, calorie_target=1400.0,
        protein_g=130.0, fat_g=43.6, carbs_g=175.0,
    )
    db.session.add(profile)
    db.session.commit()
    fetched = NutritionProfile.query.filter_by(user_id=user.id).first()
    assert fetched is not None
    assert fetched.diet_type == 'omnivore'
    assert fetched.allergies == ['lactose']


def test_meal_log_creation(app, db):
    user = _make_user(db)
    log = MealLog(user_id=user.id, date=date.today(), description='Гречка з куркою')
    db.session.add(log)
    db.session.commit()
    fetched = MealLog.query.filter_by(user_id=user.id).first()
    assert fetched is not None
    assert fetched.description == 'Гречка з куркою'


# ── Profile route tests ────────────────────────────────────────────────────────

def test_get_profile_no_profile(app, client, db):
    user = _make_user(db)
    r = client.get('/api/nutrition/profile', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['data'] is None


def test_get_profile_missing_weight(app, client, db):
    u = User(telegram_id=50002, name='NoWeight', onboarding_completed_at=datetime.utcnow())
    db.session.add(u)
    db.session.commit()
    r = client.get('/api/nutrition/profile', headers=_h(app, u.id))
    assert r.status_code == 400
    assert 'onboarding' in r.get_json()['error']['message'].lower()


def test_post_profile_creates_and_calculates(app, client, db):
    user = _make_user(db)  # female, 65kg, 168cm, age 28, fat_loss, 3 days/week
    body = {
        'diet_type': 'omnivore',
        'allergies': ['lactose'],
        'cooking_skill': 'beginner',
        'budget': 'medium',
        'activity_outside': 'sedentary',
    }
    r = client.post('/api/nutrition/profile', json=body, headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['diet_type'] == 'omnivore'
    assert data['allergies'] == ['lactose']
    assert data['calorie_target'] > 0
    assert data['protein_g'] == 130.0   # 2.0 * 65
    assert data['water_ml'] == 2112     # 65 * 32.5 = 2112 (int from calc_water_ml)


def test_post_profile_upserts(app, client, db):
    user = _make_user(db)
    body = {'diet_type': 'vegan', 'allergies': [], 'cooking_skill': 'advanced',
            'budget': 'high', 'activity_outside': 'moderately'}
    client.post('/api/nutrition/profile', json=body, headers=_h(app, user.id))
    body['diet_type'] = 'vegetarian'
    r = client.post('/api/nutrition/profile', json=body, headers=_h(app, user.id))
    assert r.get_json()['data']['diet_type'] == 'vegetarian'
    assert NutritionProfile.query.filter_by(user_id=user.id).count() == 1


def test_get_profile_returns_water_ml(app, client, db):
    user = _make_user(db)
    body = {'diet_type': 'omnivore', 'allergies': [], 'cooking_skill': 'intermediate',
            'budget': 'medium', 'activity_outside': 'lightly'}
    client.post('/api/nutrition/profile', json=body, headers=_h(app, user.id))
    r = client.get('/api/nutrition/profile', headers=_h(app, user.id))
    data = r.get_json()['data']
    assert 'water_ml' in data
    assert data['water_ml'] == 2112   # 65 * 32.5 = 2112 (int)


# ── Meal log route tests ───────────────────────────────────────────────────────

def test_post_meal_log(app, client, db):
    user = _make_user(db)
    r = client.post('/api/nutrition/meals/log',
                    json={'description': 'Гречка з куркою і овочами'},
                    headers=_h(app, user.id))
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    log = MealLog.query.filter_by(user_id=user.id).first()
    assert log is not None
    assert log.description == 'Гречка з куркою і овочами'
    assert log.date == date.today()


def test_post_meal_log_requires_description(app, client, db):
    user = _make_user(db)
    r = client.post('/api/nutrition/meals/log', json={}, headers=_h(app, user.id))
    assert r.status_code == 400


def test_get_meal_log_returns_14_days(app, client, db):
    user = _make_user(db)
    today = date.today()
    db.session.add(MealLog(user_id=user.id, date=today, description='Сьогодні'))
    db.session.add(MealLog(user_id=user.id, date=today - timedelta(days=10), description='10 днів тому'))
    db.session.add(MealLog(user_id=user.id, date=today - timedelta(days=20), description='20 днів тому'))
    db.session.commit()
    r = client.get('/api/nutrition/meals/log', headers=_h(app, user.id))
    assert r.status_code == 200
    entries = r.get_json()['data']
    descs = [e['description'] for e in entries]
    assert 'Сьогодні' in descs
    assert '10 днів тому' in descs
    assert '20 днів тому' not in descs


# ── Chat route tests ───────────────────────────────────────────────────────────

def test_get_chat_thread_empty(app, client, db):
    user = _make_user(db)
    r = client.get('/api/nutrition/chat/thread', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['data']['messages'] == []


def test_post_chat_message_streams(app, client, db):
    from unittest.mock import MagicMock, patch
    user = _make_user(db)
    profile = NutritionProfile(
        user_id=user.id, diet_type='omnivore', allergies=[],
        cooking_skill='beginner', budget='medium', activity_outside='sedentary',
        calorie_target=1400.0, protein_g=130.0, fat_g=43.6, carbs_g=175.0,
    )
    db.session.add(profile)
    db.session.commit()

    mock_client = MagicMock()
    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.text_stream = iter(['Спробуй ', 'вівсянку.'])
    mock_client.messages.stream.return_value = mock_stream

    with patch('app.core.ai.get_client', return_value=mock_client):
        r = client.post('/api/nutrition/chat/message',
                        json={'content': 'Що з яєць?'},
                        headers=_h(app, user.id))

    assert r.status_code == 200
    assert 'Спробуй' in r.data.decode('utf-8')


def test_post_chat_message_requires_content(app, client, db):
    user = _make_user(db)
    r = client.post('/api/nutrition/chat/message', json={}, headers=_h(app, user.id))
    assert r.status_code == 400


def test_post_profile_rejects_invalid_activity(app, client, db):
    user = _make_user(db)
    body = {'diet_type': 'omnivore', 'allergies': [], 'cooking_skill': 'beginner',
            'budget': 'medium', 'activity_outside': 'extreme'}
    r = client.post('/api/nutrition/profile', json=body, headers=_h(app, user.id))
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'INVALID_FIELD'
