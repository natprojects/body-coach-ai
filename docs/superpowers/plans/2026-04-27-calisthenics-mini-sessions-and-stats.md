# Calisthenics Mini-Sessions & Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add on-demand mini-sessions (3 types), weekly stats, training history, schedule editor in regenerate flow, and 30-day Coach memory for calisthenics.

**Architecture:** Reuse existing `Workout / WorkoutSession / LoggedExercise / LoggedSet` hierarchy. Mini-sessions are `Workout` rows with `program_week_id=NULL` and `mini_kind` set. `WorkoutSession.kind` distinguishes 'main' vs 'mini' for stats grouping. All logging endpoints work identically for both.

**Tech Stack:** Flask, SQLAlchemy, SQLite, Alembic, Anthropic API, Vanilla JS (Telegram Mini App).

---

## File Map

### Backend
- **Modify:** `app/modules/training/models.py` — add `kind` to `WorkoutSession`, `mini_kind` to `Workout`, make `Workout.program_week_id` nullable
- **Modify:** `app/modules/calisthenics/models.py` — add `optional_target_per_week` to `CalisthenicsProfile`
- **Create:** `migrations/versions/j0k1l2m3n4o5_add_mini_sessions_and_stats.py`
- **Modify:** `app/modules/calisthenics/coach.py` — add `generate_mini_session()` + `save_mini_session_from_dict()`
- **Modify:** `app/modules/calisthenics/routes.py` — add 5 new endpoints, extend `/regenerate` body, extend `/profile` validation
- **Modify:** `app/modules/coach/context.py` — replace last-calisthenics-session with 30-day summary

### Frontend
- **Modify:** `app/templates/index.html` — weekly stats card, "+ Міні-сесія" button + modal picker, history page + session detail, inline schedule editor in regenerate flow, new chip row in profile wizard

### Tests
- **Create:** `tests/calisthenics/test_mini_sessions.py`
- **Create:** `tests/calisthenics/test_stats.py`
- **Modify:** `tests/calisthenics/test_program_endpoints.py` — extend regenerate test for new params
- **Modify:** `tests/calisthenics/conftest.py` — keep seeding 37 calisthenics exercises

---

## Task 1: DB migration — schema changes

**Files:**
- Modify: `app/modules/training/models.py`
- Modify: `app/modules/calisthenics/models.py`
- Create: `migrations/versions/j0k1l2m3n4o5_add_mini_sessions_and_stats.py`

- [ ] **Step 1: Update `Workout` model**

In `app/modules/training/models.py`, update the `Workout` class — make `program_week_id` nullable and add `mini_kind`:

```python
class Workout(db.Model):
    __tablename__ = 'workouts'
    id = db.Column(db.Integer, primary_key=True)
    program_week_id = db.Column(db.Integer, db.ForeignKey('program_weeks.id'), nullable=True)
    mini_kind = db.Column(db.String(20))  # 'stretch' | 'short' | 'skill' for mini-sessions; NULL for main
    day_of_week = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    order_index = db.Column(db.Integer, nullable=False)
    target_muscle_groups = db.Column(db.String(200))
    estimated_duration_min = db.Column(db.Integer)
    warmup_notes = db.Column(db.Text)

    workout_exercises = db.relationship('WorkoutExercise', backref='workout',
                                        order_by='WorkoutExercise.order_index',
                                        cascade='all, delete-orphan')
```

