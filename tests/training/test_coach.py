import json
from unittest.mock import MagicMock
from app.core.models import User
from app.core.auth import create_jwt
from app.modules.training.models import Program, Mesocycle, ProgramWeek, Workout, WorkoutExercise, PlannedSet, Exercise

SAMPLE_PROGRAM = {
    "name": "4-Week Block Program",
    "periodization_type": "block",
    "total_weeks": 4,
    "mesocycles": [
        {
            "name": "Accumulation",
            "order_index": 0,
            "weeks_count": 3,
            "weeks": [
                {
                    "week_number": 1,
                    "notes": "Focus on form",
                    "workouts": [
                        {
                            "day_of_week": 0,
                            "name": "Upper Body A",
                            "order_index": 0,
                            "exercises": [
                                {
                                    "exercise_name": "Bench Press",
                                    "order_index": 0,
                                    "notes": None,
                                    "sets": [
                                        {"set_number": 1, "target_reps": "8-10",
                                         "target_weight_kg": 50.0, "target_rpe": 7.0, "rest_seconds": 120}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]
}


def _make_user(db):
    user = User(
        telegram_id=60001, name='Natalie', gender='female', age=26,
        weight_kg=58.0, height_cm=163.0, goal_primary='hypertrophy',
        level='intermediate', training_days_per_week=4, session_duration_min=60,
        equipment=['full_gym'], onboarding_completed_at=__import__('datetime').datetime.utcnow()
    )
    db.session.add(user)
    db.session.commit()
    return user


def test_build_training_context_with_program(db, app):
    from app.modules.training.coach import build_training_context, save_program_from_dict
    user = _make_user(db)
    save_program_from_dict(user.id, SAMPLE_PROGRAM)
    context = build_training_context(user.id)
    assert '4-Week Block Program' in context
    assert 'block' in context


def test_save_program_creates_full_hierarchy(db, app):
    from app.modules.training.coach import save_program_from_dict
    user = _make_user(db)
    program = save_program_from_dict(user.id, SAMPLE_PROGRAM)
    assert program.id is not None
    assert len(program.mesocycles) == 1
    assert len(program.mesocycles[0].weeks) == 1
    assert len(program.mesocycles[0].weeks[0].workouts) == 1
    exercise = Exercise.query.filter_by(name='Bench Press').first()
    assert exercise is not None
    ps = PlannedSet.query.first()
    assert ps.target_reps == '8-10'


def test_generate_program_endpoint(client, app, db, mock_anthropic):
    user = _make_user(db)
    mock_anthropic.messages.create.return_value = MagicMock(
        content=[MagicMock(text=json.dumps(SAMPLE_PROGRAM))]
    )
    token = create_jwt(user.id, app.config['SECRET_KEY'])
    resp = client.post('/api/training/program/generate',
                       headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert Program.query.filter_by(user_id=user.id).count() == 1


def test_generate_program_requires_onboarding(client, app, db):
    user = User(telegram_id=60002)
    db.session.add(user)
    db.session.commit()
    token = create_jwt(user.id, app.config['SECRET_KEY'])
    resp = client.post('/api/training/program/generate',
                       headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 400


def test_generate_exercise_insights(db, app, mock_anthropic):
    from app.modules.training.coach import save_program_from_dict, generate_exercise_insights
    from app.modules.training.models import WorkoutExercise
    import json

    user = _make_user(db)
    program = save_program_from_dict(user.id, SAMPLE_PROGRAM)

    we = WorkoutExercise.query.first()
    insights_response = [
        {
            "workout_exercise_id": we.id,
            "selection_reason": "Great compound push movement for hypertrophy",
            "expected_outcome": "Increased chest and front delt mass",
            "modifications_applied": None,
        }
    ]
    mock_anthropic.messages.create.return_value = MagicMock(
        content=[MagicMock(text=json.dumps(insights_response))]
    )

    count = generate_exercise_insights(program, user)

    we_refreshed = db.session.get(WorkoutExercise, we.id)
    assert count >= 1
    assert we_refreshed.selection_reason == "Great compound push movement for hypertrophy"
    assert we_refreshed.expected_outcome == "Increased chest and front delt mass"
    assert we_refreshed.modifications_applied is None
