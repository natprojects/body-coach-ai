# Profile, Program Tab & Exercise Insights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Personal Profile overlay, a full Program tab in bottom nav, and AI-generated per-exercise insights triggered manually by the user.

**Architecture:** Backend adds 4 new API endpoints (GET/PATCH /api/users/me, GET /api/training/program/full, POST /api/training/program/insights) and one new AI function. Frontend adds a profile overlay accessible via header icon, a 5th bottom-nav tab (PROGRAM), and exercise insight accordion UI. One DB migration adds 3 nullable Text columns to workout_exercises.

**Tech Stack:** Flask, SQLAlchemy, SQLite (batch_alter_table for migrations), Claude Sonnet 4.6, Telegram Mini App SPA (single index.html), pytest

---

## File Map

| File | Action |
|------|--------|
| `migrations/versions/c3d4e5f6a7b8_add_exercise_insights.py` | Create — adds 3 columns to workout_exercises |
| `app/modules/training/models.py` | Modify — add 3 fields to WorkoutExercise |
| `app/core/routes.py` | Modify — add GET/PATCH /api/users/me |
| `app/modules/training/coach.py` | Modify — add generate_exercise_insights() |
| `app/modules/training/routes.py` | Modify — add GET /api/training/program/full and POST /api/training/program/insights |
| `app/templates/index.html` | Modify — profile overlay, program tab panel, 5th nav item, JS functions |
| `tests/core/test_core_routes.py` | Modify — add tests for profile endpoints |
| `tests/training/test_coach.py` | Modify — add test for generate_exercise_insights |
| `tests/training/test_program_routes.py` | Create — tests for program/full and program/insights |

---

## Task 1: DB Migration — Add Insight Columns to workout_exercises

**Files:**
- Create: `migrations/versions/c3d4e5f6a7b8_add_exercise_insights.py`
- Modify: `app/modules/training/models.py:71-83`

- [ ] **Step 1: Write failing test for new model fields**

In `tests/training/test_models.py`, add at the end:

```python
def test_workout_exercise_has_insight_fields(db, app):
    from app.modules.training.models import WorkoutExercise
    we = WorkoutExercise(workout_id=1, exercise_id=1, order_index=0)
    assert hasattr(we, 'selection_reason')
    assert hasattr(we, 'expected_outcome')
    assert hasattr(we, 'modifications_applied')
    assert we.selection_reason is None
    assert we.expected_outcome is None
    assert we.modifications_applied is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/training/test_models.py::test_workout_exercise_has_insight_fields -v
```
Expected: FAIL with `AssertionError`

- [ ] **Step 3: Add columns to WorkoutExercise model**

In `app/modules/training/models.py`, replace the WorkoutExercise class (lines 71–83):

```python
class WorkoutExercise(db.Model):
    __tablename__ = 'workout_exercises'
    id = db.Column(db.Integer, primary_key=True)
    workout_id = db.Column(db.Integer, db.ForeignKey('workouts.id'), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey('exercises.id'), nullable=False)
    order_index = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text)
    selection_reason = db.Column(db.Text)
    expected_outcome = db.Column(db.Text)
    modifications_applied = db.Column(db.Text)

    planned_sets = db.relationship('PlannedSet', backref='workout_exercise',
                                   order_by='PlannedSet.set_number',
                                   cascade='all, delete-orphan')
    exercise = db.relationship('Exercise')
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/training/test_models.py::test_workout_exercise_has_insight_fields -v
```
Expected: PASS

- [ ] **Step 5: Create migration file**

Create `migrations/versions/c3d4e5f6a7b8_add_exercise_insights.py`:

```python
"""add insight columns to workout_exercises

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('workout_exercises') as batch_op:
        batch_op.add_column(sa.Column('selection_reason', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('expected_outcome', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('modifications_applied', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('workout_exercises') as batch_op:
        batch_op.drop_column('modifications_applied')
        batch_op.drop_column('expected_outcome')
        batch_op.drop_column('selection_reason')
```

- [ ] **Step 6: Verify migration runs cleanly**

```bash
flask db upgrade
```
Expected: `Running upgrade b1c2d3e4f5a6 -> c3d4e5f6a7b8`

- [ ] **Step 7: Commit**

```bash
git add migrations/versions/c3d4e5f6a7b8_add_exercise_insights.py app/modules/training/models.py
git commit -m "feat: add selection_reason, expected_outcome, modifications_applied to workout_exercises"
```

---

## Task 2: Profile API — GET and PATCH /api/users/me

**Files:**
- Modify: `app/core/routes.py`
- Modify: `tests/core/test_core_routes.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/core/test_core_routes.py`:

```python
def test_get_user_me(client, app, db):
    from app.core.models import User
    user = User(telegram_id=40001, name='Natalie', gender='female', age=26,
                weight_kg=58.0, height_cm=163.0, goal_primary='hypertrophy',
                level='intermediate', training_days_per_week=4)
    db.session.add(user)
    db.session.commit()
    resp = client.get('/api/users/me', headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['name'] == 'Natalie'
    assert data['data']['goal_primary'] == 'hypertrophy'
    assert 'telegram_id' not in data['data']
    assert 'password_hash' not in data['data']


def test_patch_user_me(client, app, db):
    from app.core.models import User
    user = User(telegram_id=40002, name='Old Name', age=25)
    db.session.add(user)
    db.session.commit()
    resp = client.patch('/api/users/me',
                        json={'name': 'New Name', 'age': 27, 'weight_kg': 60.5},
                        headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['data']['name'] == 'New Name'
    assert data['data']['age'] == 27
    assert data['data']['weight_kg'] == 60.5


def test_patch_user_me_ignores_protected_fields(client, app, db):
    from app.core.models import User
    user = User(telegram_id=40003)
    db.session.add(user)
    db.session.commit()
    resp = client.patch('/api/users/me',
                        json={'telegram_id': 99999, 'password_hash': 'hacked'},
                        headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    db.session.refresh(user)
    assert user.telegram_id == 40003
    assert user.password_hash is None


def test_get_user_me_requires_auth(client):
    resp = client.get('/api/users/me')
    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/core/test_core_routes.py::test_get_user_me tests/core/test_core_routes.py::test_patch_user_me -v
```
Expected: FAIL with `404`

- [ ] **Step 3: Add _serialize_user helper and routes to app/core/routes.py**

Add after the existing imports and before the `bp` definition (insert after line 10 `bp = Blueprint('core', __name__)`):

Add at the end of `app/core/routes.py`:

```python
_PROFILE_FIELDS = {
    'name', 'gender', 'age', 'weight_kg', 'height_cm', 'body_fat_pct',
    'goal_primary', 'goal_secondary', 'level', 'training_days_per_week',
    'session_duration_min', 'equipment', 'injuries_current', 'injuries_history',
    'postural_issues', 'mobility_issues', 'muscle_imbalances',
    'menstrual_tracking', 'cycle_length_days', 'last_period_date',
    'training_likes', 'training_dislikes', 'previous_methods',
    'had_coach_before', 'motivation_type',
}


def _serialize_user(user):
    d = {f: getattr(user, f) for f in _PROFILE_FIELDS}
    d['id'] = user.id
    if d.get('last_period_date'):
        d['last_period_date'] = d['last_period_date'].isoformat()
    return d


@bp.route('/users/me', methods=['GET'])
@require_auth
def get_user_me():
    user = db.session.get(User, g.user_id)
    return jsonify({'success': True, 'data': _serialize_user(user)})


@bp.route('/users/me', methods=['PATCH'])
@require_auth
def patch_user_me():
    user = db.session.get(User, g.user_id)
    data = request.json or {}
    from datetime import date as _date
    for k, v in data.items():
        if k not in _PROFILE_FIELDS:
            continue
        if k == 'last_period_date' and isinstance(v, str):
            try:
                v = _date.fromisoformat(v)
            except ValueError:
                continue
        setattr(user, k, v)
    db.session.commit()
    return jsonify({'success': True, 'data': _serialize_user(user)})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/core/test_core_routes.py::test_get_user_me tests/core/test_core_routes.py::test_patch_user_me tests/core/test_core_routes.py::test_patch_user_me_ignores_protected_fields tests/core/test_core_routes.py::test_get_user_me_requires_auth -v
```
Expected: 4 PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add app/core/routes.py tests/core/test_core_routes.py
git commit -m "feat: add GET and PATCH /api/users/me profile endpoints"
```

---

## Task 3: generate_exercise_insights() in coach.py

**Files:**
- Modify: `app/modules/training/coach.py`
- Modify: `tests/training/test_coach.py`

- [ ] **Step 1: Write failing test**

Add to `tests/training/test_coach.py`:

```python
def test_generate_exercise_insights(db, app, mock_anthropic):
    from app.modules.training.coach import save_program_from_dict, generate_exercise_insights
    from app.modules.training.models import WorkoutExercise
    import json

    user = _make_user(db)
    program = save_program_from_dict(user.id, SAMPLE_PROGRAM)

    insights_response = [
        {
            "workout_exercise_id": WorkoutExercise.query.first().id,
            "selection_reason": "Great compound push movement for hypertrophy",
            "expected_outcome": "Increased chest and front delt mass",
            "modifications_applied": None,
        }
    ]
    mock_anthropic.messages.create.return_value = MagicMock(
        content=[MagicMock(text=json.dumps(insights_response))]
    )

    generate_exercise_insights(program, user)

    we = WorkoutExercise.query.first()
    assert we.selection_reason == "Great compound push movement for hypertrophy"
    assert we.expected_outcome == "Increased chest and front delt mass"
    assert we.modifications_applied is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/training/test_coach.py::test_generate_exercise_insights -v