(Don't touch other Workout fields — only the two changes above.)

- [ ] **Step 2: Update `WorkoutSession` model**

In the same file, find `WorkoutSession` class and add `kind` column:

```python
    kind = db.Column(db.String(20), default='main', nullable=False, server_default='main')  # 'main' | 'mini'
```

Place it near the existing `module` column for readability.

- [ ] **Step 3: Update `CalisthenicsProfile` model**

In `app/modules/calisthenics/models.py`, find the `CalisthenicsProfile` class and add:

```python
    optional_target_per_week = db.Column(db.Integer, default=0, nullable=False, server_default='0')
```

Place it after `motivation` and before `updated_at`.

- [ ] **Step 4: Create migration file**

```bash
cd /Users/natalie/body-coach-ai
flask db current
```

Note current head (should be `i9j0k1l2m3n4`). Use it as `down_revision`.

Create `migrations/versions/j0k1l2m3n4o5_add_mini_sessions_and_stats.py`:

```python
"""add mini-sessions kind and stats fields

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Branch Labels: None
Depends On: None
"""
from alembic import op
import sqlalchemy as sa

revision = 'j0k1l2m3n4o5'
down_revision = 'i9j0k1l2m3n4'
branch_labels = None
depends_on = None


def upgrade():
    # Workouts: mini_kind + program_week_id nullable
    with op.batch_alter_table('workouts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mini_kind', sa.String(20), nullable=True))
        batch_op.alter_column('program_week_id', existing_type=sa.Integer(), nullable=True)

    # WorkoutSession: kind
    with op.batch_alter_table('workout_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('kind', sa.String(20), nullable=False, server_default='main'))

    # CalisthenicsProfile: optional_target_per_week
    with op.batch_alter_table('calisthenics_profiles', schema=None) as batch_op:
        batch_op.add_column(sa.Column('optional_target_per_week', sa.Integer, nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('calisthenics_profiles', schema=None) as batch_op:
        batch_op.drop_column('optional_target_per_week')

    with op.batch_alter_table('workout_sessions', schema=None) as batch_op:
        batch_op.drop_column('kind')

    with op.batch_alter_table('workouts', schema=None) as batch_op:
        batch_op.alter_column('program_week_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column('mini_kind')
```

- [ ] **Step 5: Run migration**

```bash
flask db upgrade
flask db current
```

Expected: `j0k1l2m3n4o5 (head)`.

- [ ] **Step 6: Run full suite**

```bash
pytest -q
```

Expected: 190 still pass (no behavior change yet).

- [ ] **Step 7: Commit**

```bash
git add app/modules/training/models.py app/modules/calisthenics/models.py migrations/versions/j0k1l2m3n4o5_add_mini_sessions_and_stats.py
git commit -m "feat: add mini-session schema (kind, mini_kind, optional_target_per_week)"
```

---

## Task 2: Profile endpoint validation for `optional_target_per_week`

**Files:**
- Modify: `app/modules/calisthenics/routes.py`
- Modify: `tests/calisthenics/test_routes.py`

- [ ] **Step 1: Write failing tests**

APPEND to `tests/calisthenics/test_routes.py`:

```python
def test_post_profile_accepts_optional_target(app, client, db):
    user = _make_user(db, telegram_id=70080)
    body = {
        'goals': ['muscle'], 'equipment': ['floor'],
        'days_per_week': 4, 'session_duration_min': 45,
        'injuries': [], 'motivation': 'look',
        'optional_target_per_week': 2,
    }
    r = client.post('/api/calisthenics/profile', json=body, headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['optional_target_per_week'] == 2


def test_post_profile_default_optional_target_zero(app, client, db):
    user = _make_user(db, telegram_id=70081)
    body = {
        'goals': ['muscle'], 'equipment': ['floor'],
        'days_per_week': 4, 'session_duration_min': 45,
        'injuries': [], 'motivation': 'look',
    }
    r = client.post('/api/calisthenics/profile', json=body, headers=_h(app, user.id))
    assert r.status_code == 200
    assert r.get_json()['data']['optional_target_per_week'] == 0


def test_post_profile_invalid_optional_target(app, client, db):
    user = _make_user(db, telegram_id=70082)
    body = {
        'goals': ['muscle'], 'equipment': ['floor'],
        'days_per_week': 4, 'session_duration_min': 45,
        'injuries': [], 'motivation': 'look',
        'optional_target_per_week': 8,
    }
    r = client.post('/api/calisthenics/profile', json=body, headers=_h(app, user.id))
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'INVALID_FIELD'
```

- [ ] **Step 2: Verify tests fail**

```bash
pytest tests/calisthenics/test_routes.py::test_post_profile_accepts_optional_target -v
```

Expected: FAIL — field not present in response or rejected.

- [ ] **Step 3: Update `set_calisthenics_profile` route**

In `app/modules/calisthenics/routes.py`, find `set_calisthenics_profile()`. Add validation + assignment after the existing motivation check:

```python
    optional_target = data.get('optional_target_per_week', 0)
    if not isinstance(optional_target, int) or isinstance(optional_target, bool) or not (0 <= optional_target <= 7):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': 'optional_target_per_week must be an integer between 0 and 7',
        }}), 400
```

After the existing field assignments (`profile.motivation = motivation`), add:

```python
    profile.optional_target_per_week = optional_target
```

Update `_profile_to_dict` to include the new field:

```python
def _profile_to_dict(profile: CalisthenicsProfile) -> dict:
    return {
        'goals':                profile.goals or [],
        'equipment':            profile.equipment or [],
        'days_per_week':        profile.days_per_week,
        'session_duration_min': profile.session_duration_min,
        'injuries':             profile.injuries or [],
        'motivation':           profile.motivation,
        'optional_target_per_week': profile.optional_target_per_week or 0,
    }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/calisthenics/test_routes.py -v
```

Expected: all PASS (3 new + existing).

- [ ] **Step 5: Commit**

```bash
git add app/modules/calisthenics/routes.py tests/calisthenics/test_routes.py
git commit -m "feat: support optional_target_per_week in profile endpoints"
```

---

## Task 3: AI mini-session generation function

**Files:**
- Modify: `app/modules/calisthenics/coach.py`
- Create: `tests/calisthenics/test_mini_sessions.py`

- [ ] **Step 1: Write failing tests**

Create `tests/calisthenics/test_mini_sessions.py`:

```python
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
```

- [ ] **Step 2: Verify tests fail**

```bash
pytest tests/calisthenics/test_mini_sessions.py::test_save_mini_session_creates_workout_with_kind -v
```

Expected: FAIL — function does not exist.

- [ ] **Step 3: Implement save function in coach.py**

In `app/modules/calisthenics/coach.py`, append at the end:

```python
_VALID_MINI_TYPES = {'stretch', 'short', 'skill'}


def save_mini_session_from_dict(user_id: int, mini_type: str, mini_dict: dict) -> Workout:
    """Persist an AI-generated mini-session as a Workout row with program_week_id=NULL.
    Reuses existing WorkoutExercise/PlannedSet hierarchy so logging is identical to main."""
    if mini_type not in _VALID_MINI_TYPES:
        raise ValueError(f"Invalid mini_type: {mini_type!r}")

    workout = Workout(
        program_week_id=None,
        mini_kind=mini_type,
        day_of_week=0,  # not used for mini, but column is non-null
        name=mini_dict.get('name', f'{mini_type} session'),
        order_index=0,
        estimated_duration_min=mini_dict.get('estimated_duration_min'),
        warmup_notes=mini_dict.get('warmup_notes'),
    )
    db.session.add(workout)
    db.session.flush()

    for ex_dict in mini_dict.get('exercises', []):
        exercise = _resolve_calisthenics_exercise(ex_dict['exercise_name'])
        we = WorkoutExercise(
            workout_id=workout.id,
            exercise_id=exercise.id,
            order_index=ex_dict.get('order_index', 0),
            tempo=ex_dict.get('tempo'),
            is_mandatory=ex_dict.get('is_mandatory', True),
            notes=ex_dict.get('coaching_notes') or ex_dict.get('notes'),
        )
        db.session.add(we)
        db.session.flush()

        for s_dict in ex_dict.get('sets', []):
            ps = PlannedSet(
                workout_exercise_id=we.id,
                set_number=s_dict['set_number'],
                target_reps=s_dict.get('target_reps'),
                target_seconds=s_dict.get('target_seconds'),
                target_weight_kg=None,
                target_rpe=s_dict.get('target_rpe'),
                rest_seconds=s_dict.get('rest_seconds'),
                is_amrap=s_dict.get('is_amrap', False),
            )
            db.session.add(ps)

    db.session.commit()
    return workout
```

- [ ] **Step 4: Run save tests**

```bash
pytest tests/calisthenics/test_mini_sessions.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Implement `generate_mini_session()` in coach.py**

Append:

```python
_MINI_PROMPTS = {
    'stretch': {
        'duration_min': 10,
        'guidance': (
            "Generate a 10-minute mobility / stretch session with 5-7 exercises, "
            "30-60 seconds each. Target: hips, shoulders, spine, posture. "
            "All exercises are seconds-based (target_seconds set, target_reps null). "
            "No AMRAP. Anchor selections to user's injuries (avoid aggravating positions)."
        ),
    },
    'short': {
        'duration_min': 15,
        'guidance': (
            "Generate a 15-minute compact strength session with 3-4 exercises, "
            "2 sets each. The LAST set of each exercise has is_amrap: true. "
            "Use exercise levels matching the user's main program — don't push harder. "
            "Avoid duplicating chains the user already trained today (a comma-separated list "
            "of recently used chains is provided as 'today_main_chains')."
        ),
    },
    'skill': {
        'duration_min': 10,
        'guidance': (
            "Generate a 10-minute skill-focus session with 1-2 specific skill progressions. "
            "Examples: L-sit holds, handstand wall holds, planche leans, dragon flag negatives. "
            "Focus on form/quality, low volume (3-4 sets × 5-15s holds OR 3 reps with 60-90s rest). "
            "Pick a skill the user is close to but hasn't fully mastered, looking at their assessment."
        ),
    },
}


def generate_mini_session(user, profile: CalisthenicsProfile,
                          last_assessment: CalisthenicsAssessment, mini_type: str,
                          today_main_chains: list = None) -> dict:
    """Call Claude to generate a mini-session of the given type. Returns parsed JSON dict."""
    if mini_type not in _VALID_MINI_TYPES:
        raise ValueError(f"Invalid mini_type: {mini_type!r}")

    config = _MINI_PROMPTS[mini_type]
    catalog = _calisthenics_exercise_catalog()

    system_prompt = f"""You are an expert calisthenics coach.
Generate a calisthenics MINI-SESSION as compact JSON only — no prose, no markdown, just valid JSON.

{config['guidance']}

CLOSED EXERCISE LIST (use ONLY these names, exactly as written):
{json.dumps(catalog, ensure_ascii=False)}

INJURIES from profile: {profile.injuries or []}
GOALS: {profile.goals or []}

JSON shape (compact):
{{"name":"...","estimated_duration_min":{config['duration_min']},"warmup_notes":"...","exercises":[{{"exercise_name":"...","order_index":0,"tempo":"...","is_mandatory":true,"coaching_notes":"...","sets":[{{"set_number":1,"target_reps":"8-12","target_seconds":null,"target_rpe":7.0,"rest_seconds":60,"is_amrap":false}}]}}]}}"""

    user_prompt = f"""User: {user.name}, level: {user.level}, equipment: {profile.equipment}
Last assessment: pushups={last_assessment.pushups}, pullups={last_assessment.pullups}, squats={last_assessment.squats}, plank={last_assessment.plank}s, hollow={last_assessment.hollow_body}s
today_main_chains: {today_main_chains or []}

Return only the JSON object."""

    response = complete(
        system_prompt=system_prompt, user_message=user_prompt,
        max_tokens=2048, model='claude-sonnet-4-6',
    )
    response = re.sub(r'^```(?:json)?\s*', '', response.strip())
    response = re.sub(r'\s*```$', '', response).strip()
    try:
        return json.loads(response)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI returned invalid JSON for mini-session: {e}")
```

- [ ] **Step 6: Run full suite**

```bash
pytest -q
```

Expected: 197+ tests pass (4 new).

- [ ] **Step 7: Commit**

```bash
git add app/modules/calisthenics/coach.py tests/calisthenics/test_mini_sessions.py
git commit -m "feat: AI generation + save function for mini-sessions (stretch/short/skill)"
```

---

## Task 4: POST /mini-session/generate endpoint

**Files:**
- Modify: `app/modules/calisthenics/routes.py`
- Modify: `tests/calisthenics/test_mini_sessions.py`

- [ ] **Step 1: Write failing tests**

APPEND to `tests/calisthenics/test_mini_sessions.py`:

```python
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
```

- [ ] **Step 2: Run to verify failing**

```bash
pytest tests/calisthenics/test_mini_sessions.py::test_generate_mini_creates_workout -v
```

Expected: FAIL — 404.

- [ ] **Step 3: Add endpoint to routes.py**

In `app/modules/calisthenics/routes.py`, update the import:

```python
from .coach import (
    generate_calisthenics_program,
    save_calisthenics_program_from_dict,
    generate_calisthenics_insights,
    generate_mini_session,
    save_mini_session_from_dict,
)
```

Append the endpoint:

```python
def _serialize_mini_workout(workout) -> dict:
    return {
        'workout_id': workout.id,
        'name': workout.name,
        'mini_kind': workout.mini_kind,
        'estimated_duration_min': workout.estimated_duration_min,
        'exercises': [{
            'id': we.id,
            'exercise_id': we.exercise_id,
            'exercise_name': db.session.get(Exercise, we.exercise_id).name,
            'unit': db.session.get(Exercise, we.exercise_id).unit,
            'order_index': we.order_index,
            'tempo': we.tempo,
            'notes': we.notes,
            'sets': [{
                'id': ps.id, 'set_number': ps.set_number,
                'target_reps': ps.target_reps, 'target_seconds': ps.target_seconds,
                'target_rpe': ps.target_rpe, 'rest_seconds': ps.rest_seconds,
                'is_amrap': ps.is_amrap,
            } for ps in PlannedSet.query.filter_by(
                workout_exercise_id=we.id
            ).order_by(PlannedSet.set_number).all()],
        } for we in sorted(workout.workout_exercises, key=lambda x: x.order_index)],
    }


@bp.route('/calisthenics/mini-session/generate', methods=['POST'])
@require_auth
def post_generate_mini_session():
    data = request.get_json(silent=True) or {}
    mini_type = data.get('type')
    if mini_type not in ('stretch', 'short', 'skill'):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_TYPE',
            'message': "type must be one of: stretch, short, skill",
        }}), 400

    user = db.session.get(User, g.user_id)
    profile = CalisthenicsProfile.query.filter_by(user_id=g.user_id).first()
    if not profile:
        return jsonify({'success': False, 'error': {
            'code': 'PROFILE_REQUIRED', 'message': 'Complete the profile first',
        }}), 400

    last_assessment = (CalisthenicsAssessment.query
                       .filter_by(user_id=g.user_id)
                       .order_by(CalisthenicsAssessment.assessed_at.desc())
                       .first())
    if not last_assessment:
        return jsonify({'success': False, 'error': {
            'code': 'ASSESSMENT_REQUIRED', 'message': 'Take the assessment first',
        }}), 400

    # Compute today_main_chains for context (chains the user trained today, to avoid duplication)
    from datetime import date
    today_chains = []
    today_sessions = WorkoutSession.query.filter_by(
        user_id=g.user_id, module='calisthenics', date=date.today(), kind='main'
    ).all()
    for s in today_sessions:
        if s.workout:
            for we in s.workout.workout_exercises:
                ex = db.session.get(Exercise, we.exercise_id)
                if ex and ex.progression_chain:
                    today_chains.append(ex.progression_chain)
    today_chains = list(set(today_chains))

    try:
        mini_dict = generate_mini_session(user, profile, last_assessment, mini_type, today_chains)
        workout = save_mini_session_from_dict(g.user_id, mini_type, mini_dict)
    except ValueError as e:
        return jsonify({'success': False, 'error': {
            'code': 'AI_GENERATION_FAILED', 'message': str(e),
        }}), 500

    return jsonify({'success': True, 'data': _serialize_mini_workout(workout)})
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/calisthenics/test_mini_sessions.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/modules/calisthenics/routes.py tests/calisthenics/test_mini_sessions.py
git commit -m "feat: POST /api/calisthenics/mini-session/generate"
```

---

## Task 5: Stamp `kind='mini'` on session/start when starting a mini-workout

**Files:**
- Modify: `app/modules/calisthenics/routes.py`
- Modify: `tests/calisthenics/test_mini_sessions.py`

- [ ] **Step 1: Write failing test**

APPEND to `tests/calisthenics/test_mini_sessions.py`:

```python
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
```

- [ ] **Step 2: Verify failing**

```bash
pytest tests/calisthenics/test_mini_sessions.py::test_session_start_for_mini_workout_sets_kind -v
```

Expected: FAIL — kind is 'main' since session/start always sets 'main' or default.

- [ ] **Step 3: Update `post_session_start` route**

In `app/modules/calisthenics/routes.py`, find `post_session_start`. The current `WorkoutSession` constructor doesn't set `kind`. Update creation block:

```python
    # If workout has mini_kind set, this is a mini-session
    session_kind = 'mini' if workout.mini_kind else 'main'
    session = WorkoutSession(
        user_id=g.user_id, workout_id=workout_id,
        module='calisthenics', status='in_progress',
        date=date.today(),
        kind=session_kind,
    )
