# Menstrual Cycle Adaptation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a pre-workout cycle phase card with weight adaptations and AI exercise suggestions, based on the user's menstrual cycle phase.

**Architecture:** New `app/modules/training/cycle.py` handles all phase calculation and adaptation logic. A new `GET /api/training/cycle/phase` endpoint serves phase data. Frontend intercepts "Почати тренування" tap, shows an overlay, and applies adaptations to displayed weights.

**Tech Stack:** Python/Flask/SQLAlchemy, Anthropic haiku for AI suggestions, existing `complete()` function in `app/core/ai.py`.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `app/modules/training/models.py` | Add `cycle_phase`, `cycle_adapted` to `WorkoutSession` |
| Create | `migrations/versions/<hash>_cycle_fields.py` | DB migration for new columns |
| Create | `app/modules/training/cycle.py` | Phase calc, `get_cycle_phase()`, `get_cycle_adaptations()`, AI suggestions |
| Modify | `app/modules/training/routes.py` | New `GET /api/training/cycle/phase` endpoint + modified `session_start` |
| Create | `tests/training/test_cycle.py` | Tests for cycle logic and endpoint |
| Modify | `app/templates/index.html` | Phase badge, cycle overlay, adapted targets, checkin field |

---

## Task 1: DB Migration — add cycle_phase and cycle_adapted to WorkoutSession

**Files:**
- Modify: `app/modules/training/models.py`
- Create: migration file via `flask db migrate`

- [ ] **Step 1: Add fields to WorkoutSession in `app/modules/training/models.py`**

Find the `WorkoutSession` class and add two columns after `ai_feedback`:

```python
class WorkoutSession(db.Model):
    __tablename__ = 'workout_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    workout_id = db.Column(db.Integer, db.ForeignKey('workouts.id'), nullable=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(20), default='in_progress')
    notes = db.Column(db.Text)
    ai_feedback = db.Column(db.Text)
    last_exercise_id = db.Column(db.Integer, db.ForeignKey('exercises.id'), nullable=True)
    cycle_phase = db.Column(db.String(20), nullable=True)
    cycle_adapted = db.Column(db.Boolean, default=False)

    logged_exercises = db.relationship('LoggedExercise', backref='session',
                                       order_by='LoggedExercise.order_index',
                                       cascade='all, delete-orphan')
```

- [ ] **Step 2: Generate migration**

```bash
cd /Users/natalie/body-coach-ai
flask db migrate -m "add cycle fields to workout sessions"
```

Expected output: `Generating .../migrations/versions/XXXX_add_cycle_fields_to_workout_sessions.py`

- [ ] **Step 3: Fix the generated migration**

Open the generated migration file. Remove any `batch_op.create_foreign_key(...)` lines if present (SQLite FK issue). The upgrade function should only contain `add_column` calls:

```python
def upgrade():
    op.add_column('workout_sessions', sa.Column('cycle_phase', sa.String(length=20), nullable=True))
    op.add_column('workout_sessions', sa.Column('cycle_adapted', sa.Boolean(), nullable=True))
```

If the generated file already looks like that — leave it as is. The downgrade should be:

```python
def downgrade():
    op.drop_column('workout_sessions', 'cycle_adapted')
    op.drop_column('workout_sessions', 'cycle_phase')
```

- [ ] **Step 4: Apply migration**

```bash
flask db upgrade
```

Expected: `Running upgrade ... -> XXXX`

- [ ] **Step 5: Run tests to verify nothing broke**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -5
```

Expected: `68 passed`

- [ ] **Step 6: Commit**

```bash
git add app/modules/training/models.py migrations/versions/
git commit -m "feat: add cycle_phase and cycle_adapted to WorkoutSession"
```

---

## Task 2: `cycle.py` — phase calculation and `get_cycle_phase()`

**Files:**
- Create: `app/modules/training/cycle.py`
- Create: `tests/training/test_cycle.py`

- [ ] **Step 1: Write failing tests in `tests/training/test_cycle.py`**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/training/test_cycle.py -v 2>&1 | tail -10
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.modules.training.cycle'`

