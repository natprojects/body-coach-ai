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


from datetime import date, datetime, timedelta
from app.modules.training.models import (
    Program, ProgramWeek, Workout, Mesocycle, WorkoutSession, Exercise, WorkoutExercise, PlannedSet,
)


def _make_program(db, user, days_indices=(0,)):
    p = Program(user_id=user.id, name='Cali', periodization_type='hypertrophy',
                total_weeks=4, status='active', module='calisthenics')
    db.session.add(p)
    db.session.flush()
    m = Mesocycle(program_id=p.id, name='Block 1', order_index=0, weeks_count=1)
    db.session.add(m)
    db.session.flush()
    w = ProgramWeek(mesocycle_id=m.id, week_number=1)
    db.session.add(w)
    db.session.flush()
    workouts = []
    for i, dow in enumerate(days_indices):
        wo = Workout(program_week_id=w.id, day_of_week=dow,
                     name=f'Day {i}', order_index=i)
        db.session.add(wo)
        workouts.append(wo)
    db.session.commit()
    return p, workouts


def test_today_scheduled(app, client, db):
    user = _make_user(db, telegram_id=91001)
    today_dow = date.today().weekday()
    _make_program(db, user, days_indices=(today_dow,))
    r = client.get('/api/calisthenics/today', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data is not None
    assert data['name'] == 'Day 0'
    assert data.get('rest_day') is not True


def test_today_rest_day_when_all_done(app, client, db):
    user = _make_user(db, telegram_id=91002)
    today_dow = date.today().weekday()
    _, workouts = _make_program(db, user, days_indices=(today_dow,))
    # Mark workout completed via a session
    s = WorkoutSession(user_id=user.id, workout_id=workouts[0].id,
                       module='calisthenics', status='completed', date=date.today())
    db.session.add(s)
    db.session.commit()
    r = client.get('/api/calisthenics/today', headers=_h(app, user.id))
    data = r.get_json()['data']
    assert data['rest_day'] is True


def test_today_no_program(app, client, db):
    user = _make_user(db, telegram_id=91003)
    r = client.get('/api/calisthenics/today', headers=_h(app, user.id))
    assert r.status_code == 200
    assert r.get_json()['data'] is None


def test_today_requires_auth(app, client):
    r = client.get('/api/calisthenics/today')
    assert r.status_code == 401


def test_session_start_creates_session(app, client, db):
    user = _make_user(db, telegram_id=91004)
    today_dow = date.today().weekday()
    _, workouts = _make_program(db, user, days_indices=(today_dow,))
    r = client.post('/api/calisthenics/session/start',
                    json={'workout_id': workouts[0].id},
                    headers=_h(app, user.id))
    assert r.status_code == 200
    sid = r.get_json()['data']['session_id']
    s = db.session.get(WorkoutSession, sid)
    assert s.module == 'calisthenics'
    assert s.status == 'in_progress'


def test_session_start_rejects_other_module_workout(app, client, db):
    user = _make_user(db, telegram_id=91005)
    # Create gym workout
    gp = Program(user_id=user.id, name='Gym', periodization_type='hypertrophy',
                 total_weeks=4, status='active', module='gym')
    db.session.add(gp); db.session.flush()
    gm = Mesocycle(program_id=gp.id, name='m', order_index=0, weeks_count=1)
    db.session.add(gm); db.session.flush()
    gw = ProgramWeek(mesocycle_id=gm.id, week_number=1)
    db.session.add(gw); db.session.flush()
    gym_wo = Workout(program_week_id=gw.id, day_of_week=0, name='Gym', order_index=0)
    db.session.add(gym_wo); db.session.commit()

    r = client.post('/api/calisthenics/session/start',
                    json={'workout_id': gym_wo.id}, headers=_h(app, user.id))
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'MODULE_MISMATCH'


def test_session_start_404_for_other_user_workout(app, client, db):
    user1 = _make_user(db, telegram_id=91006)
    user2 = _make_user(db, telegram_id=91007)
    _, workouts = _make_program(db, user1, days_indices=(0,))
    r = client.post('/api/calisthenics/session/start',
                    json={'workout_id': workouts[0].id},
                    headers=_h(app, user2.id))
    assert r.status_code == 404


def test_session_start_requires_auth(app, client):
    r = client.post('/api/calisthenics/session/start', json={'workout_id': 1})
    assert r.status_code == 401


from app.modules.training.models import (
    WorkoutExercise, PlannedSet, LoggedExercise, LoggedSet,
)


def _make_program_with_full_workout(db, user, today_dow):
    p, [wo] = _make_program(db, user, days_indices=(today_dow,))
    ex = Exercise.query.filter_by(module='calisthenics', name='full pushup').first()
    we = WorkoutExercise(workout_id=wo.id, exercise_id=ex.id, order_index=0,
                         tempo='3-1-2-0', is_mandatory=True)
    db.session.add(we); db.session.flush()
    for n in (1, 2, 3):
        ps = PlannedSet(workout_exercise_id=we.id, set_number=n,
                        target_reps='8-12', target_rpe=8.0, rest_seconds=90,
                        is_amrap=(n == 3))
        db.session.add(ps)
    db.session.commit()
    return p, wo, we


def _start_session(db, user, workout):
    s = WorkoutSession(user_id=user.id, workout_id=workout.id,
                       module='calisthenics', status='in_progress',
                       date=date.today())
    db.session.add(s); db.session.commit()
    return s


def test_log_set_records_reps(app, client, db):
    user = _make_user(db, telegram_id=92001)
    today_dow = date.today().weekday()
    _, wo, we = _make_program_with_full_workout(db, user, today_dow)
    s = _start_session(db, user, wo)
    r = client.post(f'/api/calisthenics/session/{s.id}/log-set',
                    json={'workout_exercise_id': we.id, 'set_number': 1,
                          'actual_reps': 10, 'actual_seconds': None},
                    headers=_h(app, user.id))
    assert r.status_code == 200
    logs = LoggedSet.query.all()
    assert len(logs) == 1
    assert logs[0].actual_reps == 10


def test_log_set_records_seconds(app, client, db):
    user = _make_user(db, telegram_id=92002)
    today_dow = date.today().weekday()
    _, wo, _we = _make_program_with_full_workout(db, user, today_dow)
    plank_ex = Exercise.query.filter_by(module='calisthenics', name='forearm plank').first()
    we_p = WorkoutExercise(workout_id=wo.id, exercise_id=plank_ex.id, order_index=1)
    db.session.add(we_p); db.session.flush()
    ps = PlannedSet(workout_exercise_id=we_p.id, set_number=1, target_seconds=30, is_amrap=False)
    db.session.add(ps); db.session.commit()
    s = _start_session(db, user, wo)
    r = client.post(f'/api/calisthenics/session/{s.id}/log-set',
                    json={'workout_exercise_id': we_p.id, 'set_number': 1,
                          'actual_reps': None, 'actual_seconds': 35},
                    headers=_h(app, user.id))
    assert r.status_code == 200
    log = LoggedSet.query.order_by(LoggedSet.id.desc()).first()
    assert log.actual_seconds == 35


def test_log_set_upsert(app, client, db):
    """Same set logged twice — second value overwrites first."""
    user = _make_user(db, telegram_id=92003)
    today_dow = date.today().weekday()
    _, wo, we = _make_program_with_full_workout(db, user, today_dow)
    s = _start_session(db, user, wo)
    client.post(f'/api/calisthenics/session/{s.id}/log-set',
                json={'workout_exercise_id': we.id, 'set_number': 1, 'actual_reps': 8},
                headers=_h(app, user.id))
    client.post(f'/api/calisthenics/session/{s.id}/log-set',
                json={'workout_exercise_id': we.id, 'set_number': 1, 'actual_reps': 12},
                headers=_h(app, user.id))
    logs = LoggedSet.query.all()
    assert len(logs) == 1
    assert logs[0].actual_reps == 12


def test_log_set_404_other_user_session(app, client, db):
    user1 = _make_user(db, telegram_id=92004)
    user2 = _make_user(db, telegram_id=92005)
    today_dow = date.today().weekday()
    _, wo, we = _make_program_with_full_workout(db, user1, today_dow)
    s = _start_session(db, user1, wo)
    r = client.post(f'/api/calisthenics/session/{s.id}/log-set',
                    json={'workout_exercise_id': we.id, 'set_number': 1, 'actual_reps': 10},
                    headers=_h(app, user2.id))
    assert r.status_code == 404


def test_complete_marks_session(app, client, db):
    user = _make_user(db, telegram_id=92006)
    today_dow = date.today().weekday()
    _, wo, _we = _make_program_with_full_workout(db, user, today_dow)
    s = _start_session(db, user, wo)
    r = client.post(f'/api/calisthenics/session/{s.id}/complete',
                    json={}, headers=_h(app, user.id))
    assert r.status_code == 200
    db.session.refresh(s)
    assert s.status == 'completed'
    data = r.get_json()['data']
    assert 'level_up_suggestions' in data
    assert data['level_up_suggestions'] == []  # Task 8 will add real suggestions


def test_complete_404_for_gym_session(app, client, db):
    user = _make_user(db, telegram_id=92007)
    today_dow = date.today().weekday()
    _, wo, _we = _make_program_with_full_workout(db, user, today_dow)
    s = WorkoutSession(user_id=user.id, workout_id=wo.id, module='gym',
                       status='in_progress', date=date.today())
    db.session.add(s); db.session.commit()
    r = client.post(f'/api/calisthenics/session/{s.id}/complete',
                    json={}, headers=_h(app, user.id))
    assert r.status_code == 404


def test_log_set_requires_auth(app, client):
    r = client.post('/api/calisthenics/session/1/log-set', json={})
    assert r.status_code == 401


def test_complete_requires_auth(app, client):
    r = client.post('/api/calisthenics/session/1/complete', json={})
    assert r.status_code == 401


@patch('app.modules.calisthenics.routes.generate_calisthenics_program', return_value=SAMPLE)
def test_regenerate_archives_old_creates_new(mock_gen, app, client, db):
    user = _make_user(db, telegram_id=94001)
    r1 = client.post('/api/calisthenics/program/generate', headers=_h(app, user.id))
    p1_id = r1.get_json()['data']['id']

    r2 = client.post(f'/api/calisthenics/program/{p1_id}/regenerate', headers=_h(app, user.id))
    assert r2.status_code == 200
    p2_id = r2.get_json()['data']['id']
    assert p2_id != p1_id

    p1 = db.session.get(Program, p1_id)
    assert p1.status == 'completed'
    p2 = db.session.get(Program, p2_id)
    assert p2.status == 'active'


def test_regenerate_404_for_other_user_program(app, client, db):
    user1 = _make_user(db, telegram_id=94002)
    user2 = _make_user(db, telegram_id=94003)
    p = Program(user_id=user1.id, name='C', periodization_type='hypertrophy',
                total_weeks=4, status='active', module='calisthenics')
    db.session.add(p); db.session.commit()
    r = client.post(f'/api/calisthenics/program/{p.id}/regenerate', headers=_h(app, user2.id))
    assert r.status_code == 404


def test_regenerate_requires_assessment(app, client, db):
    user = _make_user(db, telegram_id=94004, with_assessment=False)
    p = Program(user_id=user.id, name='C', periodization_type='hypertrophy',
                total_weeks=4, status='active', module='calisthenics')
    db.session.add(p); db.session.commit()
    r = client.post(f'/api/calisthenics/program/{p.id}/regenerate', headers=_h(app, user.id))
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'ASSESSMENT_REQUIRED'


def test_regenerate_requires_auth(app, client):
    r = client.post('/api/calisthenics/program/1/regenerate')
    assert r.status_code == 401


@patch('app.modules.calisthenics.routes.generate_calisthenics_program', return_value=SAMPLE)
def test_regenerate_updates_days_per_week(mock_gen, app, client, db):
    user = _make_user(db, telegram_id=94010)
    r1 = client.post('/api/calisthenics/program/generate', headers=_h(app, user.id))
    p1_id = r1.get_json()['data']['id']

    r2 = client.post(f'/api/calisthenics/program/{p1_id}/regenerate',
                     json={'days_per_week': 5, 'optional_target_per_week': 2},
                     headers=_h(app, user.id))
    assert r2.status_code == 200

    profile = CalisthenicsProfile.query.filter_by(user_id=user.id).first()
    assert profile.days_per_week == 5
    assert profile.optional_target_per_week == 2


@patch('app.modules.calisthenics.routes.generate_calisthenics_program', return_value=SAMPLE)
def test_regenerate_invalid_days(mock_gen, app, client, db):
    user = _make_user(db, telegram_id=94011)
    r1 = client.post('/api/calisthenics/program/generate', headers=_h(app, user.id))
    p1_id = r1.get_json()['data']['id']
    r2 = client.post(f'/api/calisthenics/program/{p1_id}/regenerate',
                     json={'days_per_week': 9},
                     headers=_h(app, user.id))
    assert r2.status_code == 400
    assert r2.get_json()['error']['code'] == 'INVALID_FIELD'


@patch('app.modules.calisthenics.routes.generate_calisthenics_program', return_value=SAMPLE)
def test_regenerate_works_without_params(mock_gen, app, client, db):
    user = _make_user(db, telegram_id=94012)
    r1 = client.post('/api/calisthenics/program/generate', headers=_h(app, user.id))
    p1_id = r1.get_json()['data']['id']
    profile_before = CalisthenicsProfile.query.filter_by(user_id=user.id).first()
    days_before = profile_before.days_per_week

    r2 = client.post(f'/api/calisthenics/program/{p1_id}/regenerate', json={},
                     headers=_h(app, user.id))
    assert r2.status_code == 200
    profile_after = CalisthenicsProfile.query.filter_by(user_id=user.id).first()
    assert profile_after.days_per_week == days_before