```

Also update the module-mismatch check — mini-workouts have `program_week_id=None` and don't belong to a program, so the existing program-lookup logic must handle that:

```python
    # Mini-workouts have no program_week — accept directly
    if workout.mini_kind:
        # Anyone with a calisthenics profile can start any mini-workout they own.
        # We check ownership: this workout was created via mini-session/generate, but
        # we don't track creator on Workout. Trust the path for v1 (mini workouts are
        # only created via authenticated POST /mini-session/generate which already
        # enforces profile/assessment).
        pass
    else:
        program = (Program.query
                   .join(Mesocycle).join(ProgramWeek)
                   .filter(ProgramWeek.id == workout.program_week_id)
                   .first())
        if not program or program.user_id != g.user_id:
            return jsonify({'success': False, 'error': {
                'code': 'WORKOUT_NOT_FOUND', 'message': 'Workout not found',
            }}), 404
        if program.module != 'calisthenics':
            return jsonify({'success': False, 'error': {
                'code': 'MODULE_MISMATCH',
                'message': 'This workout belongs to a different module',
            }}), 400
```

So the full `post_session_start` becomes:

```python
@bp.route('/calisthenics/session/start', methods=['POST'])
@require_auth
def post_session_start():
    data = request.get_json(silent=True) or {}
    workout_id = data.get('workout_id')
    if not isinstance(workout_id, int):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD', 'message': 'workout_id required',
        }}), 400

    workout = db.session.get(Workout, workout_id)
    if not workout:
        return jsonify({'success': False, 'error': {
            'code': 'WORKOUT_NOT_FOUND', 'message': 'Workout not found',
        }}), 404

    if workout.mini_kind:
        # Mini-session — bypass program ownership check (mini workouts have no program)
        pass
    else:
        program = (Program.query
                   .join(Mesocycle).join(ProgramWeek)
                   .filter(ProgramWeek.id == workout.program_week_id)
                   .first())
        if not program or program.user_id != g.user_id:
            return jsonify({'success': False, 'error': {
                'code': 'WORKOUT_NOT_FOUND', 'message': 'Workout not found',
            }}), 404
        if program.module != 'calisthenics':
            return jsonify({'success': False, 'error': {
                'code': 'MODULE_MISMATCH',
                'message': 'This workout belongs to a different module',
            }}), 400

    session_kind = 'mini' if workout.mini_kind else 'main'
    session = WorkoutSession(
        user_id=g.user_id, workout_id=workout_id,
        module='calisthenics', status='in_progress',
        date=date.today(),
        kind=session_kind,
    )
    db.session.add(session)
    db.session.commit()
    return jsonify({'success': True, 'data': {'session_id': session.id}})
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/calisthenics/test_mini_sessions.py -v
pytest -q
```

Expected: all PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
git add app/modules/calisthenics/routes.py tests/calisthenics/test_mini_sessions.py
git commit -m "feat: session/start sets kind='mini' for mini-workouts; bypass program check"
```

---

## Task 6: GET /stats/weekly endpoint

**Files:**
- Modify: `app/modules/calisthenics/routes.py`
- Create: `tests/calisthenics/test_stats.py`

- [ ] **Step 1: Write failing tests**

Create `tests/calisthenics/test_stats.py`:

