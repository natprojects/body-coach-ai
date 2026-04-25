from datetime import datetime
from app.core.models import User
from app.core.auth import create_jwt
from app.modules.training.models import Program, Mesocycle, ProgramWeek, Workout


def _make_user(db, telegram_id=70001, active_module='gym'):
    u = User(
        telegram_id=telegram_id, name='Iso', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['floor'], onboarding_completed_at=datetime.utcnow(),
        active_module=active_module,
    )
    db.session.add(u)
    db.session.commit()
    return u


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


def _make_program(db, user, module='gym'):
    p = Program(
        user_id=user.id, name=f'{module} Program', periodization_type='hypertrophy',
        total_weeks=4, status='active', module=module,
    )
    db.session.add(p)
    db.session.flush()
    m = Mesocycle(program_id=p.id, name='Block 1', order_index=0, weeks_count=1)
    db.session.add(m)
    db.session.flush()
    w = ProgramWeek(mesocycle_id=m.id, week_number=1)
    db.session.add(w)
    db.session.flush()
    workout = Workout(program_week_id=w.id, day_of_week=0, name=f'{module} Day 1', order_index=0)
    db.session.add(workout)
    db.session.commit()
    return p


def test_gym_user_sees_only_gym_program(app, client, db):
    user = _make_user(db, telegram_id=70001, active_module='gym')
    _make_program(db, user, module='gym')
    _make_program(db, user, module='calisthenics')

    r = client.get('/api/training/program/current', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data is not None
    assert data['name'] == 'gym Program'


def test_calisthenics_user_does_not_see_gym_program(app, client, db):
    user = _make_user(db, telegram_id=70002, active_module='calisthenics')
    _make_program(db, user, module='gym')

    r = client.get('/api/training/program/current', headers=_h(app, user.id))
    assert r.status_code == 200
    assert r.get_json()['data'] is None
