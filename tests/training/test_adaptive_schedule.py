from datetime import date, datetime
from app.core.models import User
from app.core.auth import create_jwt
from app.modules.training.coach import save_program_from_dict
from app.modules.training.models import Mesocycle, ProgramWeek, Workout, WorkoutSession


def _off_days():
    """Two day_of_week values guaranteed to not be today."""
    today = date.today().weekday()
    return (today + 2) % 7, (today + 4) % 7


def _make_user(db):
    user = User(
        telegram_id=80101, name='AdaptTest', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='intermediate', training_days_per_week=3, session_duration_min=60,
        equipment=['full_gym'], onboarding_completed_at=datetime.utcnow()
    )
    db.session.add(user)
    db.session.commit()
    return user


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


def _make_two_workout_program(user_id, day1, day2):
    """Program with Workout A on day1 (order 0) and Workout B on day2 (order 1)."""
    return save_program_from_dict(user_id, {
        "name": "Adaptive Test", "periodization_type": "linear", "total_weeks": 4,
        "mesocycles": [{"name": "Block", "order_index": 0, "weeks_count": 4, "weeks": [{
            "week_number": 1, "notes": None, "workouts": [
                {"day_of_week": day1, "name": "Workout A", "order_index": 0, "exercises": [{
                    "exercise_name": "Squat", "order_index": 0, "notes": None,
                    "sets": [{"set_number": 1, "target_reps": "8-10",
                              "target_weight_kg": 60.0, "target_rpe": 7.0, "rest_seconds": 90}]
                }]},
                {"day_of_week": day2, "name": "Workout B", "order_index": 1, "exercises": [{
                    "exercise_name": "Bench Press", "order_index": 0, "notes": None,
                    "sets": [{"set_number": 1, "target_reps": "8-10",
                              "target_weight_kg": 50.0, "target_rpe": 7.0, "rest_seconds": 90}]
                }]},
            ]
        }]}]
    })


def test_ad_hoc_returns_next_incomplete_workout(client, app, db):
    """On an unscheduled day, returns first incomplete workout with ad_hoc=True."""
    day1, day2 = _off_days()
    user = _make_user(db)
    _make_two_workout_program(user.id, day1, day2)

    resp = client.get('/api/training/today', headers=_h(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data.get('rest_day') is not True
    assert data['name'] == 'Workout A'
    assert data['ad_hoc'] is True


def test_scheduled_day_no_ad_hoc(client, app, db):
    """On a scheduled day, ad_hoc key is absent from response."""
    today_dow = date.today().weekday()
    user = _make_user(db)
    save_program_from_dict(user.id, {
        "name": "Sched Test", "periodization_type": "linear", "total_weeks": 4,
        "mesocycles": [{"name": "Block", "order_index": 0, "weeks_count": 4, "weeks": [{
            "week_number": 1, "notes": None, "workouts": [{
                "day_of_week": today_dow, "name": "Today Workout", "order_index": 0,
                "exercises": [{"exercise_name": "Deadlift", "order_index": 0, "notes": None,
                               "sets": [{"set_number": 1, "target_reps": "5",
                                         "target_weight_kg": 80.0, "target_rpe": 8.0,
                                         "rest_seconds": 180}]}]
            }]
        }]}]
    })

    resp = client.get('/api/training/today', headers=_h(app, user.id))
    data = resp.get_json()['data']
    assert data['name'] == 'Today Workout'
    assert 'ad_hoc' not in data


def test_all_completed_returns_rest_day(client, app, db):
    """When all workouts in the week are completed, returns rest_day=True."""
    day1, day2 = _off_days()
    user = _make_user(db)
    program = _make_two_workout_program(user.id, day1, day2)

    mesocycle = Mesocycle.query.filter_by(program_id=program.id).first()
    week = ProgramWeek.query.filter_by(mesocycle_id=mesocycle.id, week_number=1).first()
    for wo in Workout.query.filter_by(program_week_id=week.id).all():
        db.session.add(WorkoutSession(
            user_id=user.id, workout_id=wo.id, date=date.today(), status='completed'
        ))
    db.session.commit()

    resp = client.get('/api/training/today', headers=_h(app, user.id))
    data = resp.get_json()['data']
    assert data.get('rest_day') is True


def test_ad_hoc_skips_completed_workouts(client, app, db):
    """When Workout A is completed, returns Workout B with ad_hoc=True."""
    day1, day2 = _off_days()
    user = _make_user(db)
    program = _make_two_workout_program(user.id, day1, day2)

    mesocycle = Mesocycle.query.filter_by(program_id=program.id).first()
    week = ProgramWeek.query.filter_by(mesocycle_id=mesocycle.id, week_number=1).first()
    workout_a = Workout.query.filter_by(program_week_id=week.id, order_index=0).first()
    db.session.add(WorkoutSession(
        user_id=user.id, workout_id=workout_a.id, date=date.today(), status='completed'
    ))
    db.session.commit()

    resp = client.get('/api/training/today', headers=_h(app, user.id))
    data = resp.get_json()['data']
    assert data['name'] == 'Workout B'
    assert data['ad_hoc'] is True


def test_recommendations_today_on_ad_hoc_day(client, app, db):
    """recommendations_today returns recs list on an unscheduled day (not empty)."""
    day1, day2 = _off_days()
    user = _make_user(db)
    _make_two_workout_program(user.id, day1, day2)

    resp = client.get('/api/training/recommendations/today', headers=_h(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert 'recommendations' in data
    recs = data['recommendations']
    # Workout A has one exercise (Squat); with no prior sessions the endpoint
    # falls back to planned targets, so the list must not be empty.
    assert len(recs) == 1
    assert recs[0]['exercise_name'] == 'Squat'
    assert recs[0]['recommendation_type'] == 'planned'
    assert recs[0]['recommended_weight_kg'] == 60.0