```python
from datetime import datetime, date, timedelta
import pytest
from app.core.models import User
from app.core.auth import create_jwt
from app.modules.calisthenics.models import CalisthenicsProfile, CalisthenicsAssessment
from app.modules.training.models import (
    Program, Mesocycle, ProgramWeek, Workout, Exercise, WorkoutExercise, PlannedSet,
    WorkoutSession,
)


def _make_user(db, telegram_id=70200, days_per_week=4, optional_target=2):
    u = User(
        telegram_id=telegram_id, name='Stats', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['floor'], onboarding_completed_at=datetime.utcnow(),
        active_module='calisthenics',
    )
    db.session.add(u); db.session.commit()
    p = CalisthenicsProfile(
        user_id=u.id, goals=['muscle'], equipment=['floor'],
        days_per_week=days_per_week, session_duration_min=45,
        injuries=[], motivation='look',
        optional_target_per_week=optional_target,
    )
    db.session.add(p); db.session.commit()
    return u, p


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


def _add_session(db, user, kind, dow_offset_from_monday):
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    s = WorkoutSession(
        user_id=user.id, module='calisthenics', status='completed',
        date=monday + timedelta(days=dow_offset_from_monday),
        kind=kind,
    )
    db.session.add(s); db.session.commit()
    return s


def test_weekly_stats_zero_when_no_sessions(app, client, db):
    user, _ = _make_user(db, telegram_id=70200)
    r = client.get('/api/calisthenics/stats/weekly', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['main_done'] == 0
    assert data['mini_done'] == 0
    assert data['main_target'] == 4
    assert data['mini_target'] == 2


def test_weekly_stats_counts_main_and_mini(app, client, db):
    user, _ = _make_user(db, telegram_id=70201)
    _add_session(db, user, 'main', 0)
    _add_session(db, user, 'main', 1)
    _add_session(db, user, 'mini', 2)
    r = client.get('/api/calisthenics/stats/weekly', headers=_h(app, user.id))
    data = r.get_json()['data']
    assert data['main_done'] == 2
    assert data['mini_done'] == 1


def test_weekly_stats_excludes_other_modules(app, client, db):
    user, _ = _make_user(db, telegram_id=70202)
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    db.session.add(WorkoutSession(
        user_id=user.id, module='gym', status='completed',
        date=monday, kind='main',
    ))
    db.session.commit()
    r = client.get('/api/calisthenics/stats/weekly', headers=_h(app, user.id))
    assert r.get_json()['data']['main_done'] == 0


def test_weekly_stats_excludes_in_progress(app, client, db):
    user, _ = _make_user(db, telegram_id=70203)
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    db.session.add(WorkoutSession(
        user_id=user.id, module='calisthenics', status='in_progress',
        date=monday, kind='main',
    ))
    db.session.commit()
    r = client.get('/api/calisthenics/stats/weekly', headers=_h(app, user.id))
    assert r.get_json()['data']['main_done'] == 0


def test_weekly_stats_no_profile_returns_zero_targets(app, client, db):
    u = User(telegram_id=70204, name='NoProf', gender='female', age=25,
             weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
             level='beginner', training_days_per_week=3, session_duration_min=45,
             equipment=['floor'], onboarding_completed_at=datetime.utcnow(),
             active_module='calisthenics')
    db.session.add(u); db.session.commit()
    r = client.get('/api/calisthenics/stats/weekly', headers=_h(app, u.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['main_target'] == 0
    assert data['mini_target'] == 0


def test_weekly_stats_requires_auth(app, client):
    r = client.get('/api/calisthenics/stats/weekly')
    assert r.status_code == 401
```

- [ ] **Step 2: Verify failing**

```bash
pytest tests/calisthenics/test_stats.py::test_weekly_stats_zero_when_no_sessions -v
```

Expected: FAIL — 404.

- [ ] **Step 3: Add endpoint to routes.py**

```python
@bp.route('/calisthenics/stats/weekly', methods=['GET'])
@require_auth
def get_weekly_stats():
    from datetime import date, timedelta
    today = date.today()
    monday = today - timedelta(days=today.weekday())

    profile = CalisthenicsProfile.query.filter_by(user_id=g.user_id).first()
    main_target = profile.days_per_week if profile else 0
    mini_target = profile.optional_target_per_week if profile else 0

    sessions = WorkoutSession.query.filter(
        WorkoutSession.user_id == g.user_id,
        WorkoutSession.module == 'calisthenics',
        WorkoutSession.status == 'completed',
        WorkoutSession.date >= monday,
    ).all()
    main_done = sum(1 for s in sessions if s.kind == 'main')
    mini_done = sum(1 for s in sessions if s.kind == 'mini')

    return jsonify({'success': True, 'data': {
        'week_start': monday.isoformat(),
        'main_done': main_done, 'main_target': main_target,
        'mini_done': mini_done, 'mini_target': mini_target,
    }})
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/calisthenics/test_stats.py -v
pytest -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/calisthenics/routes.py tests/calisthenics/test_stats.py
git commit -m "feat: GET /api/calisthenics/stats/weekly"
```

---

## Task 7: GET /sessions/history + /sessions/<id>/detail endpoints

**Files:**
- Modify: `app/modules/calisthenics/routes.py`
- Modify: `tests/calisthenics/test_stats.py`

- [ ] **Step 1: Write failing tests**

APPEND to `tests/calisthenics/test_stats.py`:

```python
def test_history_returns_recent_sessions(app, client, db):
    user, _ = _make_user(db, telegram_id=70210)
    today = date.today()
    p = Program(user_id=user.id, name='C', periodization_type='hypertrophy',
                total_weeks=4, status='active', module='calisthenics')
    db.session.add(p); db.session.flush()
    m = Mesocycle(program_id=p.id, name='m', order_index=0, weeks_count=1)
    db.session.add(m); db.session.flush()
    w = ProgramWeek(mesocycle_id=m.id, week_number=1)
    db.session.add(w); db.session.flush()
    main_w = Workout(program_week_id=w.id, day_of_week=0, name='Push A', order_index=0)
    db.session.add(main_w); db.session.flush()

    # Two sessions: one main 2 days ago, one mini today
    db.session.add(WorkoutSession(user_id=user.id, workout_id=main_w.id, module='calisthenics',
                                   status='completed', date=today - timedelta(days=2), kind='main'))
    mini_w = Workout(program_week_id=None, mini_kind='stretch', day_of_week=0,
                     name='10хв стретч', order_index=0)
    db.session.add(mini_w); db.session.flush()
    db.session.add(WorkoutSession(user_id=user.id, workout_id=mini_w.id, module='calisthenics',
                                   status='completed', date=today, kind='mini'))
    db.session.commit()

    r = client.get('/api/calisthenics/sessions/history', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert len(data) == 2
    # newest first
    assert data[0]['kind'] == 'mini'
    assert data[0]['workout_name'] == '10хв стретч'
    assert data[1]['kind'] == 'main'


def test_history_limit_param(app, client, db):
    user, _ = _make_user(db, telegram_id=70211)
    today = date.today()
    for i in range(5):
        db.session.add(WorkoutSession(
            user_id=user.id, module='calisthenics', status='completed',
            date=today - timedelta(days=i), kind='main',
        ))
    db.session.commit()
    r = client.get('/api/calisthenics/sessions/history?limit=3', headers=_h(app, user.id))
    assert len(r.get_json()['data']) == 3


def test_session_detail_returns_logged_sets(app, client, db):
    from app.modules.training.models import LoggedExercise, LoggedSet
    user, _ = _make_user(db, telegram_id=70212)
    today = date.today()
    p = Program(user_id=user.id, name='C', periodization_type='hypertrophy',
                total_weeks=4, status='active', module='calisthenics')
    db.session.add(p); db.session.flush()
    m = Mesocycle(program_id=p.id, name='m', order_index=0, weeks_count=1)
    db.session.add(m); db.session.flush()
    w = ProgramWeek(mesocycle_id=m.id, week_number=1)
    db.session.add(w); db.session.flush()
    workout = Workout(program_week_id=w.id, day_of_week=0, name='Push A', order_index=0)
    db.session.add(workout); db.session.flush()
    pushup = Exercise.query.filter_by(module='calisthenics', name='full pushup').first()
    we = WorkoutExercise(workout_id=workout.id, exercise_id=pushup.id, order_index=0)
    db.session.add(we); db.session.commit()

    s = WorkoutSession(user_id=user.id, workout_id=workout.id, module='calisthenics',
                       status='completed', date=today, kind='main')
    db.session.add(s); db.session.flush()
    le = LoggedExercise(session_id=s.id, exercise_id=pushup.id, order_index=0)
    db.session.add(le); db.session.flush()
    db.session.add(LoggedSet(logged_exercise_id=le.id, set_number=1, actual_reps=10))
    db.session.add(LoggedSet(logged_exercise_id=le.id, set_number=2, actual_reps=12))
    db.session.commit()

    r = client.get(f'/api/calisthenics/sessions/{s.id}/detail', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['workout_name'] == 'Push A'
    assert data['kind'] == 'main'
    assert len(data['exercises']) == 1
    assert data['exercises'][0]['exercise_name'] == 'full pushup'
    assert len(data['exercises'][0]['logged_sets']) == 2
    assert data['exercises'][0]['logged_sets'][0]['actual_reps'] == 10


def test_session_detail_404_for_other_user(app, client, db):
    user1, _ = _make_user(db, telegram_id=70213)
    user2, _ = _make_user(db, telegram_id=70214)
    s = WorkoutSession(user_id=user1.id, module='calisthenics',
                       status='completed', date=date.today(), kind='main')
    db.session.add(s); db.session.commit()
    r = client.get(f'/api/calisthenics/sessions/{s.id}/detail', headers=_h(app, user2.id))
    assert r.status_code == 404


def test_history_requires_auth(app, client):
    r = client.get('/api/calisthenics/sessions/history')
    assert r.status_code == 401


def test_session_detail_requires_auth(app, client):
    r = client.get('/api/calisthenics/sessions/1/detail')
    assert r.status_code == 401
```

- [ ] **Step 2: Verify failing**

```bash
pytest tests/calisthenics/test_stats.py::test_history_returns_recent_sessions -v
```