```
Expected: FAIL with `ImportError: cannot import name 'generate_exercise_insights'`

- [ ] **Step 3: Add generate_exercise_insights to app/modules/training/coach.py**

Add after the `generate_program` function:

```python
def generate_exercise_insights(program, user) -> int:
    """Generate selection_reason, expected_outcome, modifications_applied for all
    WorkoutExercises in the program. Returns count of exercises updated."""
    from .models import WorkoutExercise, Workout, ProgramWeek, Mesocycle

    # Collect all workout exercises for this program
    exercises_data = []
    wes = (WorkoutExercise.query
           .join(Workout)
           .join(ProgramWeek)
           .join(Mesocycle)
           .filter(Mesocycle.program_id == program.id)
           .order_by(Mesocycle.order_index, ProgramWeek.week_number, Workout.order_index, WorkoutExercise.order_index)
           .all())

    if not wes:
        return 0

    for we in wes:
        exercises_data.append({
            'workout_exercise_id': we.id,
            'exercise_name': we.exercise.name,
            'workout_name': we.workout.name,
            'day_of_week': we.workout.day_of_week,
        })

    system_prompt = (
        "You are an expert strength and conditioning coach. "
        "Return a JSON array only — no prose, no markdown fences. "
        "For each exercise explain why it was chosen for this specific user, "
        "what outcome to expect, and any modification made due to injuries/limitations. "
        "If no modification was needed, set modifications_applied to null. "
        "Return exactly one object per input exercise, in the same order."
    )

    user_prompt = (
        f"User profile:\n"
        f"- Goal: {user.goal_primary}, Level: {user.level}\n"
        f"- Equipment: {user.equipment}\n"
        f"- Injuries: {user.injuries_current}\n"
        f"- Postural issues: {user.postural_issues}\n"
        f"- Mobility issues: {user.mobility_issues}\n"
        f"- Muscle imbalances: {user.muscle_imbalances}\n\n"
        f"Exercises:\n{json.dumps(exercises_data, ensure_ascii=False)}\n\n"
        "Return JSON array with fields: workout_exercise_id, selection_reason, expected_outcome, modifications_applied"
    )

    raw = complete(system_prompt, user_prompt, max_tokens=4096, model='claude-sonnet-4-6')
    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw).strip()

    insights = json.loads(raw)

    # Build lookup by workout_exercise_id
    we_map = {we.id: we for we in wes}
    for item in insights:
        we = we_map.get(item.get('workout_exercise_id'))
        if we:
            we.selection_reason = item.get('selection_reason')
            we.expected_outcome = item.get('expected_outcome')
            we.modifications_applied = item.get('modifications_applied')

    db.session.commit()
    return len(insights)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/training/test_coach.py::test_generate_exercise_insights -v
```
Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add app/modules/training/coach.py tests/training/test_coach.py
git commit -m "feat: add generate_exercise_insights() batch AI function"
```

---

## Task 4: Program Routes — GET /api/training/program/full and POST /api/training/program/insights

**Files:**
- Modify: `app/modules/training/routes.py`
- Create: `tests/training/test_program_routes.py`

- [ ] **Step 1: Write failing tests**

Create `tests/training/test_program_routes.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/training/test_program_routes.py -v
```
Expected: FAIL with `404`

- [ ] **Step 3: Add helper and routes to app/modules/training/routes.py**

Add the `_serialize_program_full` helper and two new routes at the end of `app/modules/training/routes.py` (after the existing `progress_history` route):

```python
def _serialize_program_full(program):
    from datetime import date
    days_elapsed = (date.today() - program.created_at.date()).days
    current_week = (days_elapsed // 7) + 1

    # insights_generated = True if every WorkoutExercise has selection_reason set
    from .models import WorkoutExercise, Workout, ProgramWeek
    total_wes = (WorkoutExercise.query
                 .join(Workout).join(ProgramWeek).join(Mesocycle)
                 .filter(Mesocycle.program_id == program.id).count())
    filled_wes = (WorkoutExercise.query
                  .join(Workout).join(ProgramWeek).join(Mesocycle)
                  .filter(Mesocycle.program_id == program.id,
                          WorkoutExercise.selection_reason.isnot(None)).count())
    insights_generated = total_wes > 0 and filled_wes == total_wes

    return {
        'id': program.id,
        'name': program.name,
        'periodization_type': program.periodization_type,
        'total_weeks': program.total_weeks,
        'current_week': current_week,
        'insights_generated': insights_generated,
        'mesocycles': [{
            'id': m.id,
            'name': m.name,
            'order_index': m.order_index,
            'weeks_count': m.weeks_count,
            'weeks': [{
                'week_number': w.week_number,
                'notes': w.notes,
                'workouts': [{
                    'id': wo.id,
                    'name': wo.name,
                    'day_of_week': wo.day_of_week,
                    'order_index': wo.order_index,
                    'exercises': [{
                        'workout_exercise_id': we.id,
                        'exercise_name': we.exercise.name,
                        'order_index': we.order_index,
                        'selection_reason': we.selection_reason,
                        'expected_outcome': we.expected_outcome,
                        'modifications_applied': we.modifications_applied,
                        'sets': [{
                            'set_number': ps.set_number,
                            'target_reps': ps.target_reps,
                            'target_weight_kg': ps.target_weight_kg,
                            'target_rpe': ps.target_rpe,
                            'rest_seconds': ps.rest_seconds,
                        } for ps in we.planned_sets]
                    } for we in wo.workout_exercises]
                } for wo in w.workouts]
            } for w in m.weeks]
        } for m in program.mesocycles]
    }


@bp.route('/training/program/full', methods=['GET'])
@require_auth
def program_full():
    program = Program.query.filter_by(user_id=g.user_id, status='active').first()
    if not program:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': _serialize_program_full(program)})


@bp.route('/training/program/insights', methods=['POST'])
@require_auth
def program_insights():
    program = Program.query.filter_by(user_id=g.user_id, status='active').first()
    if not program:
        return jsonify({'success': False, 'error': {
            'code': 'NOT_FOUND', 'message': 'No active program'
        }}), 404

    from .models import WorkoutExercise, Workout, ProgramWeek
    total = (WorkoutExercise.query
             .join(Workout).join(ProgramWeek).join(Mesocycle)
             .filter(Mesocycle.program_id == program.id).count())
    filled = (WorkoutExercise.query
              .join(Workout).join(ProgramWeek).join(Mesocycle)
              .filter(Mesocycle.program_id == program.id,
                      WorkoutExercise.selection_reason.isnot(None)).count())

    if total > 0 and filled == total:
        return jsonify({'success': True, 'data': {'count': total, 'already_done': True}})

    user = db.session.get(User, g.user_id)
    from .coach import generate_exercise_insights
    try:
        count = generate_exercise_insights(program, user)
    except (ValueError, Exception) as e:
        return jsonify({'success': False, 'error': {
            'code': 'AI_ERROR', 'message': 'Failed to generate insights, please try again.'
        }}), 500

    return jsonify({'success': True, 'data': {'count': count, 'already_done': False}})
```

