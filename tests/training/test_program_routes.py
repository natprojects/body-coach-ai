import json
from unittest.mock import MagicMock
from datetime import datetime
from app.core.models import User
from app.core.auth import create_jwt
from app.modules.training.coach import save_program_from_dict

SAMPLE_PROGRAM = {
    "name": "Test Block",
    "periodization_type": "linear",
    "total_weeks": 4,
    "mesocycles": [{
        "name": "Accumulation",
        "order_index": 0,
        "weeks_count": 4,
        "weeks": [{
            "week_number": 1,
            "notes": None,
            "workouts": [{
                "day_of_week": 0,
                "name": "Upper A",
                "order_index": 0,
                "exercises": [{
                    "exercise_name": "Bench Press",
                    "order_index": 0,
                    "notes": None,
                    "sets": [{"set_number": 1, "target_reps": "8-10",
                               "target_weight_kg": 60.0, "target_rpe": 7.0, "rest_seconds": 120}]
                }]
            }]
        }]
    }]
}


def _make_user(db):
    user = User(
        telegram_id=70001, name='Test', gender='female', age=25,
        weight_kg=58.0, height_cm=163.0, goal_primary='hypertrophy',
        level='intermediate', training_days_per_week=4, session_duration_min=60,
        equipment=['full_gym'], injuries_current=[], postural_issues=[],
        mobility_issues=[], muscle_imbalances=[],
        onboarding_completed_at=datetime.utcnow()
    )
    db.session.add(user)
    db.session.commit()
    return user


def _auth(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


def test_get_program_full_no_program(client, app, db):
    user = _make_user(db)
    resp = client.get('/api/training/program/full', headers=_auth(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data'] is None


def test_get_program_full_with_program(client, app, db):
    user = _make_user(db)
    save_program_from_dict(user.id, SAMPLE_PROGRAM)
    resp = client.get('/api/training/program/full', headers=_auth(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    prog = data['data']
    assert prog['name'] == 'Test Block'
    assert prog['insights_generated'] is False
    assert len(prog['mesocycles']) == 1
    week = prog['mesocycles'][0]['weeks'][0]
    assert week['week_number'] == 1
    ex = week['workouts'][0]['exercises'][0]
    assert ex['exercise_name'] == 'Bench Press'
    assert ex['selection_reason'] is None
    assert len(ex['sets']) == 1


def test_get_program_full_requires_auth(client):
    resp = client.get('/api/training/program/full')
    assert resp.status_code == 401


def test_post_insights_generates_and_saves(client, app, db, mock_anthropic):
    user = _make_user(db)
    program = save_program_from_dict(user.id, SAMPLE_PROGRAM)
    from app.modules.training.models import WorkoutExercise, Workout, ProgramWeek, Mesocycle
    we = (WorkoutExercise.query
          .join(Workout).join(ProgramWeek).join(Mesocycle)
          .filter(Mesocycle.program_id == program.id).first())

    mock_anthropic.messages.create.return_value = MagicMock(content=[MagicMock(
        text=json.dumps([{
            "workout_exercise_id": we.id,
            "selection_reason": "Great for hypertrophy",
            "expected_outcome": "More chest mass",
            "modifications_applied": None,
        }])
    )])

    resp = client.post('/api/training/program/insights', headers=_auth(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['count'] == 1

    db.session.refresh(we)
    assert we.selection_reason == "Great for hypertrophy"


def test_post_insights_skips_if_already_done(client, app, db, mock_anthropic):
    user = _make_user(db)
    program = save_program_from_dict(user.id, SAMPLE_PROGRAM)
    from app.modules.training.models import WorkoutExercise, Workout, ProgramWeek, Mesocycle
    we = (WorkoutExercise.query
          .join(Workout).join(ProgramWeek).join(Mesocycle)
          .filter(Mesocycle.program_id == program.id).first())
    we.selection_reason = "Already set"
    db.session.commit()

    resp = client.post('/api/training/program/insights', headers=_auth(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['data']['already_done'] is True
    mock_anthropic.messages.create.assert_not_called()