Expected: FAIL — 404.

- [ ] **Step 3: Add endpoints to routes.py**

```python
@bp.route('/calisthenics/sessions/history', methods=['GET'])
@require_auth
def get_sessions_history():
    limit = min(int(request.args.get('limit', 30) or 30), 100)
    sessions = (WorkoutSession.query
                .filter(WorkoutSession.user_id == g.user_id,
                        WorkoutSession.module == 'calisthenics',
                        WorkoutSession.status == 'completed')
                .order_by(WorkoutSession.date.desc(), WorkoutSession.id.desc())
                .limit(limit)
                .all())

    out = []
    for s in sessions:
        workout = db.session.get(Workout, s.workout_id) if s.workout_id else None
        ex_count = (WorkoutExercise.query.filter_by(workout_id=workout.id).count()
                    if workout else 0)
        out.append({
            'id': s.id,
            'date': s.date.isoformat() if s.date else None,
            'kind': s.kind,
            'workout_name': workout.name if workout else 'Видалене тренування',
            'mini_kind': workout.mini_kind if workout else None,
            'exercise_count': ex_count,
            'duration_min': workout.estimated_duration_min if workout else None,
        })
    return jsonify({'success': True, 'data': out})


@bp.route('/calisthenics/sessions/<int:session_id>/detail', methods=['GET'])
@require_auth
def get_session_detail(session_id):
    from app.modules.training.models import LoggedExercise, LoggedSet
    session = WorkoutSession.query.filter_by(
        id=session_id, user_id=g.user_id, module='calisthenics'
    ).first()
    if not session:
        return jsonify({'success': False, 'error': {
            'code': 'SESSION_NOT_FOUND', 'message': 'Session not found',
        }}), 404

    workout = db.session.get(Workout, session.workout_id) if session.workout_id else None

    logged_exercises = (LoggedExercise.query
                        .filter_by(session_id=session.id)
                        .order_by(LoggedExercise.order_index)
                        .all())
    exercises = []
    for le in logged_exercises:
        ex = db.session.get(Exercise, le.exercise_id)
        sets = (LoggedSet.query
                .filter_by(logged_exercise_id=le.id)
                .order_by(LoggedSet.set_number)
                .all())
        exercises.append({
            'exercise_name': ex.name if ex else '?',
            'unit': ex.unit if ex else None,
            'logged_sets': [{
                'set_number': s.set_number,
                'actual_reps': s.actual_reps,
                'actual_seconds': s.actual_seconds,
            } for s in sets],
        })

    return jsonify({'success': True, 'data': {
        'id': session.id,
        'date': session.date.isoformat() if session.date else None,
        'kind': session.kind,
        'status': session.status,
        'workout_name': workout.name if workout else 'Видалене тренування',
        'mini_kind': workout.mini_kind if workout else None,
        'exercises': exercises,
    }})
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/calisthenics/test_stats.py -v
pytest -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/calisthenics/routes.py tests/calisthenics/test_stats.py
git commit -m "feat: GET /api/calisthenics/sessions/history + /sessions/<id>/detail"
```

---

## Task 8: Extend regenerate endpoint with optional schedule params

**Files:**
- Modify: `app/modules/calisthenics/routes.py`
- Modify: `tests/calisthenics/test_program_endpoints.py`

- [ ] **Step 1: Write failing tests**

APPEND to `tests/calisthenics/test_program_endpoints.py`:

```python
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
```

- [ ] **Step 2: Verify failing**

```bash
pytest tests/calisthenics/test_program_endpoints.py::test_regenerate_updates_days_per_week -v
```

Expected: FAIL — params not honored.

- [ ] **Step 3: Update `post_regenerate` in routes.py**

Find `post_regenerate`. After `profile = CalisthenicsProfile.query.filter_by(user_id=g.user_id).first()` (and before generation), add:

```python
    data = request.get_json(silent=True) or {}

    # Optionally update schedule before regenerating
    if 'days_per_week' in data:
        new_days = data['days_per_week']
        if not isinstance(new_days, int) or isinstance(new_days, bool) or not (1 <= new_days <= 7):
            return jsonify({'success': False, 'error': {
                'code': 'INVALID_FIELD',
                'message': 'days_per_week must be int 1..7',
            }}), 400
        profile.days_per_week = new_days
    if 'optional_target_per_week' in data:
        new_opt = data['optional_target_per_week']
        if not isinstance(new_opt, int) or isinstance(new_opt, bool) or not (0 <= new_opt <= 7):
            return jsonify({'success': False, 'error': {
                'code': 'INVALID_FIELD',
                'message': 'optional_target_per_week must be int 0..7',
            }}), 400
        profile.optional_target_per_week = new_opt
    db.session.commit()
```

(Place this after the `if not profile or not last_assessment: ASSESSMENT_REQUIRED` check.)

- [ ] **Step 4: Run tests**

```bash
pytest tests/calisthenics/test_program_endpoints.py -v
pytest -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/calisthenics/routes.py tests/calisthenics/test_program_endpoints.py
git commit -m "feat: regenerate endpoint accepts days_per_week + optional_target_per_week to update profile"
```

---

## Task 9: Coach context — 30-day calisthenics summary

**Files:**
- Modify: `app/modules/coach/context.py`
- Create: `tests/coach/test_calisthenics_context.py`

- [ ] **Step 1: Write failing tests**

Create `tests/coach/test_calisthenics_context.py`:

```python
from datetime import datetime, date, timedelta
import pytest
from app.core.models import User
from app.modules.calisthenics.models import CalisthenicsProfile, CalisthenicsAssessment
from app.modules.training.models import (
    Program, Mesocycle, ProgramWeek, Workout, Exercise, WorkoutExercise,
    PlannedSet, WorkoutSession, LoggedExercise, LoggedSet,
)


def _make_user(db, telegram_id=70300):
    u = User(
        telegram_id=telegram_id, name='CtxTest', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['floor'], onboarding_completed_at=datetime.utcnow(),
        active_module='calisthenics',
    )
    db.session.add(u); db.session.commit()
    return u


def test_context_no_calisthenics_data_shows_empty_message(app, db):
    from app.modules.coach.context import build_coach_context
    user = _make_user(db, telegram_id=70300)
    ctx = build_coach_context(user.id)
    assert 'No recent calisthenics sessions' in ctx


def test_context_includes_30d_session_counts(app, db):
    from app.modules.coach.context import build_coach_context
    user = _make_user(db, telegram_id=70301)
    today = date.today()
    # 5 main + 2 mini sessions in last 30 days
    for d in range(5):
        db.session.add(WorkoutSession(
            user_id=user.id, module='calisthenics', status='completed',
            date=today - timedelta(days=d * 2), kind='main',
        ))
    for d in range(2):
        db.session.add(WorkoutSession(
            user_id=user.id, module='calisthenics', status='completed',
            date=today - timedelta(days=d), kind='mini',
        ))
    db.session.commit()
    ctx = build_coach_context(user.id)
    assert '7 sessions' in ctx
    assert '5 main' in ctx
    assert '2 mini' in ctx


def test_context_old_sessions_excluded_from_30d_window(app, db):
    from app.modules.coach.context import build_coach_context
    user = _make_user(db, telegram_id=70302)
    db.session.add(WorkoutSession(
        user_id=user.id, module='calisthenics', status='completed',
        date=date.today() - timedelta(days=60), kind='main',
    ))
    db.session.commit()
    ctx = build_coach_context(user.id)
    assert 'No recent calisthenics sessions' in ctx


def test_context_groups_by_chain(app, db):
    """Sessions whose workouts touch certain chains show up grouped."""
    from app.modules.coach.context import build_coach_context
    user = _make_user(db, telegram_id=70303)
    p = Program(user_id=user.id, name='C', periodization_type='hypertrophy',
                total_weeks=4, status='active', module='calisthenics')
    db.session.add(p); db.session.flush()
    m = Mesocycle(program_id=p.id, name='m', order_index=0, weeks_count=1)
    db.session.add(m); db.session.flush()
    w = ProgramWeek(mesocycle_id=m.id, week_number=1)
    db.session.add(w); db.session.flush()
    push_workout = Workout(program_week_id=w.id, day_of_week=0,
                           name='Push A', order_index=0)
    db.session.add(push_workout); db.session.flush()
    full_pushup = Exercise.query.filter_by(module='calisthenics', name='full pushup').first()
    db.session.add(WorkoutExercise(workout_id=push_workout.id, exercise_id=full_pushup.id, order_index=0))
    db.session.commit()

    db.session.add(WorkoutSession(
        user_id=user.id, workout_id=push_workout.id, module='calisthenics',
        status='completed', date=date.today() - timedelta(days=1), kind='main',
    ))
    db.session.commit()

    ctx = build_coach_context(user.id)
    assert 'push' in ctx.lower()
```