- [ ] **Step 3: Create `app/modules/training/cycle.py`**

```python
# app/modules/training/cycle.py
from app.core.ai import complete

PHASE_DATA = {
    'menstrual': {
        'title': 'Менструальна фаза',
        'description': 'Тренуйся за самопочуттям. Якщо енергія низька — не форсуй.',
        'modifier': 1.0,
        'pr_allowed': True,
        'warnings': [],
    },
    'follicular': {
        'title': 'Фолікулярна фаза',
        'description': '💪 Найкращий час для важких тренувань і нових рекордів.',
        'modifier': 1.0,
        'pr_allowed': True,
        'warnings': [],
    },
    'ovulation': {
        'title': 'Овуляція',
        'description': "Підвищена лаксичність зв'язок. Зроби додаткову розминку суглобів, уникай стрибків.",
        'modifier': 1.0,
        'pr_allowed': True,
        'warnings': ["Уникай плайометрики (стрибки, бурпі) — підвищений ризик травми зв'язок."],
    },
    'luteal': {
        'title': 'Лютеальна фаза',
        'description': 'Знижена працездатність — це нормально. −10% ваги, без рекордів. Фокус на техніку.',
        'modifier': 0.9,
        'pr_allowed': False,
        'warnings': [],
    },
}

_PLYOMETRIC_KW = ('jump', 'box jump', 'burpee', 'hop', 'bound', 'стрибок', 'бурпі', 'lunge jump')
_COMPOUND_KW = ('squat', 'deadlift', 'bench press', 'overhead press', 'military press',
                'rdl', 'romanian', 'row', 'присід', 'мертва', 'жим')


def _is_plyometric(name: str) -> bool:
    n = name.lower()
    return any(kw in n for kw in _PLYOMETRIC_KW)


def _is_compound(name: str) -> bool:
    n = name.lower()
    return any(kw in n for kw in _COMPOUND_KW)


def _phase_for_day(cycle_day: int) -> str:
    if cycle_day <= 5:
        return 'menstrual'
    if cycle_day <= 11:
        return 'follicular'
    if cycle_day <= 16:
        return 'ovulation'
    return 'luteal'


def get_cycle_phase(user_id: int) -> dict:
    """Return cycle phase info for the user.
    Returns {'show_card': False} if cycle tracking is not enabled or data is missing."""
    from datetime import date
    from app.core.models import DailyCheckin, User
    from app.extensions import db

    user = db.session.get(User, user_id)
    if not user or not user.menstrual_tracking or not user.last_period_date:
        return {'show_card': False}

    today_checkin = DailyCheckin.query.filter_by(
        user_id=user_id, date=date.today()
    ).first()

    if today_checkin and today_checkin.cycle_day:
        cycle_day = today_checkin.cycle_day
    else:
        cycle_length = user.cycle_length_days or 28
        days_since = (date.today() - user.last_period_date).days
        cycle_day = (days_since % cycle_length) + 1

    phase = _phase_for_day(cycle_day)
    info = dict(PHASE_DATA[phase])
    info['warnings'] = list(info['warnings'])

    # Determine whether to show the pre-workout card
    if phase == 'follicular':
        show_card = False
    elif phase == 'menstrual':
        energy = getattr(today_checkin, 'energy_level', None) if today_checkin else None
        show_card = bool(energy and energy < 5)
    else:
        show_card = True  # ovulation and luteal always show card

    return {
        'show_card': show_card,
        'phase': phase,
        'cycle_day': cycle_day,
        'modifier': info['modifier'],
        'phase_title': info['title'],
        'phase_description': info['description'],
        'warnings': info['warnings'],
        'pr_allowed': info['pr_allowed'],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/training/test_cycle.py -v 2>&1 | tail -15
```

