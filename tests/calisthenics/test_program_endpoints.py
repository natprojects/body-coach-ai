from datetime import datetime
from unittest.mock import patch
import pytest
from app.core.models import User
from app.core.auth import create_jwt
from app.modules.calisthenics.models import CalisthenicsProfile, CalisthenicsAssessment


SAMPLE = {
    "name": "Calisthenics Foundations",
    "periodization_type": "hypertrophy",
    "total_weeks": 4,
    "mesocycles": [{
        "name": "Block 1", "order_index": 0, "weeks_count": 1,
        "weeks": [{
            "week_number": 1, "notes": None,
            "workouts": [{
                "day_of_week": 0, "name": "Push A", "order_index": 0,
                "target_muscle_groups": "Chest", "estimated_duration_min": 35, "warmup_notes": "...",
                "exercises": [{
                    "exercise_name": "full pushup", "order_index": 0,
                    "tempo": "3-1-2-0", "is_mandatory": True, "coaching_notes": "...",
                    "sets": [
                        {"set_number": 1, "target_reps": "8-12", "target_seconds": None,
                         "target_rpe": 7.0, "rest_seconds": 90, "is_amrap": False},
                        {"set_number": 2, "target_reps": "8-12", "target_seconds": None,
                         "target_rpe": 8.0, "rest_seconds": 90, "is_amrap": False},
                        {"set_number": 3, "target_reps": "8-12", "target_seconds": None,
                         "target_rpe": 9.0, "rest_seconds": 90, "is_amrap": True},
                    ],
                }],
            }],
        }],
    }],
}


def _make_user(db, telegram_id=90001, with_profile=True, with_assessment=True):
    u = User(
        telegram_id=telegram_id, name='C', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['floor'], onboarding_completed_at=datetime.utcnow(),
        active_module='calisthenics',
    )
    db.session.add(u)
    db.session.commit()
    if with_profile:
        db.session.add(CalisthenicsProfile(
            user_id=u.id, goals=['muscle'], equipment=['floor'],
            days_per_week=3, session_duration_min=45, injuries=[], motivation='look',
        ))
    if with_assessment:
        db.session.add(CalisthenicsAssessment(
            user_id=u.id, australian_pullups=8, pushups=12, pike_pushups=8,
            squats=20, superman_hold=20, plank=30, hollow_body=15, lunges=12,
        ))
    db.session.commit()
    return u


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


@patch('app.modules.calisthenics.routes.generate_calisthenics_program', return_value=SAMPLE)
def test_generate_creates_program(mock_gen, app, client, db):
    user = _make_user(db, telegram_id=90001)
    r = client.post('/api/calisthenics/program/generate', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['name'] == 'Calisthenics Foundations'
    assert data['module'] == 'calisthenics'
    assert mock_gen.called


def test_generate_requires_profile(app, client, db):
    user = _make_user(db, telegram_id=90002, with_profile=False)
    r = client.post('/api/calisthenics/program/generate', headers=_h(app, user.id))
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'PROFILE_REQUIRED'


def test_generate_requires_assessment(app, client, db):
    user = _make_user(db, telegram_id=90003, with_assessment=False)
    r = client.post('/api/calisthenics/program/generate', headers=_h(app, user.id))
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'ASSESSMENT_REQUIRED'


def test_generate_requires_auth(app, client):
    r = client.post('/api/calisthenics/program/generate')
    assert r.status_code == 401


def test_get_active_no_program(app, client, db):
    user = _make_user(db, telegram_id=90004)
    r = client.get('/api/calisthenics/program/active', headers=_h(app, user.id))
    assert r.status_code == 200
    assert r.get_json()['data'] is None


@patch('app.modules.calisthenics.routes.generate_calisthenics_program', return_value=SAMPLE)
def test_get_active_returns_program(mock_gen, app, client, db):
    user = _make_user(db, telegram_id=90005)
    client.post('/api/calisthenics/program/generate', headers=_h(app, user.id))
    r = client.get('/api/calisthenics/program/active', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data is not None
    assert data['name'] == 'Calisthenics Foundations'
    assert len(data['mesocycles']) == 1