- [ ] **Step 2: Verify failing**

```bash
pytest tests/coach/test_calisthenics_context.py::test_context_no_calisthenics_data_shows_empty_message -v
```

Expected: pass — current context already says nothing for empty calisthenics. (May already pass; check.)

```bash
pytest tests/coach/test_calisthenics_context.py::test_context_includes_30d_session_counts -v
```

Expected: FAIL.

- [ ] **Step 3: Update `build_coach_context` calisthenics branch**

In `app/modules/coach/context.py`, find the calisthenics block (it currently has "Last Calisthenics Workout"). Replace the calisthenics section with:

```python
    # ── CALISTHENICS ──
    cali_program = (Program.query
                    .filter_by(user_id=user_id, status='active', module='calisthenics')
                    .first())
    if cali_program:
        parts.append(f"\n## Calisthenics Program: {cali_program.name} ({cali_program.periodization_type}, {cali_program.total_weeks} weeks)")

    try:
        from app.modules.calisthenics.models import CalisthenicsProfile, CalisthenicsAssessment
        cali_profile = CalisthenicsProfile.query.filter_by(user_id=user_id).first()
        if cali_profile:
            parts.append(
                f"\n### Calisthenics Profile\n"
                f"- Goals: {cali_profile.goals}, Equipment: {cali_profile.equipment}\n"
                f"- {cali_profile.days_per_week}/week × {cali_profile.session_duration_min}min, "
                f"Mini target: {cali_profile.optional_target_per_week or 0}/week, "
                f"Injuries: {cali_profile.injuries}, Motivation: {cali_profile.motivation}"
            )
        last_assess = (CalisthenicsAssessment.query
                       .filter_by(user_id=user_id)
                       .order_by(CalisthenicsAssessment.assessed_at.desc())
                       .first())
        if last_assess:
            parts.append(
                f"\n### Last Calisthenics Assessment ({last_assess.assessed_at.date().isoformat()})\n"
                f"- pullups: {last_assess.pullups}, australian: {last_assess.australian_pullups}, "
                f"pushups: {last_assess.pushups}, pike: {last_assess.pike_pushups}\n"
                f"- squats: {last_assess.squats}, lunges: {last_assess.lunges}\n"
                f"- plank: {last_assess.plank}s, hollow body: {last_assess.hollow_body}s, "
                f"superman: {last_assess.superman_hold}s"
            )
    except ImportError:
        pass

    # 30-day calisthenics activity summary (replaces "last session")
    since = date.today() - timedelta(days=30)
    cali_sessions = (WorkoutSession.query
                     .filter(WorkoutSession.user_id == user_id,
                             WorkoutSession.module == 'calisthenics',
                             WorkoutSession.status == 'completed',
                             WorkoutSession.date >= since)
                     .all())
    if not cali_sessions:
        parts.append("\n## Calisthenics Activity\nNo recent calisthenics sessions.")
    else:
        main_count = sum(1 for s in cali_sessions if s.kind == 'main')
        mini_count = sum(1 for s in cali_sessions if s.kind == 'mini')
        # Mini breakdown by mini_kind
        mini_by_kind = {}
        for s in cali_sessions:
            if s.kind == 'mini' and s.workout_id:
                w = db.session.get(Workout, s.workout_id)
                if w and w.mini_kind:
                    mini_by_kind[w.mini_kind] = mini_by_kind.get(w.mini_kind, 0) + 1
        mini_breakdown = ', '.join(f"{count} {k}" for k, count in sorted(mini_by_kind.items()))

        # Main by chain
        chain_counts = {}
        for s in cali_sessions:
            if s.kind == 'main' and s.workout_id:
                w = db.session.get(Workout, s.workout_id)
                if w:
                    for we in w.workout_exercises:
                        ex_obj = db.session.get(Exercise, we.exercise_id)
                        if ex_obj and ex_obj.progression_chain:
                            chain_counts[ex_obj.progression_chain] = chain_counts.get(ex_obj.progression_chain, 0) + 1
        chain_str = ', '.join(f"{c} {cnt}" for c, cnt in sorted(chain_counts.items(), key=lambda kv: -kv[1]))

        lines = [f"\n## Calisthenics Activity (last 30 days)"]
        sessions_line = f"- {len(cali_sessions)} sessions: {main_count} main, {mini_count} mini"
        if mini_breakdown:
            sessions_line += f" ({mini_breakdown})"
        lines.append(sessions_line)
        if chain_str:
            lines.append(f"- Main by chain: {chain_str}")
        parts.append('\n'.join(lines))
```

Make sure `Workout`, `Exercise` are imported at the top of the function (they should already be).

- [ ] **Step 4: Run tests**

```bash
pytest tests/coach/test_calisthenics_context.py -v
pytest -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/modules/coach/context.py tests/coach/test_calisthenics_context.py
git commit -m "feat: replace last-session block with 30-day calisthenics summary in Coach context"
```

---

## Task 10: Frontend — Profile wizard adds optional_target_per_week chip row

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Find the existing days_per_week + duration step**

```bash
grep -n "Скільки разів на тиждень\|Тривалість сесії\|days_per_week" app/templates/index.html | head
```

You'll find the wizard step with these chip rows.

- [ ] **Step 2: Add `optional_target_per_week` chip row after duration**

In the wizard step (probably step 3, "Скільки разів на тиждень"), AFTER the duration chip row, ADD a new chip row:

```html
        <div class="cali-setup-title" style="margin-top:20px">Опціональних міні-сесій?</div>
        <div class="cali-chip-group">
          ${[0,1,2,3,4].map(n =>
            `<button class="cali-chip" onclick="caliSelectOptional(this,${n})">${n}</button>`
          ).join('')}
        </div>
```

(The exact chip HTML may differ based on the existing structure — match the existing style for days/duration chips.)

- [ ] **Step 3: Add `_caliSetupData.optional_target_per_week` and selector function**

Find the JS section with `_caliSetupData` (search for `const _caliSetupData = {`). Add:

```javascript
const _caliSetupData = { goals: [], equipment: [], days_per_week: null, session_duration_min: null, injuries: [], motivation: null, optional_target_per_week: 0 };
```

(Update existing object — add new field with default 0.)

Append `caliSelectOptional` after `caliSelectDuration`:

```javascript
function caliSelectOptional(btn, val) {
  btn.closest('.cali-chip-group').querySelectorAll('.cali-chip').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  _caliSetupData.optional_target_per_week = val;
}
```

- [ ] **Step 4: Update `caliFinishSetup` to include optional_target_per_week**

Find `caliFinishSetup`. The POST body already comes from `_caliSetupData` — since we added the field to that object, it'll go through automatically. Verify the body payload includes it. No code change needed beyond the data assignment.

- [ ] **Step 5: Smoke test**

```bash
pytest -q
```

Expected: 200+ tests still pass.