Expected: all 8 tests PASS

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add app/modules/training/cycle.py tests/training/test_cycle.py
git commit -m "feat: cycle phase calculation — get_cycle_phase() with 4-phase logic"
```

---

## Task 3: Endpoint + modified session_start

**Files:**
- Modify: `app/modules/training/routes.py`
- Modify: `tests/training/test_cycle.py`

- [ ] **Step 1: Add failing tests for the endpoint**

Append to `tests/training/test_cycle.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3 -m pytest tests/training/test_cycle.py::test_cycle_phase_endpoint_returns_data tests/training/test_cycle.py::test_cycle_phase_endpoint_no_tracking tests/training/test_cycle.py::test_session_start_saves_cycle_fields -v 2>&1 | tail -10
```

Expected: FAIL with 404 (endpoint doesn't exist yet)

- [ ] **Step 3: Add `GET /api/training/cycle/phase` endpoint to `app/modules/training/routes.py`**

Find the last `@bp.route` decorator in the file and add AFTER it:

```python
@bp.route('/training/cycle/phase', methods=['GET'])
@require_auth
def cycle_phase_check():
    from app.modules.training.cycle import get_cycle_phase, get_cycle_adaptations
    phase_data = get_cycle_phase(g.user_id)
    if not phase_data.get('phase'):
        # tracking disabled or no data
        return jsonify({'success': True, 'data': phase_data})
    adaptations = []
    if phase_data.get('show_card') and phase_data['phase'] in ('ovulation', 'luteal', 'menstrual'):
        adaptations = get_cycle_adaptations(
            g.user_id,
            phase_data['phase'],
            phase_data['modifier'],
        )
    phase_data['adaptations'] = adaptations
    return jsonify({'success': True, 'data': phase_data})
```

Note: `get_cycle_adaptations` doesn't exist yet — it will be added in Task 4. For now, import it but it will be a stub.

- [ ] **Step 4: Add `get_cycle_adaptations` stub to `app/modules/training/cycle.py`**

Append to `cycle.py`:

```python
def get_cycle_adaptations(user_id: int, phase: str, modifier: float) -> list:
    """Return weight adaptations for today's recommendations. Stub — AI added in Task 4."""
    from app.modules.training.models import ExerciseRecommendation
    from sqlalchemy import func
    from app.extensions import db

    # Latest recommendation per exercise for this user
    latest_subq = (
        db.session.query(
            ExerciseRecommendation.exercise_id,
            func.max(ExerciseRecommendation.created_at).label('max_created'),
        )
        .filter_by(user_id=user_id)
        .group_by(ExerciseRecommendation.exercise_id)
        .subquery()
    )
    recs = (
        ExerciseRecommendation.query
        .join(latest_subq, db.and_(
            ExerciseRecommendation.exercise_id == latest_subq.c.exercise_id,
            ExerciseRecommendation.created_at == latest_subq.c.max_created,
        ))
        .filter(ExerciseRecommendation.user_id == user_id)
        .limit(10)
        .all()
    )

    adaptations = []
    for rec in recs:
        original = rec.recommended_weight_kg or 0
        if original <= 0:
            continue
        adapted = round(original * modifier / 2.5) * 2.5
        if adapted != original:
            adaptations.append({
                'exercise_name': rec.exercise.name,
                'exercise_id': rec.exercise_id,
                'original_weight': original,
                'adapted_weight': adapted,
                'ai_note': None,
            })
    return adaptations
```

- [ ] **Step 5: Modify `session_start` in `app/modules/training/routes.py`**

Find the existing `session_start` function and replace it:

```python
@bp.route('/training/session/start', methods=['POST'])
@require_auth
def session_start():
    data = request.json or {}
    session = WorkoutSession(
        user_id=g.user_id,
        workout_id=data.get('workout_id'),
        date=date.today(),
        status='in_progress',
        cycle_phase=data.get('cycle_phase'),
        cycle_adapted=bool(data.get('cycle_adapted', False)),
    )
    db.session.add(session)
    db.session.commit()
    return jsonify({'success': True, 'data': {'session_id': session.id}})
