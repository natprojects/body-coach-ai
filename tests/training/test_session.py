import json
from datetime import date, datetime
from unittest.mock import MagicMock
from app.core.models import User
from app.core.auth import create_jwt
from app.modules.training.coach import save_program_from_dict
from app.modules.training.models import (
    Exercise, LoggedExercise, LoggedSet, Workout, WorkoutSession
)

SAMPLE_PROGRAM = {
    "name": "Test Program", "periodization_type": "linear", "total_weeks": 4,
    "mesocycles": [{
        "name": "Accumulation", "order_index": 0, "weeks_count": 4,
        "weeks": [{
            "week_number": 1, "notes": None,
            "workouts": [{
                "day_of_week": date.today().weekday(), "name": "Full Body", "order_index": 0,
                "exercises": [{
                    "exercise_name": "Squat", "order_index": 0, "notes": None,
                    "sets": [
                        {"set_number": 1, "target_reps": "5", "target_weight_kg": 80.0,
                         "target_rpe": 8.0, "rest_seconds": 180}
                    ]
                }]
            }]
        }]
    }]
}


def _make_user(db):
    user = User(
        telegram_id=70001, name='Test', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='strength',
        level='intermediate', training_days_per_week=3, session_duration_min=60,
        equipment=['full_gym'], onboarding_completed_at=datetime.utcnow()
    )
    db.session.add(user)
    db.session.commit()
    return user


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


def test_get_today_workout(client, app, db):
    user = _make_user(db)
    save_program_from_dict(user.id, SAMPLE_PROGRAM)
    resp = client.get('/api/training/today', headers=_h(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data is not None
    assert data['name'] == 'Full Body'
    assert len(data['exercises']) == 1


def test_start_session(client, app, db):
    user = _make_user(db)
    save_program_from_dict(user.id, SAMPLE_PROGRAM)
    today_resp = client.get('/api/training/today', headers=_h(app, user.id))
    workout_id = today_resp.get_json()['data']['id']
    resp = client.post('/api/training/session/start', json={'workout_id': workout_id},
                       headers=_h(app, user.id))
    assert resp.status_code == 200
    session_id = resp.get_json()['data']['session_id']
    assert WorkoutSession.query.get(session_id).status == 'in_progress'


def test_log_set(client, app, db):
    user = _make_user(db)
    save_program_from_dict(user.id, SAMPLE_PROGRAM)
    exercise = Exercise.query.filter_by(name='Squat').first()
    session = WorkoutSession(user_id=user.id, date=date.today())
    db.session.add(session)
    db.session.commit()
    resp = client.post('/api/training/session/log-set', json={
        'session_id': session.id,
        'exercise_id': exercise.id,
        'set_number': 1,
        'actual_reps': 5,
        'actual_weight_kg': 82.5,
        'actual_rpe': 8.5,
    }, headers=_h(app, user.id))
    assert resp.status_code == 200
    assert LoggedSet.query.count() == 1
    assert LoggedExercise.query.count() == 1


def test_log_second_set_appends_to_same_logged_exercise(client, app, db):
    user = _make_user(db)
    save_program_from_dict(user.id, SAMPLE_PROGRAM)
    exercise = Exercise.query.filter_by(name='Squat').first()
    session = WorkoutSession(user_id=user.id, date=date.today())
    db.session.add(session)
    db.session.commit()
    for i, (reps, weight) in enumerate([(5, 80.0), (5, 82.5)], start=1):
        client.post('/api/training/session/log-set', json={
            'session_id': session.id, 'exercise_id': exercise.id,
            'set_number': i, 'actual_reps': reps, 'actual_weight_kg': weight, 'actual_rpe': 8.0,
        }, headers=_h(app, user.id))
    assert LoggedExercise.query.count() == 1
    assert LoggedSet.query.count() == 2


def test_complete_session(client, app, db, mock_anthropic):
    user = _make_user(db)
    session = WorkoutSession(user_id=user.id, date=date.today())
    db.session.add(session)
    db.session.commit()
    mock_anthropic.messages.create.return_value = MagicMock(
        content=[MagicMock(text='Great workout! You hit all your targets.')]
    )
    resp = client.post('/api/training/session/complete', json={'session_id': session.id},
                       headers=_h(app, user.id))
    assert resp.status_code == 200
    updated = WorkoutSession.query.get(session.id)
    assert updated.status == 'completed'
    assert updated.ai_feedback == 'Great workout! You hit all your targets.'
