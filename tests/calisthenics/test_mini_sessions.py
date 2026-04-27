from datetime import datetime
from unittest.mock import patch
import pytest
from app.core.models import User
from app.core.auth import create_jwt
from app.modules.calisthenics.models import CalisthenicsProfile, CalisthenicsAssessment
from app.modules.training.models import Program, Mesocycle, ProgramWeek, Workout, Exercise, WorkoutExercise, PlannedSet


def _make_user(db, telegram_id=80101):
    u = User(
        telegram_id=telegram_id, name='Mini', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['floor'], onboarding_completed_at=datetime.utcnow(),
        active_module='calisthenics',
    )
    db.session.add(u)
    db.session.commit()
    p = CalisthenicsProfile(
        user_id=u.id, goals=['muscle'], equipment=['floor', 'bands'],
        days_per_week=4, session_duration_min=45, injuries=[], motivation='look',
        optional_target_per_week=2,
    )
    a = CalisthenicsAssessment(
        user_id=u.id, australian_pullups=8, pushups=12, pike_pushups=8,
        squats=20, superman_hold=20, plank=30, hollow_body=15, lunges=12,
    )
    db.session.add_all([p, a])
    db.session.commit()
    return u, p, a


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


SAMPLE_STRETCH = {
    "name": "10хв стретч",
    "estimated_duration_min": 10,
    "exercises": [
        {"exercise_name": "forearm plank", "order_index": 0, "tempo": None,
         "is_mandatory": True, "coaching_notes": "Hold steady",
         "sets": [{"set_number": 1, "target_reps": None, "target_seconds": 30,
                   "target_rpe": 5.0, "rest_seconds": 30, "is_amrap": False}]},
        {"exercise_name": "hollow body hold", "order_index": 1, "tempo": None,
         "is_mandatory": True, "coaching_notes": "Lower back pressed",
         "sets": [{"set_number": 1, "target_reps": None, "target_seconds": 25,
                   "target_rpe": 5.0, "rest_seconds": 30, "is_amrap": False}]},
    ],
}


def test_save_mini_session_creates_workout_with_kind(app, db):
    from app.modules.calisthenics.coach import save_mini_session_from_dict
    user, _, _ = _make_user(db, telegram_id=80101)
    workout = save_mini_session_from_dict(user.id, 'stretch', SAMPLE_STRETCH)
    assert workout.mini_kind == 'stretch'
    assert workout.program_week_id is None
    assert workout.name == '10хв стретч'
    we_count = WorkoutExercise.query.filter_by(workout_id=workout.id).count()
    assert we_count == 2
    sets = PlannedSet.query.join(WorkoutExercise).filter(WorkoutExercise.workout_id == workout.id).all()
    assert len(sets) == 2
    assert sets[0].target_seconds == 30


def test_save_mini_session_resolves_seeded_exercises(app, db):
    from app.modules.calisthenics.coach import save_mini_session_from_dict
    user, _, _ = _make_user(db, telegram_id=80102)
    workout = save_mini_session_from_dict(user.id, 'stretch', SAMPLE_STRETCH)
    we_first = WorkoutExercise.query.filter_by(workout_id=workout.id, order_index=0).first()
    ex = db.session.get(Exercise, we_first.exercise_id)
    assert ex.module == 'calisthenics'
    assert ex.name == 'forearm plank'


def test_save_mini_session_unknown_exercise_raises(app, db):
    from app.modules.calisthenics.coach import save_mini_session_from_dict
    user, _, _ = _make_user(db, telegram_id=80103)
    import copy
    bad = copy.deepcopy(SAMPLE_STRETCH)
    bad['exercises'][0]['exercise_name'] = 'invented yoga of doom'
    with pytest.raises(ValueError, match='invented yoga of doom'):
        save_mini_session_from_dict(user.id, 'stretch', bad)


def test_save_mini_session_invalid_type_raises(app, db):
    from app.modules.calisthenics.coach import save_mini_session_from_dict
    user, _, _ = _make_user(db, telegram_id=80104)
    with pytest.raises(ValueError, match='mini_type'):
        save_mini_session_from_dict(user.id, 'meditation', SAMPLE_STRETCH)


@patch('app.modules.calisthenics.routes.generate_mini_session', return_value=SAMPLE_STRETCH)
def test_generate_mini_creates_workout(mock_gen, app, client, db):
    user, _, _ = _make_user(db, telegram_id=80110)
    r = client.post('/api/calisthenics/mini-session/generate',
                    json={'type': 'stretch'}, headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['mini_kind'] == 'stretch'
    assert data['workout_id']
    workout = db.session.get(Workout, data['workout_id'])
    assert workout.mini_kind == 'stretch'
    assert workout.program_week_id is None


def test_generate_mini_invalid_type(app, client, db):
    user, _, _ = _make_user(db, telegram_id=80111)
    r = client.post('/api/calisthenics/mini-session/generate',
                    json={'type': 'meditation'}, headers=_h(app, user.id))
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'INVALID_TYPE'


def test_generate_mini_requires_profile(app, client, db):
    u = User(telegram_id=80112, name='NoProf', gender='female', age=25,
             weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
             level='beginner', training_days_per_week=3, session_duration_min=45,
             equipment=['floor'], onboarding_completed_at=datetime.utcnow(),
             active_module='calisthenics')
    db.session.add(u); db.session.commit()
    r = client.post('/api/calisthenics/mini-session/generate',
                    json={'type': 'stretch'}, headers=_h(app, u.id))
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'PROFILE_REQUIRED'


def test_generate_mini_requires_auth(app, client):
    r = client.post('/api/calisthenics/mini-session/generate', json={'type': 'stretch'})
    assert r.status_code == 401


@patch('app.modules.calisthenics.routes.generate_mini_session', return_value=SAMPLE_STRETCH)
def test_session_start_for_mini_workout_sets_kind(mock_gen, app, client, db):
    user, _, _ = _make_user(db, telegram_id=80115)
    gen = client.post('/api/calisthenics/mini-session/generate',
                      json={'type': 'stretch'}, headers=_h(app, user.id))
    workout_id = gen.get_json()['data']['workout_id']
    r = client.post('/api/calisthenics/session/start',
                    json={'workout_id': workout_id}, headers=_h(app, user.id))
    assert r.status_code == 200
    sid = r.get_json()['data']['session_id']
    from app.modules.training.models import WorkoutSession
    s = db.session.get(WorkoutSession, sid)
    assert s.kind == 'mini'
    assert s.module == 'calisthenics'


@patch('app.modules.calisthenics.routes.generate_mini_session', return_value=SAMPLE_STRETCH)
def test_session_start_rejects_other_user_mini_workout(mock_gen, app, client, db):
    user1, _, _ = _make_user(db, telegram_id=80120)
    user2, _, _ = _make_user(db, telegram_id=80121)
    # user1 creates a mini-workout
    gen = client.post('/api/calisthenics/mini-session/generate',
                      json={'type': 'stretch'}, headers=_h(app, user1.id))
    workout_id = gen.get_json()['data']['workout_id']
    # user2 tries to start a session against user1's mini-workout
    r = client.post('/api/calisthenics/session/start',
                    json={'workout_id': workout_id}, headers=_h(app, user2.id))
    assert r.status_code == 404
    assert r.get_json()['error']['code'] == 'WORKOUT_NOT_FOUND'