Note: `_serialize_program_full` uses `Mesocycle` which is already imported at the top of routes.py.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/training/test_program_routes.py -v
```
Expected: 5 PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add app/modules/training/routes.py tests/training/test_program_routes.py
git commit -m "feat: add GET /api/training/program/full and POST /api/training/program/insights"
```

---

## Task 5: Frontend — Profile Overlay

**Files:**
- Modify: `app/templates/index.html`

This task adds: CSS for profile overlay, the HTML overlay element, 👤 button in the status-bar, and JS functions `openProfile`, `loadProfile`, `toggleProfileEdit`, `saveProfile`.

- [ ] **Step 1: Add profile CSS**

In `app/templates/index.html`, add the following CSS block inside `<style>`, after the `.feedback-text` rule (just before `</style>`):

```css
    /* ── PROFILE OVERLAY ── */
    .profile-section { margin-bottom: 20px; }
    .profile-section-title { font-family: 'Barlow Condensed', sans-serif; font-size: 11px;
      font-weight: 700; letter-spacing: .18em; text-transform: uppercase;
      color: var(--accent); margin-bottom: 12px; }
    .profile-row { display: flex; justify-content: space-between; align-items: flex-start;
      padding: 9px 0; border-bottom: 1px solid var(--border); gap: 12px; }
    .profile-row:last-child { border-bottom: none; }
    .profile-row-label { font-size: 12px; color: var(--muted); text-transform: uppercase;
      letter-spacing: .06em; flex-shrink: 0; padding-top: 2px; }
    .profile-row-value { font-size: 14px; color: var(--text); text-align: right; word-break: break-word; }
    .profile-row input, .profile-row textarea, .profile-row select {
      width: 100%; background: var(--card); border: 1px solid var(--border);
      border-radius: 4px; color: var(--text); font-family: 'DM Sans', sans-serif;
      font-size: 14px; padding: 7px 10px; outline: none; transition: border-color .2s; }
    .profile-row input:focus, .profile-row textarea:focus, .profile-row select:focus {
      border-color: var(--accent); }
    .profile-row textarea { resize: none; height: 64px; }
    #profile-icon { background: none; border: 1px solid var(--border); border-radius: 50%;
      width: 32px; height: 32px; display: flex; align-items: center; justify-content: center;
      cursor: pointer; font-size: 16px; transition: border-color .2s; flex-shrink: 0; }
    #profile-icon:active { border-color: var(--accent); }
    .profile-edit-bar { display: flex; gap: 10px; margin-top: 20px; }
```

- [ ] **Step 2: Add 👤 icon to status-bar**

In `app/templates/index.html`, replace the status-bar div (lines ~276–279):

```html
  <div class="status-bar">
    <span class="user-name" id="user-name">ATHLETE</span>
    <div style="display:flex;align-items:center;gap:10px">
      <span class="today-date" id="today-date"></span>
      <button id="profile-icon" onclick="openProfile()">👤</button>
    </div>
  </div>
```

- [ ] **Step 3: Add profile overlay HTML**

In `app/templates/index.html`, add the following block after the `<!-- OVERLAY: FEEDBACK -->` section (after the closing `</div>` of overlay-feedback, before `<script>`):