```

- [ ] **Step 6: Run tests**

```bash
python3 -m pytest tests/training/test_cycle.py -v 2>&1 | tail -15
```

Expected: all 11 tests PASS

- [ ] **Step 7: Run full suite**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -5
```

- [ ] **Step 8: Commit**

```bash
git add app/modules/training/routes.py app/modules/training/cycle.py tests/training/test_cycle.py
git commit -m "feat: GET /api/training/cycle/phase endpoint + session_start cycle fields"
```

---

## Task 4: AI suggestions in `get_cycle_adaptations()`

**Files:**
- Modify: `app/modules/training/cycle.py`
- Modify: `tests/training/test_cycle.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/training/test_cycle.py`:

```python
from unittest.mock import MagicMock, patch
from app.modules.training.models import Exercise, ExerciseRecommendation
from datetime import datetime as dt


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


def test_luteal_applies_weight_modifier(app, db):
    """Luteal phase: weights reduced by 10%."""
    user = _make_user_with_cycle(db, last_period_date=date.today() - timedelta(days=18))
    _make_rec(db, user.id, 'Bench Press', 60.0)
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
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3 -m pytest tests/training/test_cycle.py::test_luteal_applies_weight_modifier tests/training/test_cycle.py::test_ai_note_for_compound_in_luteal -v 2>&1 | tail -10
```

Expected: FAIL

- [ ] **Step 3: Replace `get_cycle_adaptations` stub in `cycle.py` with full implementation**

Find and replace the entire `get_cycle_adaptations` function:

```python
def get_cycle_adaptations(user_id: int, phase: str, modifier: float) -> list:
    """Return weight adaptations for today's recommendations, with AI notes for key exercises."""
    from app.modules.training.models import ExerciseRecommendation
    from sqlalchemy import func
    from app.extensions import db

    # Latest recommendation per exercise for this user
    latest_subq = (
        db.session.query(
            ExerciseRecommendation.exercise_id,
            func.max(ExerciseRecommendation.created_at).label('max_created'),
        )
        .filter_by(user_id=user_id)
        .group_by(ExerciseRecommendation.exercise_id)
        .subquery()
    )
    recs = (
        ExerciseRecommendation.query
        .join(latest_subq, db.and_(
            ExerciseRecommendation.exercise_id == latest_subq.c.exercise_id,
            ExerciseRecommendation.created_at == latest_subq.c.max_created,
        ))
        .filter(ExerciseRecommendation.user_id == user_id)
        .limit(10)
        .all()
    )

    adaptations = []
    ai_calls = 0

    for rec in recs:
        original = rec.recommended_weight_kg or 0
        if original <= 0:
            continue

        adapted = round(original * modifier / 2.5) * 2.5
        ai_note = None

        needs_ai = (
            (phase == 'ovulation' and _is_plyometric(rec.exercise.name)) or
            (phase == 'luteal' and _is_compound(rec.exercise.name))
        )
        if needs_ai and ai_calls < 3:
            try:
                ai_note = _ai_suggestion(rec.exercise.name, original, phase)
                ai_calls += 1
            except Exception:
                pass

        if adapted != original or ai_note:
            adaptations.append({
                'exercise_name': rec.exercise.name,
                'exercise_id': rec.exercise_id,
                'original_weight': original,
                'adapted_weight': adapted,
                'ai_note': ai_note,
            })

    return adaptations


def _ai_suggestion(exercise_name: str, weight_kg: float, phase: str) -> str:
    if phase == 'ovulation':
        system = (
            'You are a strength coach. Reply in Ukrainian only. '
            'Suggest ONE lower-impact alternative to this plyometric exercise to protect joints '
            'during ovulation (high estrogen = ligament laxity). '
            'Be specific: name the alternative, give weight and reps. Max 15 words.'
        )
    else:  # luteal
        system = (
            'You are a strength coach. Reply in Ukrainian only. '
            'Suggest ONE easier variation of this compound exercise for the luteal phase '
            '(lower energy week, −10% performance normal). '
            'Be specific: name the variation, give weight and reps. Max 15 words.'
        )
    return complete(
        system,
        f'Exercise: {exercise_name}, {weight_kg}kg.',
        max_tokens=50,
        model='claude-haiku-4-5-20251001',
    ).strip()
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/training/test_cycle.py -v 2>&1 | tail -20
```