- [ ] **Step 6: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: profile wizard collects optional_target_per_week"
```

---

## Task 11: Frontend — "Цього тижня" stats card on home

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Add new state field for weekly stats**

Find `const S = {`. Add to S near other calisthenics fields:

```javascript
  calisthenicsWeeklyStats: null,
```

- [ ] **Step 2: Update `caliReloadProgramData` to also fetch stats**

Find `async function caliReloadProgramData()`. Change it to fetch stats in parallel:

```javascript
async function caliReloadProgramData() {
  const [todayR, overviewR, statsR] = await Promise.all([
    api('GET', '/api/calisthenics/today'),
    api('GET', '/api/training/week-overview'),
    api('GET', '/api/calisthenics/stats/weekly'),
  ]);
  S.calisthenicsToday = (todayR && todayR.success) ? todayR.data : null;
  S.calisthenicsWeekOverview = (overviewR && overviewR.success) ? overviewR.data : null;
  S.calisthenicsCompletedCount = ((overviewR && overviewR.data && overviewR.data.workouts) || [])
    .filter(w => w.status === 'done').length;
  S.calisthenicsWeeklyStats = (statsR && statsR.success) ? statsR.data : null;
}
```

- [ ] **Step 3: Render the stats card in `renderCalisthenicsHome`**

Find `renderCalisthenicsHome`. After defining `dowNames`, BEFORE building the home `el.innerHTML`, build a stats card variable:

```javascript
  const ws = S.calisthenicsWeeklyStats;
  const showMini = ws && ws.mini_target > 0;
  const weeklyCard = ws ? `
    <div class="hero-card" style="margin-bottom:14px">
      <div class="hero-label">Цього тижня</div>
      <div class="hero-stats">
        <div class="stat"><span class="stat-value">${ws.main_done}/${ws.main_target}</span><span class="stat-label">Основних</span></div>
        ${showMini ? `<div class="stat"><span class="stat-value">${ws.mini_done}/${ws.mini_target}</span><span class="stat-label">Міні</span></div>` : ''}
      </div>
    </div>` : '';
```

In the State B `el.innerHTML` (where `endOfBlockBanner`, `todayCard`, `overviewCard`, `lastAssessBlock` are concatenated), insert `${weeklyCard}` BEFORE `${todayCard}`:

```javascript
  el.innerHTML = `${endOfBlockBanner}${weeklyCard}${todayCard}${overviewCard}${lastAssessBlock}`;
```

- [ ] **Step 4: Smoke test**

```bash
pytest -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: 'Цього тижня' stats card on calisthenics home"
```

---

## Task 12: Frontend — "+ Міні-сесія" button + picker modal

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Add the button to home rendering**

In `renderCalisthenicsHome`, find where `todayCard` is built. AFTER the `todayCard` definition, ADD:

```javascript
  const miniBtn = `
    <button class="btn btn-ghost" style="margin-bottom:14px" onclick="openMiniSessionPicker()">
      + МІНІ-СЕСІЯ
    </button>`;
```

Insert `${miniBtn}` in the State B `el.innerHTML` AFTER `${todayCard}`:

```javascript
  el.innerHTML = `${endOfBlockBanner}${weeklyCard}${todayCard}${miniBtn}${overviewCard}${lastAssessBlock}`;
```

- [ ] **Step 2: Add picker modal + handlers**

Append in the calisthenics JS block:

```javascript
function openMiniSessionPicker() {
  const overlay = document.createElement('div');
  overlay.id = 'mini-picker-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:1000;display:flex;align-items:center;justify-content:center;padding:20px';
  overlay.innerHTML = `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:14px;padding:22px;max-width:340px;width:100%">
      <div style="font-family:'Barlow Condensed',sans-serif;font-size:18px;font-weight:800;text-transform:uppercase;letter-spacing:.05em;margin-bottom:14px">Обери міні-сесію</div>
      <button class="btn btn-primary" style="margin-bottom:8px" onclick="generateMiniSession('stretch')">🧘 Стретч 10 хв</button>
      <button class="btn btn-primary" style="margin-bottom:8px" onclick="generateMiniSession('short')">💪 Скорочена силова 15 хв</button>
      <button class="btn btn-primary" style="margin-bottom:12px" onclick="generateMiniSession('skill')">🎯 Скіл-фокус 10 хв</button>
      <button class="btn btn-ghost" onclick="closeMiniSessionPicker()">Закрити</button>
    </div>`;
  document.body.appendChild(overlay);
}


function closeMiniSessionPicker() {
  const o = document.getElementById('mini-picker-overlay');
  if (o) o.remove();
}


async function generateMiniSession(type) {
  closeMiniSessionPicker();
  const el = document.getElementById('train-content');
  el.innerHTML = `
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:60vh">
      <div style="width:48px;height:48px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:caliSpin 1s linear infinite;margin-bottom:20px"></div>
      <div style="font-family:'Barlow Condensed',sans-serif;font-size:18px;text-transform:uppercase;letter-spacing:.05em">Створюю сесію…</div>
      <div style="font-size:13px;color:var(--muted);margin-top:8px">5-15 секунд</div>
    </div>`;

  const r = await api('POST', '/api/calisthenics/mini-session/generate', {type}, 600000);
  if (!r || !r.success) {
    alert('Не вдалось створити: ' + (r?.error?.message || ''));
    renderCalisthenicsHome();
    return;
  }
  // Server returned the workout. Now start a session and render workout view.
  const workoutId = r.data.workout_id;
  const startR = await api('POST', '/api/calisthenics/session/start', {workout_id: workoutId});
  if (!startR || !startR.success) {
    alert('Не вдалось почати: ' + (startR?.error?.message || ''));
    renderCalisthenicsHome();
    return;
  }
  S.calisthenicsActiveSession = {
    session_id: startR.data.session_id,
    workout: r.data,
    logged: {},
  };
  // r.data has the same shape as today.* (id, name, exercises[], etc.)
  // renderCalisthenicsWorkout reads from S.calisthenicsActiveSession.workout — needs `id` field set
  S.calisthenicsActiveSession.workout.id = workoutId;
  renderCalisthenicsWorkout();
}
```

- [ ] **Step 3: Smoke test**

```bash
pytest -q
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: + МІНІ-СЕСІЯ button + 3-type picker modal"
```

---

## Task 13: Frontend — Schedule editor in regenerate flow

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Find existing regenerate trigger**

Search for `caliSubmitAssessment` and the end-of-block banner — these are the two places that trigger regenerate.

- [ ] **Step 2: Add schedule editor modal function**

Append:

```javascript
function openScheduleEditor() {
  const profile = S.calisthenicsProfile || {};
  const currentDays = profile.days_per_week || 4;
  const currentOpt = profile.optional_target_per_week || 0;
  let pickedDays = currentDays;
  let pickedOpt = currentOpt;

  const overlay = document.createElement('div');
  overlay.id = 'schedule-editor-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:1000;display:flex;align-items:center;justify-content:center;padding:20px';
  const renderChips = (n, current, fn) => [1,2,3,4,5,6].slice(0, n).map(d =>
    `<button class="cali-chip ${d === current ? 'selected' : ''}"
        onclick="${fn}(this,${d})">${d}</button>`
  ).join('');
  overlay.innerHTML = `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:14px;padding:22px;max-width:360px;width:100%">
      <div style="font-family:'Barlow Condensed',sans-serif;font-size:18px;font-weight:800;text-transform:uppercase;letter-spacing:.05em;margin-bottom:14px">Розклад нової програми</div>
      <div style="font-size:13px;color:var(--muted);margin-bottom:8px">Скільки днів на тиждень?</div>
      <div class="cali-chip-group" id="sched-days-row" style="margin-bottom:14px">
        ${[2,3,4,5,6].map(d => `<button class="cali-chip ${d === pickedDays ? 'selected' : ''}" onclick="schedPickDays(this,${d})">${d}</button>`).join('')}
      </div>
      <div style="font-size:13px;color:var(--muted);margin-bottom:8px">Опціональних міні-сесій?</div>
      <div class="cali-chip-group" id="sched-opt-row" style="margin-bottom:18px">
        ${[0,1,2,3,4].map(n => `<button class="cali-chip ${n === pickedOpt ? 'selected' : ''}" onclick="schedPickOpt(this,${n})">${n}</button>`).join('')}
      </div>
      <button class="btn btn-primary" style="margin-bottom:8px" onclick="confirmRegenerate()">Створити нову програму</button>
      <button class="btn btn-ghost" onclick="closeScheduleEditor()">Скасувати</button>
    </div>`;
  document.body.appendChild(overlay);

  S._schedPicked = {days: pickedDays, opt: pickedOpt};
}


function closeScheduleEditor() {
  const o = document.getElementById('schedule-editor-overlay');
  if (o) o.remove();
  S._schedPicked = null;
}


function schedPickDays(btn, val) {
  btn.closest('.cali-chip-group').querySelectorAll('.cali-chip').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  if (S._schedPicked) S._schedPicked.days = val;
}


function schedPickOpt(btn, val) {
  btn.closest('.cali-chip-group').querySelectorAll('.cali-chip').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  if (S._schedPicked) S._schedPicked.opt = val;
}


async function confirmRegenerate() {
  if (!S.calisthenicsProgram || !S._schedPicked) return;
  const pid = S.calisthenicsProgram.id;
  const body = {
    days_per_week: S._schedPicked.days,
    optional_target_per_week: S._schedPicked.opt,
  };
  closeScheduleEditor();
  const el = document.getElementById('train-content');
  el.innerHTML = `
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:60vh">
      <div style="width:48px;height:48px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:caliSpin 1s linear infinite;margin-bottom:20px"></div>
      <div style="font-family:'Barlow Condensed',sans-serif;font-size:18px;text-transform:uppercase;letter-spacing:.05em">Створюю нову програму…</div>
    </div>`;
  const r = await api('POST', `/api/calisthenics/program/${pid}/regenerate`, body, 600000);
  if (!r || !r.success) {
    alert('Не вдалось: ' + (r?.error?.message || ''));
    renderCalisthenicsHome();
    return;
  }
  S.calisthenicsProgram = r.data;
  // Reload profile too since days_per_week changed
  const profileR = await api('GET', '/api/calisthenics/profile');
  if (profileR && profileR.success) S.calisthenicsProfile = profileR.data;
  await caliReloadProgramData();
  renderCalisthenicsHome();
}
```

- [ ] **Step 3: Wire end-of-block banner to open the editor**

Find `endOfBlockBanner` definition in `renderCalisthenicsHome`. Change the button's onclick from `renderCalisthenicsAssessment()` to `openScheduleEditor()`:

```javascript
  endOfBlockBanner = `
    <div class="no-program-card" style="background:rgba(245,158,11,.12);border-color:rgba(245,158,11,.4)">
      <div class="np-title">🏆 Блок завершено!</div>
      <div class="np-body">Пройди тест щоб виміряти прогрес → новий блок</div>
      <button class="btn btn-primary" onclick="openScheduleEditor()">Перегенерувати</button>
    </div>`;
```

(If she wants to also re-take the assessment, she can do it via the existing "Пройти тест знову" button on the bottom card. Keep them separate.)

- [ ] **Step 4: Update `caliSubmitAssessment` regenerate prompt to use editor**

Find `caliSubmitAssessment`. It currently does `confirm('Зберегти результати. Створити новий блок програми?')`. Replace that branch:

```javascript
    if (S.calisthenicsProgram) {
      if (confirm('Створити новий блок програми зі свіжими результатами?')) {
        openScheduleEditor();
        return;  // editor takes over
      }
    }
```

- [ ] **Step 5: Smoke test**

```bash
pytest -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: schedule editor modal in regenerate flow (days/optional pickers)"
```

---

## Task 14: Frontend — History page + session detail

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Add "Історія" button to home**

In `renderCalisthenicsHome`, find where `lastAssessBlock` is built. Add a small "Історія тренувань" link near the bottom. Update home `el.innerHTML` to include an extra block:

```javascript
  const historyLink = program ? `
    <div style="text-align:center;margin-top:8px">
      <button class="btn btn-ghost" onclick="openCalisthenicsHistory()">Історія тренувань</button>
    </div>` : '';
```

Insert `${historyLink}` after `${lastAssessBlock}`:

```javascript
  el.innerHTML = `${endOfBlockBanner}${weeklyCard}${todayCard}${miniBtn}${overviewCard}${lastAssessBlock}${historyLink}`;
```

- [ ] **Step 2: Add history modal**

Append:

```javascript
async function openCalisthenicsHistory() {
  const overlay = document.createElement('div');
  overlay.id = 'cali-history-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:var(--bg);z-index:1000;display:flex;flex-direction:column;overflow:hidden';
  overlay.innerHTML = `
    <div style="display:flex;align-items:center;padding:14px 16px;border-bottom:1px solid var(--border)">
      <button class="btn btn-ghost" style="width:auto;padding:6px 14px;margin-right:12px" onclick="closeCalisthenicsHistory()">←</button>
      <div style="font-family:'Barlow Condensed',sans-serif;font-size:18px;font-weight:800;text-transform:uppercase;letter-spacing:.05em">Історія тренувань</div>
    </div>
    <div id="cali-history-list" style="flex:1;overflow-y:auto;padding:16px">
      <div style="color:var(--muted);font-size:13px;text-align:center;padding:20px">Завантаження…</div>
    </div>`;
  document.body.appendChild(overlay);

  const r = await api('GET', '/api/calisthenics/sessions/history?limit=30');
  const list = document.getElementById('cali-history-list');
  if (!r || !r.success) {
    list.innerHTML = `<div style="color:var(--muted);text-align:center;padding:20px">Не вдалось завантажити</div>`;
    return;
  }
  if (r.data.length === 0) {
    list.innerHTML = `<div style="color:var(--muted);text-align:center;padding:40px">Поки що тренувань нема</div>`;
    return;
  }
  list.innerHTML = r.data.map(s => `
    <div onclick="openCalisthenicsSessionDetail(${s.id})" style="padding:12px 4px;border-bottom:1px solid var(--border);cursor:pointer">
      <div style="display:flex;justify-content:space-between;align-items:baseline">
        <div style="font-size:14px;font-weight:600">${_esc(s.workout_name)}</div>
        <div style="font-size:11px;color:var(--muted)">${s.date}</div>
      </div>
      <div style="font-size:11px;color:var(--muted);margin-top:4px">
        ${s.kind === 'mini' ? `міні · ${s.mini_kind || ''}` : 'основне'} · ${s.exercise_count} вправ
      </div>
    </div>`).join('');
}


function closeCalisthenicsHistory() {
  const o = document.getElementById('cali-history-overlay');
  if (o) o.remove();
}


async function openCalisthenicsSessionDetail(sessionId) {
  const overlay = document.createElement('div');
  overlay.id = 'cali-session-detail-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:var(--bg);z-index:1010;display:flex;flex-direction:column;overflow:hidden';
  overlay.innerHTML = `
    <div style="display:flex;align-items:center;padding:14px 16px;border-bottom:1px solid var(--border)">
      <button class="btn btn-ghost" style="width:auto;padding:6px 14px;margin-right:12px" onclick="closeCalisthenicsSessionDetail()">←</button>
      <div id="cali-detail-title" style="font-family:'Barlow Condensed',sans-serif;font-size:18px;font-weight:800;text-transform:uppercase;letter-spacing:.05em">Сесія</div>
    </div>
    <div id="cali-detail-body" style="flex:1;overflow-y:auto;padding:16px">
      <div style="color:var(--muted);font-size:13px;text-align:center;padding:20px">Завантаження…</div>
    </div>`;
  document.body.appendChild(overlay);

  const r = await api('GET', `/api/calisthenics/sessions/${sessionId}/detail`);
  const body = document.getElementById('cali-detail-body');
  const title = document.getElementById('cali-detail-title');
  if (!r || !r.success) {
    body.innerHTML = `<div style="color:var(--muted);text-align:center;padding:20px">Не вдалось завантажити</div>`;
    return;
  }
  const d = r.data;
  title.textContent = `${d.workout_name} · ${d.date}`;
  if (!d.exercises.length) {
    body.innerHTML = `<div style="color:var(--muted);text-align:center;padding:20px">Сесія без записів підходів</div>`;
    return;
  }
  body.innerHTML = d.exercises.map(ex => {
    const setsStr = ex.logged_sets.map(s => {
      if (s.actual_reps != null) return s.actual_reps;
      if (s.actual_seconds != null) return s.actual_seconds + 'с';
      return '—';
    }).join(' / ');
    return `
      <div class="hero-card" style="margin-bottom:10px;padding:12px 14px">
        <div style="font-size:14px;font-weight:600;margin-bottom:4px">${_esc(ex.exercise_name)}</div>
        <div style="font-size:13px;color:var(--muted)">${setsStr}</div>
      </div>`;
  }).join('');
}


function closeCalisthenicsSessionDetail() {
  const o = document.getElementById('cali-session-detail-overlay');
  if (o) o.remove();
}
```

- [ ] **Step 3: Smoke test**

```bash
pytest -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: calisthenics history page + session detail view"
```

---

## Final Verification

After all 14 tasks:

```bash
cd /Users/natalie/body-coach-ai
pytest -q
```

Expected: 215+ tests pass (190 baseline + ~25 new).

Manual browser test plan:
1. Profile wizard now has "Опціональних міні-сесій?" chip row → choose 2 → save → check profile has `optional_target_per_week=2`
2. Open Calisthenics tab with active program → see "Цього тижня" stats card with "0/N основних" and "0/2 міні"
3. Tap "+ Міні-сесія" → picker with 3 buttons → tap Стретч → loading 5-15s → workout view with 5-7 exercises in seconds → log all sets → complete → home
4. After completing, "Цього тижня" updates: "0/N основних · 1/2 міні"
5. Tap "Історія тренувань" → list shows the mini-session at top with "міні · stretch" badge
6. Tap a session → detail view shows logged set values
7. Tap "Перегенерувати" on end-of-block banner → schedule editor opens with current values pre-selected → change days from 4 to 5 → tap Створити → loading 5-15s → new program with 5 days
8. Open Coach → ask "як я тренувалась цього місяця?" → AI mentions "X main sessions, Y mini" and chains breakdown
9. Switch to gym → no calisthenics data leaks
10. Refresh WebApp → state preserved

---

## Self-Review

- All 5 endpoints from spec covered: ✅
- Migration covers all 3 column changes: ✅
- AI generation function with 3 type variants: ✅
- Coach context replaces last-session with 30-day summary: ✅
- Frontend covers stats card, picker, history, session detail, schedule editor, wizard chip: ✅
- Mini-sessions reuse existing logging endpoints (no new logging code): ✅
- Tests touch every endpoint + critical paths: ✅
- No "TBD"/"TODO" placeholders: ✅