```html
<!-- OVERLAY: PROFILE -->
<div id="overlay-profile" class="overlay" onclick="overlayBgClick(event,'overlay-profile')">
  <div class="overlay-sheet">
    <div class="overlay-handle"></div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
      <div class="overlay-title" style="margin-bottom:0">Profile</div>
      <button id="profile-edit-toggle" class="btn btn-ghost"
        style="width:auto;padding:7px 16px;font-size:13px" onclick="toggleProfileEdit()">EDIT</button>
    </div>
    <div id="profile-body"><!-- dynamic --></div>
    <div id="profile-edit-bar" class="profile-edit-bar" style="display:none">
      <button class="btn btn-ghost" style="flex:1" onclick="cancelProfileEdit()">CANCEL</button>
      <button class="btn btn-primary" style="flex:2" onclick="saveProfile()">SAVE</button>
    </div>
    <div id="profile-msg"></div>
  </div>
</div>
```

- [ ] **Step 4: Add profile JS functions**

In `app/templates/index.html`, inside `<script>`, add the following block after the `switchTab` function:

```js
// ── PROFILE ──
let _profileData = null;
let _profileEditMode = false;

async function openProfile() {
  haptic();
  openOverlay('overlay-profile');
  document.getElementById('profile-body').innerHTML =
    '<div style="color:var(--muted);font-size:13px;text-align:center;padding:20px">Loading...</div>';
  const r = await api('GET', '/api/users/me');
  if (!r.success) {
    document.getElementById('profile-body').innerHTML =
      '<div class="error-msg">Failed to load profile</div>';
    return;
  }
  _profileData = r.data;
  _profileEditMode = false;
  renderProfileView();
}

function _fmt(val) {
  if (val === null || val === undefined) return '—';
  if (Array.isArray(val)) return val.length ? val.join(', ') : '—';
  if (typeof val === 'boolean') return val ? 'Yes' : 'No';
  return String(val);
}

function renderProfileView() {
  const d = _profileData;
  document.getElementById('profile-edit-toggle').style.display = '';
  document.getElementById('profile-edit-toggle').textContent = 'EDIT';
  document.getElementById('profile-edit-bar').style.display = 'none';

  const sections = [
    { title: 'Physical', rows: [
      ['Name', d.name], ['Gender', d.gender], ['Age', d.age],
      ['Weight', d.weight_kg ? d.weight_kg + ' kg' : '—'],
      ['Height', d.height_cm ? d.height_cm + ' cm' : '—'],
      ['Body Fat', d.body_fat_pct ? d.body_fat_pct + '%' : '—'],
    ]},
    { title: 'Goals', rows: [
      ['Primary Goal', d.goal_primary], ['Secondary', _fmt(d.goal_secondary)],
      ['Level', d.level],
    ]},
    { title: 'Training', rows: [
      ['Days / Week', d.training_days_per_week],
      ['Session Duration', d.session_duration_min ? d.session_duration_min + ' min' : '—'],
      ['Equipment', _fmt(d.equipment)],
      ['Likes', d.training_likes || '—'], ['Dislikes', d.training_dislikes || '—'],
    ]},
    { title: 'Health', rows: [
      ['Current Injuries', _fmt(d.injuries_current)],
      ['Injury History', _fmt(d.injuries_history)],
      ['Postural Issues', _fmt(d.postural_issues)],
      ['Mobility Issues', _fmt(d.mobility_issues)],
      ['Muscle Imbalances', _fmt(d.muscle_imbalances)],
    ]},
  ];

  if (d.menstrual_tracking) {
    sections.push({ title: 'Cycle', rows: [
      ['Cycle Length', d.cycle_length_days ? d.cycle_length_days + ' days' : '—'],
      ['Last Period', d.last_period_date || '—'],
    ]});
  }

  document.getElementById('profile-body').innerHTML = sections.map(s => `
    <div class="profile-section">
      <div class="profile-section-title">${s.title}</div>
      ${s.rows.map(([label, val]) => `
        <div class="profile-row">
          <span class="profile-row-label">${label}</span>
          <span class="profile-row-value">${val ?? '—'}</span>
        </div>`).join('')}
    </div>`).join('');
}

function toggleProfileEdit() {
  _profileEditMode = true;
  document.getElementById('profile-edit-toggle').style.display = 'none';
  document.getElementById('profile-edit-bar').style.display = 'flex';

  const d = _profileData;
  const fields = [
    { title: 'Physical', rows: [
      ['name','Name','text', d.name||''],
      ['age','Age','number', d.age||''],
      ['weight_kg','Weight (kg)','number', d.weight_kg||''],
      ['height_cm','Height (cm)','number', d.height_cm||''],
      ['body_fat_pct','Body Fat (%)','number', d.body_fat_pct||''],
    ]},
    { title: 'Goals', rows: [
      ['goal_primary','Primary Goal','text', d.goal_primary||''],
      ['training_days_per_week','Days / Week','number', d.training_days_per_week||''],
      ['session_duration_min','Session Duration (min)','number', d.session_duration_min||''],
    ]},
    { title: 'Health & Notes', rows: [
      ['training_likes','Training Likes','textarea', d.training_likes||''],
      ['training_dislikes','Training Dislikes','textarea', d.training_dislikes||''],
    ]},
  ];

  document.getElementById('profile-body').innerHTML = fields.map(s => `
    <div class="profile-section">
      <div class="profile-section-title">${s.title}</div>
      ${s.rows.map(([key, label, type, val]) => `
        <div class="profile-row" style="flex-direction:column;align-items:stretch;gap:6px">
          <span class="profile-row-label">${label}</span>
          ${type === 'textarea'
            ? `<textarea data-field="${key}">${val}</textarea>`
            : `<input type="${type}" data-field="${key}" value="${val}">`
          }
        </div>`).join('')}
    </div>`).join('');
}

function cancelProfileEdit() {
  _profileEditMode = false;
  renderProfileView();
}

async function saveProfile() {
  const inputs = document.querySelectorAll('#profile-body [data-field]');
  const patch = {};
  inputs.forEach(el => {
    const key = el.dataset.field;
    const raw = el.value.trim();
    if (['age','weight_kg','height_cm','body_fat_pct','training_days_per_week','session_duration_min'].includes(key)) {
      patch[key] = raw === '' ? null : parseFloat(raw);
    } else {
      patch[key] = raw || null;
    }
  });

  const msg = document.getElementById('profile-msg');
  msg.innerHTML = '<div style="color:var(--muted);font-size:13px;text-align:center">Saving...</div>';
  const r = await api('PATCH', '/api/users/me', patch);
  if (!r.success) {
    msg.innerHTML = `<div class="error-msg">${r.error?.message || 'Save failed'}</div>`;
    return;
  }
  _profileData = r.data;
  msg.innerHTML = '';
  _profileEditMode = false;

  // Update header name
  if (r.data.name) {
    const el = document.getElementById('user-name');
    if (el) el.textContent = r.data.name.toUpperCase();
  }
  renderProfileView();
}
```