Expected: all 16 tests PASS

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add app/modules/training/cycle.py tests/training/test_cycle.py
git commit -m "feat: cycle adaptations with AI suggestions for compound/plyometric exercises"
```

---

## Task 5: Frontend — badge, overlay, adapted targets, checkin field

**Files:**
- Modify: `app/templates/index.html`

Before making any edits, read the following sections of `app/templates/index.html`:
1. Find `function startWorkout` — understand its current body
2. Find `function renderTrainTab` — understand where the train tab content is rendered
3. Find `function renderTodayTargets` — understand how today's targets are displayed
4. Find the daily checkin form/modal — look for `checkin` and `cycle_day`
5. Find `overlay-feedback` div — to understand overlay HTML structure to copy
6. Find `S.sessionId` or `S =` to understand the state object

- [ ] **Step 1: Add cycle state to the state object `S`**

Find the state object initialization (look for `const S = {` or `let S = {`). Add two new fields:

```javascript
cyclePhase: null,      // phase data from GET /api/training/cycle/phase
cycleAdaptation: null, // { modifier, adaptations } when user chose "Adapt"
```

- [ ] **Step 2: Add the cycle overlay HTML**

Find `<div id="overlay-feedback"` and add a NEW overlay div AFTER it (using the same pattern):

```html
<div id="overlay-cycle" class="overlay" style="display:none">
  <div class="overlay-inner">
    <div id="cycle-card-content"></div>
    <div style="display:flex;gap:10px;margin-top:16px">
      <button class="btn btn-primary" style="flex:1" onclick="applyAndStartWorkout()">АДАПТУВАТИ</button>
      <button class="btn btn-secondary" style="flex:1" onclick="ignoreAndStartWorkout()">ІГНОРУВАТИ</button>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Add `.cycle-phase-badge` CSS**

Find the CSS section (inside `<style>`) and add before `</style>`:

```css
    .cycle-phase-badge { display:inline-block; font-size:12px; font-weight:600;
      padding:3px 10px; border-radius:12px; background:var(--card);
      border:1px solid var(--border); color:var(--muted); margin-bottom:12px; }
    .cycle-ai-note { background:#ff980018; border:1px solid #ff980044;
      border-radius:6px; padding:8px 10px; font-size:12px; color:#ff9800;
      margin-top:4px; line-height:1.4; }
```

- [ ] **Step 4: Add `renderCycleBadge()` function**

Add this function near other `render*` functions:

```javascript
function renderCycleBadge() {
  const el = document.getElementById('cycle-phase-badge');
  if (!el) return;
  if (!S.cyclePhase || !S.cyclePhase.phase) { el.style.display = 'none'; return; }
  const icons = { menstrual: '🩸', follicular: '💪', ovulation: '⚠️', luteal: '🌙' };
  const icon = icons[S.cyclePhase.phase] || '';
  el.style.display = '';
  el.textContent = `${icon} ${S.cyclePhase.phase_title} • день ${S.cyclePhase.cycle_day}`;
}
```

- [ ] **Step 5: Add `renderCycleCard()` function**

```javascript
function renderCycleCard() {
  const el = document.getElementById('cycle-card-content');
  if (!el || !S.cyclePhase) return;
  const p = S.cyclePhase;
  const icons = { menstrual: '🩸', follicular: '💪', ovulation: '⚠️', luteal: '🌙' };
  const icon = icons[p.phase] || '';
  const warningsHtml = p.warnings?.length
    ? `<div style="color:#ff9800;font-size:12px;margin-top:8px">${p.warnings.map(w => `⚠️ ${_esc(w)}`).join('<br>')}</div>`
    : '';
  const adaptationsHtml = p.adaptations?.length
    ? `<div style="margin-top:12px">
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;color:var(--muted);margin-bottom:6px">Адаптації</div>
        ${p.adaptations.map(a => `
          <div style="margin-bottom:6px">
            <span style="font-size:13px">${_esc(a.exercise_name)}</span>
            <span style="color:var(--muted);font-size:12px"> ${a.original_weight}kg → </span>
            <span style="color:#4caf50;font-weight:700;font-size:13px">${a.adapted_weight}kg</span>
            ${a.ai_note ? `<div class="cycle-ai-note">💡 ${_esc(a.ai_note)}</div>` : ''}
          </div>`).join('')}
       </div>`
    : '';
  el.innerHTML = `
    <div style="font-size:16px;font-weight:700;margin-bottom:4px">${icon} ${_esc(p.phase_title)} • день ${p.cycle_day}</div>
    <div style="font-size:13px;color:var(--muted);line-height:1.5">${_esc(p.phase_description)}</div>
    ${warningsHtml}
    ${adaptationsHtml}`;
}
```

- [ ] **Step 6: Modify `startWorkout()` to check cycle phase**

Find the existing `startWorkout` function. Read its current body. Wrap it into a new helper `_doStartWorkout()` and add cycle check:

```javascript
async function startWorkout() {
  // Check cycle phase — show card if applicable
  const cr = await api('GET', '/api/training/cycle/phase');
  if (cr.success) {
    S.cyclePhase = cr.data;
    renderCycleBadge();
    if (cr.data.show_card) {
      renderCycleCard();
      openOverlay('overlay-cycle');
      return;  // wait for user to tap Adapt or Ignore
    }
  }
  await _doStartWorkout(null);
}

async function applyAndStartWorkout() {
  closeOverlay('overlay-cycle');
  S.cycleAdaptation = {
    modifier: S.cyclePhase.modifier,
    adaptations: S.cyclePhase.adaptations || [],
  };
  await _doStartWorkout({ cycle_phase: S.cyclePhase.phase, cycle_adapted: true });
}

async function ignoreAndStartWorkout() {
  closeOverlay('overlay-cycle');
  S.cycleAdaptation = null;
  await _doStartWorkout({ cycle_phase: S.cyclePhase?.phase, cycle_adapted: false });
}
```

For `_doStartWorkout(cycleData)`: copy the existing body of `startWorkout()` into this new function, and add cycle fields to the session/start call body:

```javascript
async function _doStartWorkout(cycleData) {
  // [copy existing startWorkout body here — whatever it currently does to call session/start]
  // Modify the api('POST', '/api/training/session/start', ...) call to merge cycleData:
  const body = { workout_id: S.todayWorkout?.id };
  if (cycleData) Object.assign(body, cycleData);
  const r = await api('POST', '/api/training/session/start', body);
  // [rest of existing logic: set S.sessionId, renderTrainTab(), etc.]
}
```

**Important:** Read the existing `startWorkout()` function carefully before making this edit to preserve its exact behavior.

- [ ] **Step 7: Add cycle phase badge element to Train tab HTML**

Find the Train tab HTML container (look for `id="tab-train"` or similar). Add the badge element near the top, just before the workout/targets content:

```html
<div id="cycle-phase-badge" class="cycle-phase-badge" style="display:none"></div>
```

- [ ] **Step 8: Load cycle phase on Train tab open**

Find the function that loads the Train tab (likely `loadTrainTab()` or called when Train tab is selected). Add a cycle phase fetch:

```javascript
const cr = await api('GET', '/api/training/cycle/phase');
if (cr.success) {
  S.cyclePhase = cr.data;
  renderCycleBadge();
}
```

- [ ] **Step 9: Apply adaptation in target rendering**

Find `renderTodayTargets()` (or whatever function renders the workout targets/planned sets during a session). Where it displays `target_weight_kg` or `recommended_weight_kg`, wrap it with cycle modifier:

```javascript
// Instead of: const displayWeight = rec.recommended_weight_kg;
// Use:
const modifier = S.cycleAdaptation?.modifier || 1.0;
const displayWeight = Math.round((rec.recommended_weight_kg * modifier) / 2.5) * 2.5;
```

Also, if `S.cycleAdaptation?.adaptations` has an `ai_note` for this exercise, show it:

```javascript
const adaptation = S.cycleAdaptation?.adaptations?.find(a => a.exercise_id === rec.exercise_id);
const aiNoteHtml = adaptation?.ai_note
  ? `<div class="cycle-ai-note">💡 ${_esc(adaptation.ai_note)}</div>`
  : '';
// Add aiNoteHtml to the rendered HTML for this exercise
```

- [ ] **Step 10: Add `cycle_day` field to checkin form**

Find the daily checkin form/modal HTML (look for `checkin` or `energy_level`). After the last existing input field, add:

```html
<div id="cycle-day-row" style="display:none">
  <label style="font-size:12px;color:var(--muted)">День циклу (якщо відрізняється)</label>
  <input type="number" id="checkin-cycle-day" min="1" max="35"
    style="width:80px;padding:6px;border:1px solid var(--border);border-radius:6px;
    background:var(--card);color:var(--text);font-size:14px">
</div>
```

Show this row only for users with `menstrual_tracking=true`. In the checkin submit handler, include the value:

```javascript
const cycleDay = document.getElementById('checkin-cycle-day')?.value;
if (cycleDay) body.cycle_day = parseInt(cycleDay);
```

Check `app/modules/training/routes.py` (or `app/core/routes.py`) to find where checkins are submitted — verify `cycle_day` is already accepted (it maps to `DailyCheckin.cycle_day` which exists in the model).

Show the `cycle-day-row` when the checkin modal opens if `S.user?.menstrual_tracking`:
```javascript
document.getElementById('cycle-day-row').style.display =
  S.user?.menstrual_tracking ? '' : 'none';
```

- [ ] **Step 11: Run tests**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -5
```

Expected: all pass (frontend changes have no Python tests)

- [ ] **Step 12: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: cycle phase badge, pre-workout overlay, adapted targets, checkin field"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|-----------------|------|
| Phase calculation from last_period_date | Task 2 — `_phase_for_day()` + `get_cycle_phase()` |
| Manual cycle_day override via DailyCheckin | Task 2 — `get_cycle_phase()` reads today's checkin |
| cycle_phase + cycle_adapted saved to WorkoutSession | Task 1 (model) + Task 3 (session_start) |
| GET /api/training/cycle/phase endpoint | Task 3 |
| Pre-workout card with Adapt/Ignore buttons | Task 5 — overlay |
| Weight modifier (−10% luteal) | Task 4 — `get_cycle_adaptations()` |
| AI suggestion for compound (luteal) | Task 4 — `_ai_suggestion()` |
| AI suggestion for plyometric (ovulation) | Task 4 — `_ai_suggestion()` |
| Max 3 AI calls per session | Task 4 — `ai_calls < 3` guard |
| AI failure fallback (ai_note=None) | Task 4 — try/except |
| Passive phase badge in Train tab | Task 5 — `renderCycleBadge()` |
| Adapted weights shown in TODAY'S TARGETS | Task 5 — Step 9 |
| AI notes shown during workout | Task 5 — Step 9 |
| cycle_day field in checkin | Task 5 — Step 10 |
| follicular → no card, just badge | Task 2 — `show_card=False` for follicular |
| menstrual → card only if low energy | Task 2 — energy < 5 check |

**Placeholder scan:** No TBD or TODO present. All code blocks are complete.

**Type consistency:**
- `get_cycle_phase(user_id: int) → dict` used in Task 2, 3, 5 ✓
- `get_cycle_adaptations(user_id, phase, modifier) → list` used in Task 3 stub, Task 4 implementation ✓
- `cycle_phase` (String), `cycle_adapted` (Boolean) consistent across model, migration, route, frontend ✓
- `modifier=0.9` for luteal consistent across PHASE_DATA dict and test assertions ✓
