# tests/training/test_cycle.py
from datetime import date, datetime, timedelta
import pytest
from unittest.mock import MagicMock
from app.core.models import DailyCheckin, User
from app.core.auth import create_jwt
from app.modules.training.models import Exercise, ExerciseRecommendation


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


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


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


def _make_rec(db, user_id, exercise_name, weight, muscle_group='Chest'):
    ex = Exercise(name=exercise_name, muscle_group=muscle_group)
    db.session.add(ex)
    db.session.flush()
    rec = ExerciseRecommendation(
        user_id=user_id, exercise_id=ex.id,
        recommendation_type='maintain',
        recommended_weight_kg=weight,
        recommended_reps_min=8, recommended_reps_max=10,
        reason_text='test',
    )
    db.session.add(rec)
    db.session.commit()
    return rec


def test_luteal_applies_weight_modifier(app, db, mock_anthropic):
    """Luteal phase: weights reduced by 10%."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=18))
    _make_rec(db, user.id, 'Bench Press', 60.0)
    mock_anthropic.messages.create.return_value = MagicMock(
        content=[MagicMock(text='Спробуй дамбелі 22kg × 10.')]
    )
    from app.modules.training.cycle import get_cycle_adaptations
    adaptations = get_cycle_adaptations(user.id, 'luteal', 0.9)
    assert len(adaptations) == 1
    assert adaptations[0]['original_weight'] == 60.0
    assert adaptations[0]['adapted_weight'] == 55.0  # 60 * 0.9 = 54 → rounds to 55 (nearest 2.5)


def test_follicular_no_adaptations(app, db):
    """Follicular phase modifier=1.0: no weight changes, no adaptations returned."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=7))
    _make_rec(db, user.id, 'Squat', 80.0)
    from app.modules.training.cycle import get_cycle_adaptations
    adaptations = get_cycle_adaptations(user.id, 'follicular', 1.0)
    assert adaptations == []


def test_ai_note_for_compound_in_luteal(app, db, mock_anthropic):
    """Luteal + compound exercise → AI suggestion generated."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=18))
    _make_rec(db, user.id, 'Squat', 80.0, muscle_group='Legs')
    mock_anthropic.messages.create.return_value = MagicMock(
        content=[MagicMock(text='Спробуй goblet squat 32kg × 10.')]
    )
    from app.modules.training.cycle import get_cycle_adaptations
    adaptations = get_cycle_adaptations(user.id, 'luteal', 0.9)
    compound = [a for a in adaptations if 'Squat' in a['exercise_name']]
    assert len(compound) == 1
    assert compound[0]['ai_note'] == 'Спробуй goblet squat 32kg × 10.'
    mock_anthropic.messages.create.assert_called_once()


def test_ai_not_called_for_non_compound_in_luteal(app, db, mock_anthropic):
    """Luteal + isolation exercise (bicep curl) → no AI call."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=18))
    _make_rec(db, user.id, 'Bicep Curl', 15.0, muscle_group='Arms')
    from app.modules.training.cycle import get_cycle_adaptations
    adaptations = get_cycle_adaptations(user.id, 'luteal', 0.9)
    mock_anthropic.messages.create.assert_not_called()


def test_ai_failure_falls_back_gracefully(app, db, mock_anthropic):
    """If AI call throws, adaptation still returned with ai_note=None."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=18))
    _make_rec(db, user.id, 'Deadlift', 100.0, muscle_group='Back')
    mock_anthropic.messages.create.side_effect = Exception('API error')
    from app.modules.training.cycle import get_cycle_adaptations
    adaptations = get_cycle_adaptations(user.id, 'luteal', 0.9)
    deadlift = [a for a in adaptations if 'Deadlift' in a['exercise_name']]
    assert len(deadlift) == 1
    assert deadlift[0]['ai_note'] is None
    assert deadlift[0]['adapted_weight'] == 90.0  # 100 * 0.9


def test_ai_calls_capped_at_3(app, db, mock_anthropic):
    """AI is called at most 3 times even when there are more compound exercises in luteal."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=18))
    _make_rec(db, user.id, 'Squat', 80.0, muscle_group='Legs')
    _make_rec(db, user.id, 'Deadlift', 100.0, muscle_group='Back')
    _make_rec(db, user.id, 'Bench Press', 60.0, muscle_group='Chest')
    _make_rec(db, user.id, 'Overhead Press', 40.0, muscle_group='Shoulders')
    mock_anthropic.messages.create.return_value = MagicMock(
        content=[MagicMock(text='Спробуй варіацію.')]
    )
    from app.modules.training.cycle import get_cycle_adaptations
    adaptations = get_cycle_adaptations(user.id, 'luteal', 0.9)
    assert mock_anthropic.messages.create.call_count == 3


def test_ai_note_for_plyometric_in_ovulation(app, db, mock_anthropic):
    """Ovulation + plyometric exercise → AI suggestion generated, weight unchanged."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=13))  # day 14 = ovulation
    _make_rec(db, user.id, 'Box Jump', 0.0, muscle_group='Legs')  # bodyweight plyometric, weight=0
    # weight=0 is skipped by get_cycle_adaptations (original <= 0), so use a small weight
    _make_rec(db, user.id, 'Jump Squat', 20.0, muscle_group='Legs')
    mock_anthropic.messages.create.return_value = MagicMock(
        content=[MagicMock(text='Заміни на step-up 20kg × 12.')]
    )
    from app.modules.training.cycle import get_cycle_adaptations
    adaptations = get_cycle_adaptations(user.id, 'ovulation', 1.0)
    jump = [a for a in adaptations if 'Jump' in a['exercise_name']]
    assert len(jump) == 1
    assert jump[0]['original_weight'] == 20.0
    assert jump[0]['adapted_weight'] == 20.0  # ovulation modifier=1.0, no weight change
    assert jump[0]['ai_note'] == 'Заміни на step-up 20kg × 12.'
    mock_anthropic.messages.create.assert_called_once()