- [ ] **Step 5: Verify manually**

Run dev server: `python run.py`
Open app → tap 👤 icon → profile overlay opens showing user data.
Tap EDIT → fields become editable.
Change a value → tap SAVE → view mode updates.

- [ ] **Step 6: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: add profile overlay with view and edit modes"
```

---

## Task 6: Frontend — Program Tab

**Files:**
- Modify: `app/templates/index.html`

This task adds: CSS for program tab, the `panel-program` tab panel HTML, a 5th nav tab, and the JS functions `loadProgramTab`, `renderProgramTab`, `generateInsights`.

- [ ] **Step 1: Add program tab CSS**

In `app/templates/index.html`, add inside `<style>`, after the profile CSS (before `</style>`):

```css
    /* ── PROGRAM TAB ── */
    .prog-header { flex-shrink: 0; }
    .prog-title { font-family: 'Barlow Condensed', sans-serif; font-size: 22px;
      font-weight: 800; text-transform: uppercase; margin-bottom: 4px; }
    .prog-meta { font-size: 12px; color: var(--muted); margin-bottom: 16px; }
    .prog-insights-btn { margin-bottom: 16px; }
    .insights-ready { font-size: 13px; color: #44ff88; letter-spacing: .06em;
      text-transform: uppercase; padding: 10px 0; }
    .meso-block { background: var(--card); border: 1px solid var(--border);
      border-radius: 4px; margin-bottom: 10px; overflow: hidden; flex-shrink: 0; }
    .meso-header { padding: 14px 16px; cursor: pointer; display: flex;
      justify-content: space-between; align-items: center; }
    .meso-name { font-family: 'Barlow Condensed', sans-serif; font-size: 16px;
      font-weight: 700; text-transform: uppercase; letter-spacing: .08em; }
    .meso-chevron { font-size: 12px; color: var(--muted); transition: transform .2s; }
    .meso-body { padding: 0 12px 12px; display: none; }
    .meso-block.open .meso-body { display: block; }
    .meso-block.open .meso-chevron { transform: rotate(180deg); }
    .week-block { margin-bottom: 8px; border: 1px solid var(--border); border-radius: 3px;
      overflow: hidden; }
    .week-block.current-week { border-color: var(--accent);
      box-shadow: 0 0 8px var(--accent-glow); }
    .week-header { padding: 10px 12px; cursor: pointer; display: flex;
      justify-content: space-between; align-items: center; background: #141414; }
    .week-label { font-family: 'Barlow Condensed', sans-serif; font-size: 14px;
      font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }
    .week-current-badge { font-size: 10px; color: var(--accent); letter-spacing: .1em;
      text-transform: uppercase; }
    .week-body { display: none; padding: 8px; }
    .week-block.open .week-body { display: block; }
    .day-block { margin-bottom: 6px; }
    .day-header { font-family: 'Barlow Condensed', sans-serif; font-size: 13px;
      font-weight: 700; text-transform: uppercase; letter-spacing: .1em;
      color: var(--accent); padding: 6px 4px 4px; }
    .prog-ex-row { padding: 8px 4px; border-bottom: 1px solid var(--border); }
    .prog-ex-row:last-child { border-bottom: none; }
    .prog-ex-name { font-family: 'Barlow Condensed', sans-serif; font-size: 15px;
      font-weight: 700; text-transform: uppercase; }
    .prog-ex-sets { font-size: 12px; color: var(--muted); margin-top: 2px; margin-bottom: 4px; }
    .prog-insight { margin-top: 6px; }
    .prog-insight-toggle { background: none; border: none; color: var(--muted);
      font-size: 12px; cursor: pointer; padding: 3px 0; display: flex;
      align-items: center; gap: 4px; text-align: left; }
    .prog-insight-toggle:active { color: var(--accent); }
    .prog-insight-body { font-size: 13px; color: #aaa; line-height: 1.5;
      padding: 6px 0 2px; display: none; }
    .prog-insight-body.open { display: block; }
    .prog-mod-badge { color: #ffaa44; font-size: 11px; }
```

- [ ] **Step 2: Add panel-program HTML and 5th nav tab**

In `app/templates/index.html`, replace the `<!-- MAIN -->` section's content and nav (lines ~274–310):

```html
<!-- MAIN -->
<div id="screen-main" class="screen">
  <div class="status-bar">
    <span class="user-name" id="user-name">ATHLETE</span>
    <div style="display:flex;align-items:center;gap:10px">
      <span class="today-date" id="today-date"></span>
      <button id="profile-icon" onclick="openProfile()">👤</button>
    </div>
  </div>
  <div class="content">
    <div class="tab-panel active" id="panel-train">
      <div id="train-content"><!-- dynamic --></div>
      <div class="quick-cards">
        <div class="quick-card" onclick="openCheckin()">
          <div class="qc-label">Daily</div>
          <div class="qc-title">Check-In</div>
        </div>
        <div class="quick-card" onclick="openPainLog()">
          <div class="qc-label">Body</div>
          <div class="qc-title">Pain Log</div>
        </div>
      </div>
    </div>
    <div class="tab-panel" id="panel-program">
      <div id="program-content"><!-- dynamic --></div>
    </div>
    <div class="tab-panel" id="panel-nutrition">
      <div class="coming-soon"><div class="cs-line"></div><div class="cs-text">Nutrition</div><div class="cs-line"></div></div>
    </div>
    <div class="tab-panel" id="panel-sleep">
      <div class="coming-soon"><div class="cs-line"></div><div class="cs-text">Sleep</div><div class="cs-line"></div></div>
    </div>
    <div class="tab-panel" id="panel-coach">
      <div class="coming-soon"><div class="cs-line"></div><div class="cs-text">Coach</div><div class="cs-line"></div></div>
    </div>
  </div>
  <nav class="bottom-nav">
    <button class="nav-tab active" data-tab="train" onclick="switchTab('train')"><span class="nav-tab-label">Train</span></button>
    <button class="nav-tab" data-tab="program" onclick="switchTab('program')"><span class="nav-tab-label">Program</span></button>
    <button class="nav-tab" data-tab="nutrition" onclick="switchTab('nutrition')"><span class="nav-tab-label">Nutrition</span></button>
    <button class="nav-tab" data-tab="sleep" onclick="switchTab('sleep')"><span class="nav-tab-label">Sleep</span></button>
    <button class="nav-tab" data-tab="coach" onclick="switchTab('coach')"><span class="nav-tab-label">Coach</span></button>
  </nav>
</div>
```

Note: the status-bar here already includes the 👤 button from Task 5. If Task 5 was already applied, do not duplicate — the status-bar in Task 5 and this task are the same. Replace the whole `<!-- MAIN -->` block once using this version.

- [ ] **Step 3: Hook switchTab to load program data**

In `app/templates/index.html`, replace the `switchTab` function:

```js
function switchTab(name) {
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelector(`[data-tab="${name}"]`).classList.add('active');
  document.getElementById(`panel-${name}`).classList.add('active');
  haptic();
  if (name === 'program') loadProgramTab();
}
```

- [ ] **Step 4: Add program tab JS functions**

In `app/templates/index.html`, inside `<script>`, add after the `saveProfile` function:

```js
// ── PROGRAM TAB ──
let _programData = null;

async function loadProgramTab() {
  const el = document.getElementById('program-content');
  el.innerHTML = '<div style="color:var(--muted);font-size:13px;text-align:center;padding:40px">Loading...</div>';
  const r = await api('GET', '/api/training/program/full');
  if (!r.success) {
    el.innerHTML = '<div class="error-msg">Failed to load program</div>';
    return;
  }
  _programData = r.data;
  renderProgramTab();
}

const DAY_NAMES = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];

function renderProgramTab() {
  const el = document.getElementById('program-content');
  const p = _programData;

  if (!p) {
    el.innerHTML = `
      <div class="no-program-card">
        <div class="np-title">No Program Yet</div>
        <div class="np-body">Generate your personalized training program first.</div>
        <button class="btn btn-primary" onclick="generateProgram()">GENERATE PROGRAM</button>
      </div>`;
    return;
  }

  const insightsBtn = p.insights_generated
    ? `<div class="insights-ready">✓ Exercise Insights Ready</div>`
    : `<div class="prog-insights-btn">
        <button class="btn btn-ghost" id="insights-btn" onclick="generateInsights()">
          GENERATE EXERCISE INSIGHTS
        </button>
      </div>`;

  const mesosHtml = p.mesocycles.map(m => `
    <div class="meso-block open">
      <div class="meso-header" onclick="toggleMeso(this)">
        <span class="meso-name">${m.name}</span>
        <span class="meso-chevron">▲</span>
      </div>
      <div class="meso-body">
        ${m.weeks.map(w => {
          const isCurrent = w.week_number === p.current_week;
          return `
          <div class="week-block ${isCurrent ? 'open current-week' : ''}">
            <div class="week-header" onclick="toggleWeek(this)">
              <span class="week-label">Week ${w.week_number}</span>
              ${isCurrent ? '<span class="week-current-badge">● CURRENT</span>' : '<span></span>'}
            </div>
            <div class="week-body">
              ${w.workouts.map(wo => `
                <div class="day-block">
                  <div class="day-header">${DAY_NAMES[wo.day_of_week]} — ${wo.name}</div>
                  ${wo.exercises.map(ex => {
                    const setsStr = ex.sets.length > 0
                      ? `${ex.sets.length}×${ex.sets[0].target_reps} @${ex.sets[0].target_weight_kg}kg RPE${ex.sets[0].target_rpe}`
                      : '';
                    const insightHtml = p.insights_generated ? `
                      <div class="prog-insight">
                        <button type="button" class="prog-insight-toggle"
                          onclick="toggleInsight(this)"><span class="insight-arrow">▶</span> Why this exercise</button>
                        <div class="prog-insight-body">${ex.selection_reason || '—'}</div>
                      </div>
                      <div class="prog-insight">
                        <button type="button" class="prog-insight-toggle"
                          onclick="toggleInsight(this)"><span class="insight-arrow">▶</span> Expected outcome</button>
                        <div class="prog-insight-body">${ex.expected_outcome || '—'}</div>
                      </div>
                      ${ex.modifications_applied ? `
                      <div class="prog-insight">
                        <button type="button" class="prog-insight-toggle"
                          onclick="toggleInsight(this)"><span class="insight-arrow">▶</span> <span class="prog-mod-badge">⚠ Modification</span></button>
                        <div class="prog-insight-body">${ex.modifications_applied}</div>
                      </div>` : ''}` : '';
                    return `
                    <div class="prog-ex-row">
                      <div class="prog-ex-name">${ex.exercise_name}</div>
                      <div class="prog-ex-sets">${setsStr}</div>
                      ${insightHtml}
                    </div>`;
                  }).join('')}
                </div>`).join('')}
            </div>
          </div>`;
        }).join('')}
      </div>
    </div>`).join('');

  el.innerHTML = `
    <div class="prog-header">
      <div class="prog-title">${p.name}</div>
      <div class="prog-meta">${p.total_weeks} weeks · ${p.periodization_type}</div>
      ${insightsBtn}
    </div>
    ${mesosHtml}`;
}

function toggleMeso(header) {
  header.closest('.meso-block').classList.toggle('open');
}

function toggleWeek(header) {
  header.closest('.week-block').classList.toggle('open');
}

function toggleInsight(btn) {
  const body = btn.nextElementSibling;
  const isOpen = body.classList.toggle('open');
  const arrow = btn.querySelector('.insight-arrow');
  if (arrow) arrow.textContent = isOpen ? '▼' : '▶';
}

async function generateInsights() {
  const btn = document.getElementById('insights-btn');
  if (!btn) return;
  btn.textContent = 'GENERATING INSIGHTS...';
  btn.disabled = true;
  haptic('medium');
  const r = await api('POST', '/api/training/program/insights', null, 120000);
  if (r.success) {
    haptic('heavy');
    await loadProgramTab();
  } else {
    btn.textContent = 'TRY AGAIN';
    btn.disabled = false;
  }
}
```

- [ ] **Step 5: Verify manually**

Run dev server: `python run.py`
Open app → tap PROGRAM tab → program loads with mesocycles expanded.
Current week highlighted in blue border.
Tap GENERATE EXERCISE INSIGHTS → loading → insights appear as collapsible rows.
Tap "▶ Why this exercise" → expands to show explanation text.

- [ ] **Step 6: Run full test suite**

```bash
pytest -v
```
Expected: all tests pass (frontend changes don't affect backend tests)

- [ ] **Step 7: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: add program tab with full program view, insights accordion, and 5th nav tab"
```

---

## Task 7: Deploy

**Files:**
- None (deploy via git push)

- [ ] **Step 1: Push to main**

```bash
git push origin main
```

- [ ] **Step 2: Wait for GitHub Actions deploy to complete**

Check: `gh run watch` or visit the Actions tab in GitHub.

- [ ] **Step 3: Apply migration on server**

```bash
# GitHub Actions already runs flask db upgrade after docker compose up
# Verify it ran:
# ssh to server and check: docker compose logs gym-coach | grep alembic
```

Expected: `Running upgrade b1c2d3e4f5a6 -> c3d4e5f6a7b8`

- [ ] **Step 4: Smoke test**

In the app: tap 👤 → profile opens. Tap PROGRAM tab → program loads. If program exists, tap GENERATE EXERCISE INSIGHTS → waits ~20s → insights appear.
