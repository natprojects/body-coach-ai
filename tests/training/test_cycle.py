# tests/training/test_cycle.py
from datetime import date, datetime, timedelta
import pytest
from app.core.models import DailyCheckin, User


def _make_user_with_cycle(db, last_period_date=None, cycle_length_days=28,
                           menstrual_tracking=True):
    u = User(
        telegram_id=90001, name='CycleTest', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='intermediate', training_days_per_week=3, session_duration_min=60,
        equipment=['full_gym'], onboarding_completed_at=datetime.utcnow(),
        menstrual_tracking=menstrual_tracking,
        cycle_length_days=cycle_length_days,
        last_period_date=last_period_date,
    )
    db.session.add(u)
    db.session.commit()
    return u


def test_luteal_phase_detected(app, db):
    """Day 19 of 28-day cycle → luteal, modifier 0.9, show_card True."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=18))
    from app.modules.training.cycle import get_cycle_phase
    result = get_cycle_phase(user.id)
    assert result['phase'] == 'luteal'
    assert result['cycle_day'] == 19
    assert result['modifier'] == 0.9
    assert result['show_card'] is True
    assert result['pr_allowed'] is False


def test_follicular_phase_no_card(app, db):
    """Day 8 → follicular, show_card False (badge only)."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=7))
    from app.modules.training.cycle import get_cycle_phase
    result = get_cycle_phase(user.id)
    assert result['phase'] == 'follicular'
    assert result['show_card'] is False
    assert result['modifier'] == 1.0
    assert result['pr_allowed'] is True


def test_ovulation_shows_card_with_warnings(app, db):
    """Day 14 → ovulation, show_card True, has plyometrics warning."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=13))
    from app.modules.training.cycle import get_cycle_phase
    result = get_cycle_phase(user.id)
    assert result['phase'] == 'ovulation'
    assert result['show_card'] is True
    assert len(result['warnings']) > 0


def test_menstrual_card_only_with_low_energy(app, db):
    """Day 3 menstrual: no card without checkin, card with energy < 5."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=2))
    from app.modules.training.cycle import get_cycle_phase
    # No checkin → no card
    result = get_cycle_phase(user.id)
    assert result['phase'] == 'menstrual'
    assert result['show_card'] is False
    # Low energy checkin → show card
    db.session.add(DailyCheckin(user_id=user.id, date=date.today(), energy_level=3))
    db.session.commit()
    result2 = get_cycle_phase(user.id)
    assert result2['show_card'] is True


def test_manual_cycle_day_override(app, db):
    """DailyCheckin.cycle_day overrides calculated day."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=5))
    db.session.add(DailyCheckin(user_id=user.id, date=date.today(), cycle_day=20))
    db.session.commit()
    from app.modules.training.cycle import get_cycle_phase
    result = get_cycle_phase(user.id)
    assert result['cycle_day'] == 20
    assert result['phase'] == 'luteal'


def test_no_tracking_returns_no_card(app, db):
    """menstrual_tracking=False → show_card False."""
    user = _make_user_with_cycle(db, menstrual_tracking=False,
                                  last_period_date=date.today() - timedelta(days=18))
    from app.modules.training.cycle import get_cycle_phase
    result = get_cycle_phase(user.id)
    assert result.get('show_card') is False


def test_no_period_date_returns_no_card(app, db):
    """last_period_date=None → show_card False."""
    user = _make_user_with_cycle(db, last_period_date=None)
    from app.modules.training.cycle import get_cycle_phase
    result = get_cycle_phase(user.id)
    assert result.get('show_card') is False


def test_cycle_wraps_correctly(app, db):
    """Day 29 of 28-day cycle → wraps to day 1 (menstrual)."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=28),
                                  cycle_length_days=28)
    from app.modules.training.cycle import get_cycle_phase
    result = get_cycle_phase(user.id)
    assert result['cycle_day'] == 1
    assert result['phase'] == 'menstrual'


def test_is_plyometric_detection():
    """Keywords like 'jump', 'burpee', 'стрибок' are detected as plyometric."""
    from app.modules.training.cycle import _is_plyometric
    assert _is_plyometric('Box Jump') is True
    assert _is_plyometric('Burpee') is True
    assert _is_plyometric('стрибок') is True
    assert _is_plyometric('Bench Press') is False
    assert _is_plyometric('Squat') is False


def test_is_compound_detection():
    """Keywords like 'squat', 'deadlift', 'bench press' are detected as compound."""
    from app.modules.training.cycle import _is_compound
    assert _is_compound('Back Squat') is True
    assert _is_compound('Romanian Deadlift') is True
    assert _is_compound('Bench Press') is True
    assert _is_compound('Bicep Curl') is False
    assert _is_compound('Leg Extension') is False


from app.core.auth import create_jwt


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


def test_cycle_phase_endpoint_returns_data(client, app, db):
    """GET /api/training/cycle/phase returns phase data for a user with tracking."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=18))
    r = client.get('/api/training/cycle/phase', headers=_h(app, user.id))
    data = r.get_json()
    assert data['success'] is True
    assert data['data']['phase'] == 'luteal'
    assert data['data']['show_card'] is True
    assert 'adaptations' in data['data']


def test_cycle_phase_endpoint_no_tracking(client, app, db):
    """GET /api/training/cycle/phase returns show_card=False when tracking disabled."""
    user = _make_user_with_cycle(db, menstrual_tracking=False,
                                  last_period_date=date.today() - timedelta(days=18))
    r = client.get('/api/training/cycle/phase', headers=_h(app, user.id))
    data = r.get_json()
    assert data['success'] is True
    assert data['data']['show_card'] is False


def test_session_start_saves_cycle_fields(client, app, db):
    """POST /api/training/session/start saves cycle_phase and cycle_adapted."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=18))
    r = client.post(
        '/api/training/session/start',
        json={'cycle_phase': 'luteal', 'cycle_adapted': True},
        headers=_h(app, user.id),
    )
    data = r.get_json()
    assert data['success'] is True
    from app.modules.training.models import WorkoutSession
    session = WorkoutSession.query.get(data['data']['session_id'])
    assert session.cycle_phase == 'luteal'
    assert session.cycle_adapted is True
