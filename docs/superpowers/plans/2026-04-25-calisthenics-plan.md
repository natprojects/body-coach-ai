# Calisthenics Plan Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate, run, and progressively evolve calisthenics training programs alongside the existing gym module, with strict data-level isolation between the two.

**Architecture:** Reuse the existing `Program → Mesocycle → ProgramWeek → Workout → WorkoutExercise → PlannedSet` hierarchy. Add a `module` discriminator column on `programs` / `workout_sessions` / `exercises` and filter every query by `module = user.active_module`. Calisthenics generation lives in its own coach module but produces the same JSON shape, restricted to a closed set of seeded progression exercises. Level-up is deterministic (no AI) — triggered after a session if AMRAP results pass thresholds across the last 3 sessions.

**Note on spec deviation:** The spec's §3 mentioned a new `is_active` boolean. Implementation uses the existing `Program.status` column instead (`'active'` vs `'completed'`) — semantically identical, no migration needed for that field.

**Tech Stack:** Flask, SQLAlchemy, SQLite, Alembic, Anthropic API (existing wrapper in `app/core/ai.py`), Vanilla JS (Telegram Mini App).

---

## File Map

### Backend
- **Modify:** `app/modules/training/models.py` — add `module` to `Program`, `WorkoutSession`, `Exercise`; add `progression_chain`, `progression_level`, `unit` to `Exercise`; add `is_amrap`, `target_seconds` to `PlannedSet`
- **Create:** `migrations/versions/<rev>_add_calisthenics_plan_columns_and_seeds.py` — column additions + seed insertion of ~45 calisthenics exercises
- **Modify:** `app/modules/training/routes.py` — add module filter to existing queries; add `GET /api/training/week-overview` (universal)
- **Modify:** `app/modules/calisthenics/routes.py` — add 8 new endpoints
- **Create:** `app/modules/calisthenics/coach.py` — `generate_calisthenics_program()` + `save_calisthenics_program_from_dict()`
- **Create:** `app/modules/calisthenics/level_up.py` — `compute_level_up_suggestions()` pure function
- **Modify:** `app/modules/calisthenics/__init__.py` — register the new submodules

### Frontend
- **Modify:** `app/templates/index.html` — Calisthenics home states (B/C), workout view, level-up dialog, "Other workout" picker, Program-tab integration

### Tests
- **Create:** `tests/calisthenics/test_program_generation.py`
- **Create:** `tests/calisthenics/test_program_endpoints.py`
- **Create:** `tests/calisthenics/test_level_up.py`
- **Create:** `tests/calisthenics/test_module_isolation.py`
- **Modify:** `tests/training/test_program_routes.py` — module-isolation regression tests

### Docs
- **Create:** `docs/calisthenics_progressions.md`

---

## Task 1: DB migration — module/progression columns + exercise seeds

**Files:**
- Modify: `app/modules/training/models.py`
- Create: `migrations/versions/h8i9j0k1l2m3_add_calisthenics_plan.py`

- [ ] **Step 1: Add fields to `Program`**

In `app/modules/training/models.py`, change the `Program` class to add `module`:

```python
class Program(db.Model):
    __tablename__ = 'programs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    periodization_type = db.Column(db.String(20), nullable=False)
    total_weeks = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='active')
    module = db.Column(db.String(20), default='gym', nullable=False, server_default='gym')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    mesocycles = db.relationship('Mesocycle', backref='program', order_by='Mesocycle.order_index',
                                 cascade='all, delete-orphan')
```

- [ ] **Step 2: Add fields to `WorkoutSession`**

Find the `WorkoutSession` class. Add `module` near the existing columns:

```python
    module = db.Column(db.String(20), default='gym', nullable=False, server_default='gym')
```

- [ ] **Step 3: Add fields to `Exercise`**

Find the `Exercise` class. Add the four new columns:

```python
    module = db.Column(db.String(20), default='gym', nullable=False, server_default='gym')
    progression_chain = db.Column(db.String(30))     # 'push' | 'pull' | 'squat' | 'core_dynamic' | 'core_static' | 'lunge'
    progression_level = db.Column(db.Integer)         # 0..N within chain
    unit = db.Column(db.String(10))                   # 'reps' | 'seconds'
```

- [ ] **Step 4: Add fields to `PlannedSet`**

Find the `PlannedSet` class. Add:

```python
    is_amrap = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    target_seconds = db.Column(db.Integer)
```

- [ ] **Step 5: Create the migration file**

First, check the current head:

```bash
cd /Users/natalie/body-coach-ai
flask db current
```

Note the current head revision string and use it as `down_revision`.

Create `migrations/versions/h8i9j0k1l2m3_add_calisthenics_plan.py`:

```python
"""add calisthenics plan columns and seed exercises

Revision ID: h8i9j0k1l2m3
Revises: <REPLACE WITH `flask db current` OUTPUT>
Branch Labels: None
Depends On: None
"""
from alembic import op
import sqlalchemy as sa

revision = 'h8i9j0k1l2m3'
down_revision = '<REPLACE WITH `flask db current` OUTPUT>'  # e.g. 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


# Calisthenics exercise seeds — (chain, level, name, unit)
CALI_SEEDS = [
    ('push', 0, 'wall pushup', 'reps'),
    ('push', 1, 'incline pushup', 'reps'),
    ('push', 2, 'knee pushup', 'reps'),
    ('push', 3, 'full pushup', 'reps'),
    ('push', 4, 'diamond pushup', 'reps'),
    ('push', 5, 'decline pushup', 'reps'),
    ('push', 6, 'archer pushup', 'reps'),
    ('push', 7, 'pseudo planche pushup', 'reps'),
    ('push', 8, 'one-arm pushup negative', 'reps'),
    ('push', 9, 'one-arm pushup', 'reps'),

    ('pull', 0, 'dead hang', 'seconds'),
    ('pull', 1, 'scapular pull', 'reps'),
    ('pull', 2, 'australian pullup', 'reps'),
    ('pull', 3, 'negative pullup', 'reps'),
    ('pull', 4, 'band-assisted pullup', 'reps'),
    ('pull', 5, 'full pullup', 'reps'),
    ('pull', 6, 'archer pullup', 'reps'),
    ('pull', 7, 'one-arm pullup negative', 'reps'),

    ('squat', 0, 'assisted squat', 'reps'),
    ('squat', 1, 'full bodyweight squat', 'reps'),
    ('squat', 2, 'reverse lunge', 'reps'),
    ('squat', 3, 'bulgarian split squat', 'reps'),
    ('squat', 4, 'pistol squat negative', 'reps'),
    ('squat', 5, 'pistol squat', 'reps'),

    ('core_dynamic', 0, 'dead bug', 'reps'),
    ('core_dynamic', 1, 'hanging knee raise', 'reps'),
    ('core_dynamic', 2, 'hanging leg raise', 'reps'),
    ('core_dynamic', 3, 'toes-to-bar', 'reps'),
    ('core_dynamic', 4, 'dragon flag negative', 'reps'),

    ('core_static', 0, 'forearm plank', 'seconds'),
    ('core_static', 1, 'hollow body hold', 'seconds'),
    ('core_static', 2, 'l-sit tuck', 'seconds'),
    ('core_static', 3, 'l-sit', 'seconds'),
    ('core_static', 4, 'v-sit progression', 'seconds'),

    ('lunge', 0, 'reverse lunge', 'reps'),
    ('lunge', 1, 'walking lunge', 'reps'),
    ('lunge', 2, 'jumping lunge', 'reps'),
    ('lunge', 3, 'shrimp squat regression', 'reps'),
]


def upgrade():
    # programs.module
    with op.batch_alter_table('programs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('module', sa.String(20), nullable=False, server_default='gym'))

    # workout_sessions.module
    with op.batch_alter_table('workout_sessions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('module', sa.String(20), nullable=False, server_default='gym'))

    # exercises.module + progression fields
    with op.batch_alter_table('exercises', schema=None) as batch_op:
        batch_op.add_column(sa.Column('module', sa.String(20), nullable=False, server_default='gym'))
        batch_op.add_column(sa.Column('progression_chain', sa.String(30), nullable=True))
        batch_op.add_column(sa.Column('progression_level', sa.Integer, nullable=True))
        batch_op.add_column(sa.Column('unit', sa.String(10), nullable=True))

    # planned_sets.is_amrap + target_seconds
    with op.batch_alter_table('planned_sets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_amrap', sa.Boolean, nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('target_seconds', sa.Integer, nullable=True))

    # Seed calisthenics exercises
    bind = op.get_bind()
    for chain, level, name, unit in CALI_SEEDS:
        bind.execute(sa.text("""
            INSERT INTO exercises (name, module, progression_chain, progression_level, unit)
            VALUES (:name, 'calisthenics', :chain, :level, :unit)
        """), {'name': name, 'chain': chain, 'level': level, 'unit': unit})


def downgrade():
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM exercises WHERE module = 'calisthenics'"))

    with op.batch_alter_table('planned_sets', schema=None) as batch_op:
        batch_op.drop_column('target_seconds')
        batch_op.drop_column('is_amrap')

    with op.batch_alter_table('exercises', schema=None) as batch_op:
        batch_op.drop_column('unit')
        batch_op.drop_column('progression_level')
        batch_op.drop_column('progression_chain')
        batch_op.drop_column('module')

    with op.batch_alter_table('workout_sessions', schema=None) as batch_op:
        batch_op.drop_column('module')

    with op.batch_alter_table('programs', schema=None) as batch_op:
        batch_op.drop_column('module')
```

**Important:** look at `Exercise` model — it might already have other columns (technique_text, muscle_group). Don't touch them. Only add the 4 new columns listed.

- [ ] **Step 6: Run migration**

```bash
flask db upgrade
```

Expected: no errors, migration applied. Verify:

```bash
flask db current
# → h8i9j0k1l2m3 (head)
```

- [ ] **Step 7: Verify seeds inserted**

```bash
python3 -c "
from app import create_app
from app.extensions import db
from app.modules.training.models import Exercise
app = create_app()
with app.app_context():
    cali = Exercise.query.filter_by(module='calisthenics').all()
    print(f'Calisthenics exercises: {len(cali)}')
    chains = {e.progression_chain for e in cali}
    print(f'Chains: {sorted(chains)}')
"
```

Expected: ~37 calisthenics exercises across 6 chains.

- [ ] **Step 8: Run full test suite (smoke)**

```bash
pytest -q
```

Expected: 147 tests still pass (no regressions yet — module filtering not active).

- [ ] **Step 9: Commit**

```bash
git add app/modules/training/models.py migrations/versions/h8i9j0k1l2m3_add_calisthenics_plan.py
git commit -m "feat: add module isolation columns and seed calisthenics progressions"
```

---

## Task 2: Module isolation in gym queries

**Goal:** Every existing gym query that fetches `Program` / `Workout` / `WorkoutSession` / recommendations must additionally filter by `module = user.active_module`. Add regression tests proving gym still works after the change.

**Files:**
- Modify: `app/modules/training/routes.py`
- Modify: `app/modules/training/progress.py`
- Modify: `app/modules/training/coach.py` (the `save_program_from_dict` function — set `module='gym'` explicitly)
- Create: `tests/calisthenics/test_module_isolation.py`

- [ ] **Step 1: Write the regression test**

Create `tests/calisthenics/test_module_isolation.py`:

```python
from datetime import datetime
from app.core.models import User
from app.core.auth import create_jwt
from app.modules.training.models import Program, Mesocycle, ProgramWeek, Workout, Exercise, WorkoutExercise, PlannedSet


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
    user = _make_user(db, active_module='gym')
    _make_program(db, user, module='gym')
    _make_program(db, user, module='calisthenics')

    r = client.get('/api/training/program', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data is not None
    assert data['name'] == 'gym Program'


def test_calisthenics_user_does_not_see_gym_program(app, client, db):
    user = _make_user(db, telegram_id=70002, active_module='calisthenics')
    _make_program(db, user, module='gym')

    r = client.get('/api/training/program', headers=_h(app, user.id))
    assert r.status_code == 200
    assert r.get_json()['data'] is None
```

(The `app/training/program` endpoint will need to be checked for the exact path — adapt the URL based on what's in `app/modules/training/routes.py`.)

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/calisthenics/test_module_isolation.py -v
```

Expected: `test_calisthenics_user_does_not_see_gym_program` FAILS — endpoint returns the gym program because filter doesn't include module.

- [ ] **Step 3: Update queries in `app/modules/training/routes.py`**

Find every place that has:
```python
Program.query.filter_by(user_id=g.user_id, status='active').first()
```

Change each to:
```python
user = db.session.get(User, g.user_id)
program = Program.query.filter_by(
    user_id=g.user_id, status='active', module=user.active_module
).first()
```

There should be ~7 occurrences (lines 87, 96, 182, 497, 506, 577, 602 from the survey). Apply the same pattern to all of them. Where `user` is already loaded, just reuse it.

Also update `WorkoutSession` queries to either:
- Filter by `module=user.active_module` directly, OR
- Filter via the `Program` relationship (if `WorkoutSession.workout` is loaded)

The simplest is direct filter on `WorkoutSession.module`:
```python
session = WorkoutSession.query.filter_by(
    id=session_id, user_id=g.user_id, module=user.active_module
).first()
```

Check `app/modules/training/progress.py` — same pattern: any program/session query needs `module` filter.

Add an `User` import at the top if missing:
```python
from app.core.models import User
```

- [ ] **Step 4: Update `save_program_from_dict` in `app/modules/training/coach.py`**

Find the function. When creating the new `Program`, set module explicitly:

```python
program = Program(
    user_id=user_id,
    name=program_dict['name'],
    periodization_type=program_dict['periodization_type'],
    total_weeks=program_dict['total_weeks'],
    status='active',
    module='gym',  # NEW: explicit gym module
)
```

Same for any explicit `WorkoutSession` creation in routes — set `module='gym'`.

For `_get_or_create_exercise` in `coach.py`: only return existing or create exercises with `module='gym'`. Check:
```python
def _get_or_create_exercise(name: str) -> Exercise:
    ex = Exercise.query.filter_by(name=name, module='gym').first()
    if not ex:
        ex = Exercise(name=name, module='gym')
        db.session.add(ex)
        db.session.flush()
    return ex
```

- [ ] **Step 5: Update existing gym tests if needed**

Some existing gym tests may set up a `Program` without specifying `module`. Since the column has `default='gym'`, this should work automatically. But run the suite to check.

- [ ] **Step 6: Run module-isolation tests**

```bash
pytest tests/calisthenics/test_module_isolation.py -v
```

Expected: both tests PASS.

- [ ] **Step 7: Run full suite — no gym regressions**

```bash
pytest -q
```

Expected: all tests pass (149+).

- [ ] **Step 8: Commit**

```bash
git add app/modules/training/routes.py app/modules/training/coach.py app/modules/training/progress.py tests/calisthenics/test_module_isolation.py
git commit -m "feat: filter gym queries by user.active_module for cross-module isolation"
```

---

## Task 3: Universal week-overview endpoint

**Files:**
- Modify: `app/modules/training/routes.py`
- Modify: `tests/calisthenics/test_module_isolation.py` (extend with week-overview tests)

- [ ] **Step 1: Write failing tests**

APPEND to `tests/calisthenics/test_module_isolation.py`:

```python
def test_week_overview_gym(app, client, db):
    user = _make_user(db, telegram_id=70010, active_module='gym')
    _make_program(db, user, module='gym')
    r = client.get('/api/training/week-overview', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert 'week_start' in data
    assert isinstance(data['workouts'], list)
    assert len(data['workouts']) == 1
    assert data['workouts'][0]['name'] == 'gym Day 1'
    assert data['workouts'][0]['status'] in ('today', 'upcoming', 'done')


def test_week_overview_calisthenics(app, client, db):
    user = _make_user(db, telegram_id=70011, active_module='calisthenics')
    _make_program(db, user, module='calisthenics')
    r = client.get('/api/training/week-overview', headers=_h(app, user.id))
    assert r.status_code == 200
    workouts = r.get_json()['data']['workouts']
    assert len(workouts) == 1
    assert workouts[0]['name'] == 'calisthenics Day 1'


def test_week_overview_no_program(app, client, db):
    user = _make_user(db, telegram_id=70012, active_module='gym')
    r = client.get('/api/training/week-overview', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['workouts'] == []
```

- [ ] **Step 2: Verify tests fail**

```bash
pytest tests/calisthenics/test_module_isolation.py::test_week_overview_gym -v
```

Expected: FAIL — 404.

- [ ] **Step 3: Implement endpoint in `app/modules/training/routes.py`**

Find the `bp` blueprint (training blueprint). Add this endpoint near the existing `/program` endpoint:

```python
@bp.route('/training/week-overview', methods=['GET'])
@require_auth
def get_week_overview():
    from datetime import date
    user = db.session.get(User, g.user_id)
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # Monday

    program = Program.query.filter_by(
        user_id=g.user_id, status='active', module=user.active_module
    ).first()
    if not program:
        return jsonify({'success': True, 'data': {
            'week_start': week_start.isoformat(),
            'workouts': [],
        }})

    # Get current week's workouts (template — week_number=1 since we have 1 week template)
    week = (ProgramWeek.query
            .join(Mesocycle)
            .filter(Mesocycle.program_id == program.id)
            .first())
    if not week:
        return jsonify({'success': True, 'data': {
            'week_start': week_start.isoformat(),
            'workouts': [],
        }})

    workouts = (Workout.query
                .filter_by(program_week_id=week.id)
                .order_by(Workout.order_index)
                .all())

    # Determine status for each workout
    completed_session_workout_ids = {
        s.workout_id for s in WorkoutSession.query.filter(
            WorkoutSession.user_id == g.user_id,
            WorkoutSession.status == 'completed',
            WorkoutSession.module == user.active_module,
            WorkoutSession.started_at >= datetime.combine(week_start, datetime.min.time()),
        ).all()
    }
    today_dow = today.weekday()

    out = []
    for w in workouts:
        if w.id in completed_session_workout_ids:
            status = 'done'
        elif w.day_of_week == today_dow:
            status = 'today'
        elif w.day_of_week < today_dow:
            status = 'missed'
        else:
            status = 'upcoming'
        out.append({
            'id': w.id,
            'name': w.name,
            'day_of_week': w.day_of_week,
            'status': status,
        })

    return jsonify({'success': True, 'data': {
        'week_start': week_start.isoformat(),
        'workouts': out,
    }})
```

Make sure `from datetime import datetime, timedelta` and `User` are imported at top of file.

- [ ] **Step 4: Run tests**

```bash
pytest tests/calisthenics/test_module_isolation.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/modules/training/routes.py tests/calisthenics/test_module_isolation.py
git commit -m "feat: add universal /api/training/week-overview endpoint"
```

---

## Task 4: Calisthenics generation (coach.py + save function)

**Files:**
- Create: `app/modules/calisthenics/coach.py`
- Modify: `app/modules/calisthenics/__init__.py` (import coach module)
- Create: `tests/calisthenics/test_program_generation.py`

- [ ] **Step 1: Write failing tests for `save_calisthenics_program_from_dict`**

Create `tests/calisthenics/test_program_generation.py`:

```python
from datetime import datetime
import pytest
from app.core.models import User
from app.modules.calisthenics.models import CalisthenicsProfile, CalisthenicsAssessment
from app.modules.training.models import Program, Workout, Exercise, WorkoutExercise, PlannedSet


def _make_user_with_profile(db, telegram_id=80001):
    u = User(
        telegram_id=telegram_id, name='CaliGen', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['floor', 'bands'], onboarding_completed_at=datetime.utcnow(),
        active_module='calisthenics',
    )
    db.session.add(u)
    db.session.commit()
    p = CalisthenicsProfile(
        user_id=u.id, goals=['muscle'], equipment=['floor', 'bands'],
        days_per_week=3, session_duration_min=45, injuries=[], motivation='look',
    )
    a = CalisthenicsAssessment(
        user_id=u.id, pullups=None, australian_pullups=8, pushups=12,
        pike_pushups=8, squats=20, superman_hold=20, plank=30, hollow_body=15, lunges=12,
    )
    db.session.add_all([p, a])
    db.session.commit()
    return u, p, a


SAMPLE_PROGRAM_DICT = {
    "name": "Calisthenics Foundations",
    "periodization_type": "hypertrophy",
    "total_weeks": 4,
    "mesocycles": [{
        "name": "Block 1",
        "order_index": 0,
        "weeks_count": 1,
        "weeks": [{
            "week_number": 1,
            "notes": None,
            "workouts": [{
                "day_of_week": 0,
                "name": "Push A",
                "order_index": 0,
                "target_muscle_groups": "Chest, Triceps",
                "estimated_duration_min": 35,
                "warmup_notes": "5 min joint mobility",
                "exercises": [{
                    "exercise_name": "full pushup",
                    "order_index": 0,
                    "tempo": "3-1-2-0",
                    "is_mandatory": True,
                    "coaching_notes": "Slow eccentric",
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


def test_save_resolves_seeded_exercises(app, db):
    from app.modules.calisthenics.coach import save_calisthenics_program_from_dict
    user, _, _ = _make_user_with_profile(db, telegram_id=80001)
    program = save_calisthenics_program_from_dict(user.id, SAMPLE_PROGRAM_DICT)
    assert program.module == 'calisthenics'
    assert program.status == 'active'
    workout = program.mesocycles[0].weeks[0].workouts[0]
    we = workout.workout_exercises[0]
    ex = Exercise.query.get(we.exercise_id)
    assert ex.module == 'calisthenics'
    assert ex.name == 'full pushup'
    assert ex.progression_chain == 'push'
    sets = PlannedSet.query.filter_by(workout_exercise_id=we.id).order_by(PlannedSet.set_number).all()
    assert len(sets) == 3
    assert sets[2].is_amrap is True
    assert sets[0].is_amrap is False


def test_save_archives_previous_active_program(app, db):
    from app.modules.calisthenics.coach import save_calisthenics_program_from_dict
    user, _, _ = _make_user_with_profile(db, telegram_id=80002)
    p1 = save_calisthenics_program_from_dict(user.id, SAMPLE_PROGRAM_DICT)
    assert p1.status == 'active'
    p2 = save_calisthenics_program_from_dict(user.id, SAMPLE_PROGRAM_DICT)
    db.session.refresh(p1)
    assert p1.status == 'completed'
    assert p2.status == 'active'


def test_save_unknown_exercise_raises(app, db):
    from app.modules.calisthenics.coach import save_calisthenics_program_from_dict
    user, _, _ = _make_user_with_profile(db, telegram_id=80003)
    bad = dict(SAMPLE_PROGRAM_DICT)
    bad['mesocycles'] = [dict(SAMPLE_PROGRAM_DICT['mesocycles'][0])]
    bad['mesocycles'][0]['weeks'] = [dict(SAMPLE_PROGRAM_DICT['mesocycles'][0]['weeks'][0])]
    bad['mesocycles'][0]['weeks'][0]['workouts'] = [dict(SAMPLE_PROGRAM_DICT['mesocycles'][0]['weeks'][0]['workouts'][0])]
    bad['mesocycles'][0]['weeks'][0]['workouts'][0]['exercises'] = [{
        **SAMPLE_PROGRAM_DICT['mesocycles'][0]['weeks'][0]['workouts'][0]['exercises'][0],
        'exercise_name': 'invented galaxy lift',
    }]
    with pytest.raises(ValueError, match='invented galaxy lift'):
        save_calisthenics_program_from_dict(user.id, bad)


def test_save_does_not_touch_gym_programs(app, db):
    from app.modules.calisthenics.coach import save_calisthenics_program_from_dict
    user, _, _ = _make_user_with_profile(db, telegram_id=80004)
    gym = Program(user_id=user.id, name='Gym Block', periodization_type='hypertrophy',
                  total_weeks=4, status='active', module='gym')
    db.session.add(gym)
    db.session.commit()
    save_calisthenics_program_from_dict(user.id, SAMPLE_PROGRAM_DICT)
    db.session.refresh(gym)
    assert gym.status == 'active'  # unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/calisthenics/test_program_generation.py -v
```

Expected: FAIL — module not importable.

- [ ] **Step 3: Implement `app/modules/calisthenics/coach.py`**

```python
"""Calisthenics program generation: AI prompt + save."""
import json
from app.core.ai import call_claude
from app.extensions import db
from app.modules.training.models import (
    Program, Mesocycle, ProgramWeek, Workout, Exercise, WorkoutExercise, PlannedSet,
)
from .models import CalisthenicsProfile, CalisthenicsAssessment


def _calisthenics_exercise_catalog() -> list:
    """Return seeded calisthenics exercises as a list of dicts for the AI prompt."""
    rows = (Exercise.query
            .filter_by(module='calisthenics')
            .order_by(Exercise.progression_chain, Exercise.progression_level)
            .all())
    return [
        {'name': r.name, 'chain': r.progression_chain,
         'level': r.progression_level, 'unit': r.unit}
        for r in rows
    ]


def _resolve_calisthenics_exercise(name: str) -> Exercise:
    """Resolve an AI-returned exercise name to a seeded Exercise row."""
    ex = Exercise.query.filter_by(module='calisthenics', name=name.strip().lower()).first()
    if not ex:
        # Try exact (case-sensitive) as fallback
        ex = Exercise.query.filter_by(module='calisthenics', name=name.strip()).first()
    if not ex:
        raise ValueError(f"Unknown calisthenics exercise: {name!r}")
    return ex


def generate_calisthenics_program(user, profile: CalisthenicsProfile,
                                   last_assessment: CalisthenicsAssessment) -> dict:
    """Call Claude to generate a calisthenics program. Returns parsed JSON dict."""
    catalog = _calisthenics_exercise_catalog()
    days = profile.days_per_week or 3
    duration = profile.session_duration_min or 45

    system_prompt = f"""You are an expert calisthenics coach.
Generate a calisthenics training program as compact JSON only — no prose, no markdown, just valid JSON.

STRICT OUTPUT CONSTRAINTS:
- Exactly 1 mesocycle
- Exactly 1 week inside that mesocycle (week_number: 1) — repeating template
- Exactly {days} workouts in that week (one per training day, day_of_week 0..6)
- 4-6 exercises per workout (compound first)
- Exactly 3 sets per exercise; the LAST set MUST have is_amrap: true, others false

CLOSED EXERCISE LIST (use only these names):
{json.dumps(catalog, ensure_ascii=False)}

LEVEL SELECTION HEURISTICS based on the user's assessment:
- pushups <5 → pick push level 1-2; 5-12 → level 3; 13-25 → level 4; 25+ → level 5+
- pullups null or 0 → pick pull level 0-2 only; 1-3 → level 3-4; 4-8 → level 5; 8+ → 6+
- if pullups is null OR equipment lacks pullup_bar/dip_bars/rings → SKIP pull chain entirely; use only push/squat/core/lunge
- squats <15 → squat level 0-1; 15-30 → level 2-3; 30+ → 4+
- plank seconds <30 → core_static level 0-1; 30-60 → 2; 60+ → 3
- hollow_body seconds <20 → start at core_static 1; 20-45 → 2; 45+ → 3
- lunges <10 → lunge level 0; 10-20 → 1; 20+ → 2

INJURIES:
- knees → no jumping lunge, no pistol squat
- wrists → use parallettes implied (still pick from list, but skip diamond pushup level 4)
- shoulders → no decline pushup, no archer pushup
- back → no dragon flag negative

PROGRAM STRUCTURE REQUIREMENTS:
- Program name in English (e.g. "Calisthenics Foundations", "Push-Pull Builder")
- periodization_type: "hypertrophy" or "skill"
- total_weeks: 4 (beginner) | 5 (intermediate) | 6 (advanced)
- For each set: target_reps as string range "8-12", or target_seconds as integer for seconds-unit exercises (target_reps null in that case)
- target_rpe 7-9, rest_seconds 60-120
- tempo "3-1-2-0" format
- coaching_notes brief (e.g., "focus on full ROM")"""

    user_prompt = f"""Create a calisthenics program for:
- Name: {user.name}, Gender: {user.gender}, Age: {user.age}, Level: {user.level}
- Goals: {profile.goals}, Equipment: {profile.equipment}, Injuries: {profile.injuries}
- Sessions: {days}/week × {duration} min, Motivation: {profile.motivation}

Last assessment:
- pullups: {last_assessment.pullups}, australian_pullups: {last_assessment.australian_pullups}
- pushups: {last_assessment.pushups}, pike_pushups: {last_assessment.pike_pushups}
- squats: {last_assessment.squats}, lunges: {last_assessment.lunges}
- plank: {last_assessment.plank}s, hollow_body: {last_assessment.hollow_body}s, superman_hold: {last_assessment.superman_hold}s

JSON structure (compact, no whitespace):
{{"name":"...","periodization_type":"hypertrophy","total_weeks":4,"mesocycles":[{{"name":"Block 1","order_index":0,"weeks_count":1,"weeks":[{{"week_number":1,"notes":null,"workouts":[{{"day_of_week":0,"name":"Push A","order_index":0,"target_muscle_groups":"Chest, Triceps","estimated_duration_min":35,"warmup_notes":"...","exercises":[{{"exercise_name":"full pushup","order_index":0,"tempo":"3-1-2-0","is_mandatory":true,"coaching_notes":"...","sets":[{{"set_number":1,"target_reps":"8-12","target_seconds":null,"target_rpe":7.0,"rest_seconds":90,"is_amrap":false}},{{"set_number":2,"target_reps":"8-12","target_seconds":null,"target_rpe":8.0,"rest_seconds":90,"is_amrap":false}},{{"set_number":3,"target_reps":"8-12","target_seconds":null,"target_rpe":9.0,"rest_seconds":90,"is_amrap":true}}]}}]}}]}}]}}]}}

Use day_of_week 0=Mon,1=Tue,2=Wed,3=Thu,4=Fri,5=Sat,6=Sun."""

    response = call_claude(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=4096)
    try:
        return json.loads(response)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI returned invalid JSON: {e}")


def save_calisthenics_program_from_dict(user_id: int, program_dict: dict) -> Program:
    """Persist a generated program; archive any prior active calisthenics program."""
    # Archive previous active calisthenics program(s)
    prior = Program.query.filter_by(
        user_id=user_id, module='calisthenics', status='active'
    ).all()
    for p in prior:
        p.status = 'completed'

    program = Program(
        user_id=user_id,
        name=program_dict['name'],
        periodization_type=program_dict.get('periodization_type', 'hypertrophy'),
        total_weeks=program_dict.get('total_weeks', 4),
        status='active',
        module='calisthenics',
    )
    db.session.add(program)
    db.session.flush()

    for m_dict in program_dict.get('mesocycles', []):
        meso = Mesocycle(
            program_id=program.id,
            name=m_dict['name'],
            order_index=m_dict.get('order_index', 0),
            weeks_count=m_dict.get('weeks_count', 1),
        )
        db.session.add(meso)
        db.session.flush()

        for w_dict in m_dict.get('weeks', []):
            week = ProgramWeek(
                mesocycle_id=meso.id,
                week_number=w_dict['week_number'],
                notes=w_dict.get('notes'),
            )
            db.session.add(week)
            db.session.flush()

            for wo_dict in w_dict.get('workouts', []):
                workout = Workout(
                    program_week_id=week.id,
                    day_of_week=wo_dict['day_of_week'],
                    name=wo_dict['name'],
                    order_index=wo_dict.get('order_index', 0),
                    target_muscle_groups=wo_dict.get('target_muscle_groups'),
                    estimated_duration_min=wo_dict.get('estimated_duration_min'),
                    warmup_notes=wo_dict.get('warmup_notes'),
                )
                db.session.add(workout)
                db.session.flush()

                for ex_dict in wo_dict.get('exercises', []):
                    exercise = _resolve_calisthenics_exercise(ex_dict['exercise_name'])
                    we = WorkoutExercise(
                        workout_id=workout.id,
                        exercise_id=exercise.id,
                        order_index=ex_dict.get('order_index', 0),
                        tempo=ex_dict.get('tempo'),
                        is_mandatory=ex_dict.get('is_mandatory', True),
                        coaching_notes=ex_dict.get('coaching_notes'),
                    )
                    db.session.add(we)
                    db.session.flush()

                    for s_dict in ex_dict.get('sets', []):
                        ps = PlannedSet(
                            workout_exercise_id=we.id,
                            set_number=s_dict['set_number'],
                            target_reps=s_dict.get('target_reps'),
                            target_seconds=s_dict.get('target_seconds'),
                            target_weight_kg=None,  # always null for calisthenics
                            target_rpe=s_dict.get('target_rpe'),
                            rest_seconds=s_dict.get('rest_seconds'),
                            is_amrap=s_dict.get('is_amrap', False),
                        )
                        db.session.add(ps)

    db.session.commit()
    return program
```

**Important:** check `WorkoutExercise` model to confirm field names (`tempo`, `is_mandatory`, `coaching_notes`). Adjust if names differ. Same for `PlannedSet`.

- [ ] **Step 4: Run tests**

```bash
pytest tests/calisthenics/test_program_generation.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/modules/calisthenics/coach.py tests/calisthenics/test_program_generation.py
git commit -m "feat: calisthenics AI generation prompt and save function"
```

---

## Task 5: POST /generate + GET /active endpoints

**Files:**
- Modify: `app/modules/calisthenics/routes.py`
- Create: `tests/calisthenics/test_program_endpoints.py`

- [ ] **Step 1: Write failing tests**

Create `tests/calisthenics/test_program_endpoints.py`:

```python
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
```

- [ ] **Step 2: Verify tests fail**

```bash
pytest tests/calisthenics/test_program_endpoints.py -v
```

Expected: FAIL — 404.

- [ ] **Step 3: Add endpoints to `app/modules/calisthenics/routes.py`**

Add at the end of the file:

```python
from app.core.models import User
from app.modules.training.models import (
    Program, Mesocycle, ProgramWeek, Workout, Exercise, WorkoutExercise, PlannedSet, WorkoutSession,
)
from .coach import generate_calisthenics_program, save_calisthenics_program_from_dict


def _serialize_program(program: Program) -> dict:
    return {
        'id': program.id,
        'name': program.name,
        'periodization_type': program.periodization_type,
        'total_weeks': program.total_weeks,
        'status': program.status,
        'module': program.module,
        'created_at': program.created_at.isoformat() if program.created_at else None,
        'mesocycles': [{
            'id': m.id,
            'name': m.name,
            'order_index': m.order_index,
            'weeks_count': m.weeks_count,
            'weeks': [{
                'id': w.id,
                'week_number': w.week_number,
                'notes': w.notes,
                'workouts': [{
                    'id': wo.id,
                    'day_of_week': wo.day_of_week,
                    'name': wo.name,
                    'order_index': wo.order_index,
                    'target_muscle_groups': wo.target_muscle_groups,
                    'estimated_duration_min': wo.estimated_duration_min,
                    'warmup_notes': wo.warmup_notes,
                    'exercises': [{
                        'id': we.id,
                        'exercise_id': we.exercise_id,
                        'exercise_name': Exercise.query.get(we.exercise_id).name,
                        'order_index': we.order_index,
                        'tempo': we.tempo,
                        'is_mandatory': we.is_mandatory,
                        'coaching_notes': we.coaching_notes,
                        'sets': [{
                            'id': ps.id,
                            'set_number': ps.set_number,
                            'target_reps': ps.target_reps,
                            'target_seconds': ps.target_seconds,
                            'target_rpe': ps.target_rpe,
                            'rest_seconds': ps.rest_seconds,
                            'is_amrap': ps.is_amrap,
                        } for ps in PlannedSet.query.filter_by(
                            workout_exercise_id=we.id
                        ).order_by(PlannedSet.set_number).all()],
                    } for we in sorted(wo.workout_exercises, key=lambda x: x.order_index)],
                } for wo in sorted(w.workouts, key=lambda x: x.order_index)],
            } for w in sorted(m.weeks, key=lambda x: x.week_number)],
        } for m in sorted(program.mesocycles, key=lambda x: x.order_index)],
    }


@bp.route('/calisthenics/program/generate', methods=['POST'])
@require_auth
def post_generate_program():
    user = db.session.get(User, g.user_id)
    profile = CalisthenicsProfile.query.filter_by(user_id=g.user_id).first()
    if not profile:
        return jsonify({'success': False, 'error': {
            'code': 'PROFILE_REQUIRED',
            'message': 'Complete the calisthenics profile setup first',
        }}), 400

    last_assessment = (CalisthenicsAssessment.query
                       .filter_by(user_id=g.user_id)
                       .order_by(CalisthenicsAssessment.assessed_at.desc())
                       .first())
    if not last_assessment:
        return jsonify({'success': False, 'error': {
            'code': 'ASSESSMENT_REQUIRED',
            'message': 'Take the assessment first',
        }}), 400

    try:
        program_dict = generate_calisthenics_program(user, profile, last_assessment)
        program = save_calisthenics_program_from_dict(g.user_id, program_dict)
    except ValueError as e:
        return jsonify({'success': False, 'error': {
            'code': 'AI_GENERATION_FAILED',
            'message': str(e),
        }}), 500

    return jsonify({'success': True, 'data': _serialize_program(program)})


@bp.route('/calisthenics/program/active', methods=['GET'])
@require_auth
def get_active_program():
    program = Program.query.filter_by(
        user_id=g.user_id, module='calisthenics', status='active'
    ).first()
    if not program:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': _serialize_program(program)})
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/calisthenics/test_program_endpoints.py -v
```

Expected: 6 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/modules/calisthenics/routes.py tests/calisthenics/test_program_endpoints.py
git commit -m "feat: calisthenics POST /program/generate and GET /program/active"
```

---

## Task 6: GET /today + POST /session/start

**Files:**
- Modify: `app/modules/calisthenics/routes.py`
- Modify: `tests/calisthenics/test_program_endpoints.py`

- [ ] **Step 1: Write failing tests**

APPEND to `tests/calisthenics/test_program_endpoints.py`:

```python
from datetime import date, timedelta
from app.modules.training.models import Program, ProgramWeek, Workout, Mesocycle, WorkoutSession


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
    p, workouts = _make_program(db, user, days_indices=(today_dow,))
    # Mark workout completed
    s = WorkoutSession(user_id=user.id, workout_id=workouts[0].id,
                       module='calisthenics', status='completed')
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
```

- [ ] **Step 2: Verify failing**

```bash
pytest tests/calisthenics/test_program_endpoints.py::test_today_scheduled -v
```

Expected: FAIL — 404.

- [ ] **Step 3: Add endpoints to routes.py**

```python
from datetime import date, datetime, timedelta


def _serialize_workout_with_exercises(workout: Workout, ad_hoc: bool = False, rest_day: bool = False) -> dict:
    if rest_day:
        return {'rest_day': True}
    return {
        'id': workout.id,
        'name': workout.name,
        'day_of_week': workout.day_of_week,
        'target_muscle_groups': workout.target_muscle_groups,
        'estimated_duration_min': workout.estimated_duration_min,
        'warmup_notes': workout.warmup_notes,
        'ad_hoc': ad_hoc,
        'exercises': [{
            'id': we.id,
            'exercise_id': we.exercise_id,
            'exercise_name': Exercise.query.get(we.exercise_id).name,
            'unit': Exercise.query.get(we.exercise_id).unit,
            'order_index': we.order_index,
            'tempo': we.tempo,
            'coaching_notes': we.coaching_notes,
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


def _get_active_calisthenics_workout(program: Program, user_id: int, today: date):
    """Reuse the gym ad-hoc pattern: scheduled today, else next incomplete in week."""
    week = (ProgramWeek.query.join(Mesocycle).filter(Mesocycle.program_id == program.id).first())
    if not week:
        return None, False, False
    today_dow = today.weekday()
    scheduled = Workout.query.filter_by(program_week_id=week.id, day_of_week=today_dow).first()
    if scheduled:
        return scheduled, False, False  # workout, ad_hoc, rest_day

    week_workouts = (Workout.query.filter_by(program_week_id=week.id)
                     .order_by(Workout.order_index).all())
    if not week_workouts:
        return None, False, False

    week_start = today - timedelta(days=today_dow)
    completed_ids = {
        s.workout_id for s in WorkoutSession.query.filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.module == 'calisthenics',
            WorkoutSession.status == 'completed',
            WorkoutSession.started_at >= datetime.combine(week_start, datetime.min.time()),
            WorkoutSession.workout_id.in_([w.id for w in week_workouts]),
        ).all()
    }
    for w in week_workouts:
        if w.id not in completed_ids:
            return w, True, False
    return None, False, True  # all done → rest


@bp.route('/calisthenics/today', methods=['GET'])
@require_auth
def get_today():
    program = Program.query.filter_by(
        user_id=g.user_id, module='calisthenics', status='active'
    ).first()
    if not program:
        return jsonify({'success': True, 'data': None})
    workout, ad_hoc, rest_day = _get_active_calisthenics_workout(program, g.user_id, date.today())
    if rest_day:
        return jsonify({'success': True, 'data': {'rest_day': True}})
    if not workout:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': _serialize_workout_with_exercises(workout, ad_hoc=ad_hoc)})


@bp.route('/calisthenics/session/start', methods=['POST'])
@require_auth
def post_session_start():
    data = request.json or {}
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

    # Check this workout's program belongs to user and is calisthenics
    program = (Program.query
               .join(Mesocycle).join(ProgramWeek)
               .filter(ProgramWeek.id == workout.program_week_id)
               .first())
    if program.user_id != g.user_id:
        return jsonify({'success': False, 'error': {
            'code': 'WORKOUT_NOT_FOUND', 'message': 'Workout not found',
        }}), 404
    if program.module != 'calisthenics':
        return jsonify({'success': False, 'error': {
            'code': 'MODULE_MISMATCH',
            'message': 'This workout belongs to a different module',
        }}), 400

    session = WorkoutSession(
        user_id=g.user_id, workout_id=workout_id,
        module='calisthenics', status='in_progress',
        started_at=datetime.utcnow(),
    )
    db.session.add(session)
    db.session.commit()
    return jsonify({'success': True, 'data': {'session_id': session.id}})
```

**Adjust:** check `WorkoutSession` model to confirm field names (`started_at`, `status`, etc.). Adapt if differs.

- [ ] **Step 4: Run tests**

```bash
pytest tests/calisthenics/test_program_endpoints.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/modules/calisthenics/routes.py tests/calisthenics/test_program_endpoints.py
git commit -m "feat: calisthenics GET /today and POST /session/start"
```

---

## Task 7: POST /log-set + POST /complete (without level-up)

**Files:**
- Modify: `app/modules/calisthenics/routes.py`
- Modify: `tests/calisthenics/test_program_endpoints.py`

- [ ] **Step 1: Inspect existing logging models**

```bash
grep -n "class LoggedSet\|class LoggedExercise" /Users/natalie/body-coach-ai/app/modules/training/models.py
```

Read the field definitions to know what columns exist (`actual_reps`, `actual_weight_kg`, `actual_seconds`?, `set_number`, `workout_session_id`, etc.).

- [ ] **Step 2: Write failing tests**

APPEND to `tests/calisthenics/test_program_endpoints.py`:

```python
from app.modules.training.models import WorkoutExercise, PlannedSet, LoggedExercise, LoggedSet


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
                       started_at=datetime.utcnow())
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
    _, wo, _ = _make_program_with_full_workout(db, user, today_dow)
    plank_ex = Exercise.query.filter_by(module='calisthenics', name='forearm plank').first()
    we_p = WorkoutExercise(workout_id=wo.id, exercise_id=plank_ex.id, order_index=1)
    db.session.add(we_p); db.session.flush()
    PlannedSet.query.filter_by(workout_exercise_id=we_p.id).all()  # Just ensure relation
    ps = PlannedSet(workout_exercise_id=we_p.id, set_number=1, target_seconds=30, is_amrap=False)
    db.session.add(ps); db.session.commit()
    s = _start_session(db, user, wo)
    r = client.post(f'/api/calisthenics/session/{s.id}/log-set',
                    json={'workout_exercise_id': we_p.id, 'set_number': 1,
                          'actual_reps': None, 'actual_seconds': 35},
                    headers=_h(app, user.id))
    assert r.status_code == 200
    log = LoggedSet.query.filter_by(set_number=1).order_by(LoggedSet.id.desc()).first()
    assert log.actual_seconds == 35


def test_complete_marks_session(app, client, db):
    user = _make_user(db, telegram_id=92003)
    today_dow = date.today().weekday()
    _, wo, _ = _make_program_with_full_workout(db, user, today_dow)
    s = _start_session(db, user, wo)
    r = client.post(f'/api/calisthenics/session/{s.id}/complete',
                    json={}, headers=_h(app, user.id))
    assert r.status_code == 200
    db.session.refresh(s)
    assert s.status == 'completed'
    data = r.get_json()['data']
    assert 'level_up_suggestions' in data
    assert data['level_up_suggestions'] == []  # no history → no suggestions


def test_complete_rejects_wrong_module_session(app, client, db):
    user = _make_user(db, telegram_id=92004)
    today_dow = date.today().weekday()
    _, wo, _ = _make_program_with_full_workout(db, user, today_dow)
    s = WorkoutSession(user_id=user.id, workout_id=wo.id, module='gym',
                       status='in_progress', started_at=datetime.utcnow())
    db.session.add(s); db.session.commit()
    r = client.post(f'/api/calisthenics/session/{s.id}/complete',
                    json={}, headers=_h(app, user.id))
    assert r.status_code == 404  # session "not found" for calisthenics scope
```

- [ ] **Step 3: Add endpoints to routes.py**

Need to know `LoggedSet` field names — adjust `actual_seconds` if it doesn't exist (in that case, use one numeric column for both reps and seconds, but spec strongly suggests adding a column. If `LoggedSet` lacks `actual_seconds`, add it via this migration **or** use `actual_reps` overloaded with seconds value when the unit is 'seconds'. Easier: use one-of pattern in app code).

**If `LoggedSet.actual_seconds` does NOT exist**, add it in this task's migration step or to existing migration. Otherwise:

```python
@bp.route('/calisthenics/session/<int:session_id>/log-set', methods=['POST'])
@require_auth
def post_log_set(session_id):
    user = db.session.get(User, g.user_id)
    session = WorkoutSession.query.filter_by(
        id=session_id, user_id=g.user_id, module='calisthenics'
    ).first()
    if not session:
        return jsonify({'success': False, 'error': {
            'code': 'SESSION_NOT_FOUND', 'message': 'Session not found',
        }}), 404

    data = request.json or {}
    we_id = data.get('workout_exercise_id')
    set_number = data.get('set_number')
    actual_reps = data.get('actual_reps')
    actual_seconds = data.get('actual_seconds')

    if not isinstance(we_id, int) or not isinstance(set_number, int):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': 'workout_exercise_id and set_number required',
        }}), 400
    if actual_reps is None and actual_seconds is None:
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': 'Either actual_reps or actual_seconds required',
        }}), 400

    we = db.session.get(WorkoutExercise, we_id)
    if not we:
        return jsonify({'success': False, 'error': {
            'code': 'WORKOUT_EXERCISE_NOT_FOUND', 'message': 'Not found',
        }}), 404

    # Find or create LoggedExercise for this session+exercise pair
    le = LoggedExercise.query.filter_by(
        workout_session_id=session.id, exercise_id=we.exercise_id
    ).first()
    if not le:
        le = LoggedExercise(
            workout_session_id=session.id,
            exercise_id=we.exercise_id,
            order_index=we.order_index,
        )
        db.session.add(le)
        db.session.flush()

    # Upsert LoggedSet
    log = LoggedSet.query.filter_by(
        logged_exercise_id=le.id, set_number=set_number
    ).first()
    is_new = log is None
    if is_new:
        log = LoggedSet(logged_exercise_id=le.id, set_number=set_number)
    log.actual_reps = actual_reps
    log.actual_seconds = actual_seconds
    log.actual_weight_kg = None
    if is_new:
        db.session.add(log)
    db.session.commit()
    return jsonify({'success': True, 'data': {'log_id': log.id}})


@bp.route('/calisthenics/session/<int:session_id>/complete', methods=['POST'])
@require_auth
def post_complete(session_id):
    session = WorkoutSession.query.filter_by(
        id=session_id, user_id=g.user_id, module='calisthenics'
    ).first()
    if not session:
        return jsonify({'success': False, 'error': {
            'code': 'SESSION_NOT_FOUND', 'message': 'Session not found',
        }}), 404

    session.status = 'completed'
    session.completed_at = datetime.utcnow()
    db.session.commit()

    # Level-up suggestions added in Task 8 — for now, empty list
    return jsonify({'success': True, 'data': {'level_up_suggestions': []}})
```

If `LoggedSet.actual_seconds` doesn't exist, you must add it in the Task 1 migration. Insert before this step:

```python
# In Task 1 migration upgrade()
with op.batch_alter_table('logged_sets', schema=None) as batch_op:
    batch_op.add_column(sa.Column('actual_seconds', sa.Integer, nullable=True))

# In downgrade()
with op.batch_alter_table('logged_sets', schema=None) as batch_op:
    batch_op.drop_column('actual_seconds')
```

And add the column on the model:
```python
# LoggedSet
actual_seconds = db.Column(db.Integer)
```

**Important — do this check in Task 1, not retroactively.** If you discover this gap during Task 7, regenerate the migration in Task 1 to include `logged_sets.actual_seconds`.

- [ ] **Step 4: Run tests**

```bash
pytest tests/calisthenics/test_program_endpoints.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/modules/calisthenics/routes.py tests/calisthenics/test_program_endpoints.py
git commit -m "feat: calisthenics POST log-set and complete (no level-up yet)"
```

---

## Task 8: Level-up logic + integration

**Files:**
- Create: `app/modules/calisthenics/level_up.py`
- Modify: `app/modules/calisthenics/routes.py` (wire into `/complete`, add `/program/<id>/level-up`)
- Create: `tests/calisthenics/test_level_up.py`

- [ ] **Step 1: Write failing tests for the pure function**

Create `tests/calisthenics/test_level_up.py`:

```python
from datetime import datetime, timedelta
import pytest
from app.core.models import User
from app.modules.training.models import (
    Program, Mesocycle, ProgramWeek, Workout, Exercise, WorkoutExercise,
    PlannedSet, WorkoutSession, LoggedExercise, LoggedSet,
)


def _setup(db, telegram_id=93001):
    u = User(telegram_id=telegram_id, name='LU', gender='female', age=25,
            weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
            level='beginner', training_days_per_week=3, session_duration_min=45,
            equipment=['floor'], onboarding_completed_at=datetime.utcnow(),
            active_module='calisthenics')
    db.session.add(u); db.session.commit()
    p = Program(user_id=u.id, name='C', periodization_type='hypertrophy',
                total_weeks=4, status='active', module='calisthenics')
    db.session.add(p); db.session.flush()
    m = Mesocycle(program_id=p.id, name='m', order_index=0, weeks_count=1)
    db.session.add(m); db.session.flush()
    w = ProgramWeek(mesocycle_id=m.id, week_number=1)
    db.session.add(w); db.session.flush()
    wo = Workout(program_week_id=w.id, day_of_week=0, name='Push', order_index=0)
    db.session.add(wo); db.session.flush()
    full_pushup = Exercise.query.filter_by(module='calisthenics', name='full pushup').first()
    we = WorkoutExercise(workout_id=wo.id, exercise_id=full_pushup.id, order_index=0)
    db.session.add(we); db.session.flush()
    for n in (1, 2, 3):
        ps = PlannedSet(workout_exercise_id=we.id, set_number=n,
                        target_reps='8-12', target_rpe=8.0, rest_seconds=90,
                        is_amrap=(n == 3))
        db.session.add(ps)
    db.session.commit()
    return u, p, wo, we, full_pushup


def _log_session(db, user, workout, exercise, amrap_value, dow_offset):
    """Create a completed session with a single AMRAP set logged."""
    s = WorkoutSession(user_id=user.id, workout_id=workout.id,
                       module='calisthenics', status='completed',
                       started_at=datetime.utcnow() - timedelta(days=dow_offset),
                       completed_at=datetime.utcnow() - timedelta(days=dow_offset))
    db.session.add(s); db.session.flush()
    le = LoggedExercise(workout_session_id=s.id, exercise_id=exercise.id, order_index=0)
    db.session.add(le); db.session.flush()
    db.session.add(LoggedSet(logged_exercise_id=le.id, set_number=1, actual_reps=10))
    db.session.add(LoggedSet(logged_exercise_id=le.id, set_number=2, actual_reps=10))
    db.session.add(LoggedSet(logged_exercise_id=le.id, set_number=3, actual_reps=amrap_value))
    db.session.commit()
    return s


def test_level_up_three_strong_sessions_promotes(app, db):
    from app.modules.calisthenics.level_up import compute_level_up_suggestions
    user, program, wo, we, full = _setup(db, telegram_id=93001)
    for d in (3, 2, 1):
        _log_session(db, user, wo, full, amrap_value=15, dow_offset=d)  # 12+3=15, threshold met
    suggestions = compute_level_up_suggestions(user.id, program)
    assert len(suggestions) == 1
    assert suggestions[0]['exercise_name_current'] == 'full pushup'
    assert suggestions[0]['exercise_name_next'] == 'diamond pushup'


def test_level_up_two_strong_one_weak_no_suggestion(app, db):
    from app.modules.calisthenics.level_up import compute_level_up_suggestions
    user, program, wo, we, full = _setup(db, telegram_id=93002)
    _log_session(db, user, wo, full, amrap_value=15, dow_offset=3)
    _log_session(db, user, wo, full, amrap_value=14, dow_offset=2)
    _log_session(db, user, wo, full, amrap_value=10, dow_offset=1)  # under threshold
    assert compute_level_up_suggestions(user.id, program) == []


def test_level_up_only_two_sessions_no_suggestion(app, db):
    from app.modules.calisthenics.level_up import compute_level_up_suggestions
    user, program, wo, we, full = _setup(db, telegram_id=93003)
    _log_session(db, user, wo, full, amrap_value=20, dow_offset=2)
    _log_session(db, user, wo, full, amrap_value=20, dow_offset=1)
    assert compute_level_up_suggestions(user.id, program) == []


def test_level_up_no_next_level_skipped(app, db):
    """If exercise is at max level in chain, no suggestion."""
    from app.modules.calisthenics.level_up import compute_level_up_suggestions
    user, program, wo, we, full = _setup(db, telegram_id=93004)
    # Replace full pushup with one-arm pushup (max level 9)
    one_arm = Exercise.query.filter_by(module='calisthenics', name='one-arm pushup').first()
    we.exercise_id = one_arm.id
    db.session.commit()
    for d in (3, 2, 1):
        _log_session(db, user, wo, one_arm, amrap_value=20, dow_offset=d)
    assert compute_level_up_suggestions(user.id, program) == []


def test_level_up_seconds_unit(app, db):
    from app.modules.calisthenics.level_up import compute_level_up_suggestions
    user, program, wo, we, full = _setup(db, telegram_id=93005)
    plank = Exercise.query.filter_by(module='calisthenics', name='forearm plank').first()
    we.exercise_id = plank.id
    # Update planned sets to use seconds
    for ps in PlannedSet.query.filter_by(workout_exercise_id=we.id).all():
        ps.target_reps = None
        ps.target_seconds = 30
    db.session.commit()

    for d in (3, 2, 1):
        s = WorkoutSession(user_id=user.id, workout_id=wo.id, module='calisthenics',
                           status='completed', started_at=datetime.utcnow() - timedelta(days=d),
                           completed_at=datetime.utcnow() - timedelta(days=d))
        db.session.add(s); db.session.flush()
        le = LoggedExercise(workout_session_id=s.id, exercise_id=plank.id, order_index=0)
        db.session.add(le); db.session.flush()
        db.session.add(LoggedSet(logged_exercise_id=le.id, set_number=3, actual_seconds=45))  # 30+10=40, value=45 OK
        db.session.commit()

    suggestions = compute_level_up_suggestions(user.id, program)
    assert len(suggestions) == 1
    assert suggestions[0]['exercise_name_next'] == 'hollow body hold'
```

- [ ] **Step 2: Verify tests fail**

```bash
pytest tests/calisthenics/test_level_up.py -v
```

Expected: FAIL — module not importable.

- [ ] **Step 3: Implement `app/modules/calisthenics/level_up.py`**

```python
"""Deterministic level-up suggestion logic for calisthenics programs."""
from app.modules.training.models import (
    Program, Mesocycle, ProgramWeek, Workout, Exercise,
    WorkoutExercise, PlannedSet, WorkoutSession, LoggedExercise, LoggedSet,
)


def _parse_reps_upper(target_reps: str) -> int | None:
    """Extract upper bound from '8-12' style range. Return None if not parseable."""
    if not target_reps:
        return None
    if '-' in target_reps:
        parts = target_reps.split('-')
        try:
            return int(parts[1].strip())
        except (ValueError, IndexError):
            return None
    try:
        return int(target_reps.strip())
    except ValueError:
        return None


def _last_n_amrap_values(user_id: int, exercise_id: int, n: int = 3) -> list:
    """Return last N completed-session AMRAP-set logged values (reps OR seconds), newest first."""
    sessions = (WorkoutSession.query
                .filter_by(user_id=user_id, module='calisthenics', status='completed')
                .order_by(WorkoutSession.completed_at.desc())
                .limit(20)  # cap to avoid runaway scans
                .all())

    results = []
    for s in sessions:
        le = LoggedExercise.query.filter_by(
            workout_session_id=s.id, exercise_id=exercise_id
        ).first()
        if not le:
            continue
        # Find the highest set_number logged set (treated as AMRAP)
        last_log = (LoggedSet.query
                    .filter_by(logged_exercise_id=le.id)
                    .order_by(LoggedSet.set_number.desc())
                    .first())
        if not last_log:
            continue
        value = last_log.actual_reps if last_log.actual_reps is not None else last_log.actual_seconds
        if value is None:
            continue
        results.append(value)
        if len(results) == n:
            break
    return results


def compute_level_up_suggestions(user_id: int, program: Program) -> list:
    """Return list of level-up suggestions for the active program."""
    suggestions = []

    # Iterate every WorkoutExercise in the program
    workouts = (Workout.query
                .join(ProgramWeek).join(Mesocycle)
                .filter(Mesocycle.program_id == program.id)
                .all())
    seen_pairs = set()  # (current_exercise_id, next_exercise_id) — dedupe across workouts
    for workout in workouts:
        for we in workout.workout_exercises:
            ex = Exercise.query.get(we.exercise_id)
            if not ex or not ex.progression_chain:
                continue
            next_level = ex.progression_level + 1
            next_ex = Exercise.query.filter_by(
                module='calisthenics',
                progression_chain=ex.progression_chain,
                progression_level=next_level,
            ).first()
            if not next_ex:
                continue  # already at max level

            if (ex.id, next_ex.id) in seen_pairs:
                continue
            seen_pairs.add((ex.id, next_ex.id))

            # AMRAP set is the last set (highest set_number with is_amrap=True if available)
            amrap_set = (PlannedSet.query
                         .filter_by(workout_exercise_id=we.id, is_amrap=True)
                         .first())
            if not amrap_set:
                # Fallback: highest set_number
                amrap_set = (PlannedSet.query
                             .filter_by(workout_exercise_id=we.id)
                             .order_by(PlannedSet.set_number.desc())
                             .first())
            if not amrap_set:
                continue

            # Compute threshold
            if ex.unit == 'seconds':
                target_value = amrap_set.target_seconds
                threshold_bonus = 10
            else:
                target_value = _parse_reps_upper(amrap_set.target_reps)
                threshold_bonus = 3
            if not target_value:
                continue
            threshold = target_value + threshold_bonus

            recent = _last_n_amrap_values(user_id, ex.id, n=3)
            if len(recent) < 3:
                continue
            if all(v >= threshold for v in recent):
                suggestions.append({
                    'workout_exercise_id': we.id,
                    'exercise_id_current': ex.id,
                    'exercise_name_current': ex.name,
                    'exercise_id_next': next_ex.id,
                    'exercise_name_next': next_ex.name,
                    'chain': ex.progression_chain,
                    'sessions_count': 3,
                })
    return suggestions
```

- [ ] **Step 4: Wire into `/complete` and add `/program/<id>/level-up` endpoint**

In `app/modules/calisthenics/routes.py`, modify the `post_complete` function:

```python
from .level_up import compute_level_up_suggestions


@bp.route('/calisthenics/session/<int:session_id>/complete', methods=['POST'])
@require_auth
def post_complete(session_id):
    session = WorkoutSession.query.filter_by(
        id=session_id, user_id=g.user_id, module='calisthenics'
    ).first()
    if not session:
        return jsonify({'success': False, 'error': {
            'code': 'SESSION_NOT_FOUND', 'message': 'Session not found',
        }}), 404

    session.status = 'completed'
    session.completed_at = datetime.utcnow()
    db.session.commit()

    # Compute level-up suggestions
    program = Program.query.filter_by(
        user_id=g.user_id, module='calisthenics', status='active'
    ).first()
    suggestions = compute_level_up_suggestions(g.user_id, program) if program else []

    return jsonify({'success': True, 'data': {'level_up_suggestions': suggestions}})


@bp.route('/calisthenics/program/<int:program_id>/level-up', methods=['POST'])
@require_auth
def post_level_up(program_id):
    program = Program.query.filter_by(
        id=program_id, user_id=g.user_id, module='calisthenics', status='active'
    ).first()
    if not program:
        return jsonify({'success': False, 'error': {
            'code': 'PROGRAM_NOT_FOUND', 'message': 'Program not found',
        }}), 404

    data = request.json or {}
    from_id = data.get('from_exercise_id')
    to_id = data.get('to_exercise_id')

    # Server-side recheck
    suggestions = compute_level_up_suggestions(g.user_id, program)
    valid = any(s['exercise_id_current'] == from_id and s['exercise_id_next'] == to_id
                for s in suggestions)
    if not valid:
        return jsonify({'success': False, 'error': {
            'code': 'LEVEL_UP_NOT_READY',
            'message': 'Promotion criteria not met',
        }}), 400

    # Verify next exercise exists and is calisthenics
    new_ex = Exercise.query.filter_by(id=to_id, module='calisthenics').first()
    if not new_ex:
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_EXERCISE', 'message': 'Target exercise invalid',
        }}), 400

    # Find all WorkoutExercise rows in this program with from_id and swap
    workout_exercises = (WorkoutExercise.query
                         .join(Workout).join(ProgramWeek).join(Mesocycle)
                         .filter(Mesocycle.program_id == program_id,
                                 WorkoutExercise.exercise_id == from_id)
                         .all())
    for we in workout_exercises:
        we.exercise_id = to_id
        # Reset planned reps to start of next level's range
        for ps in PlannedSet.query.filter_by(workout_exercise_id=we.id).all():
            if new_ex.unit == 'seconds':
                ps.target_reps = None
                ps.target_seconds = max(15, (ps.target_seconds or 30) - 10)
            else:
                ps.target_reps = '6-10'
                ps.target_seconds = None
            ps.target_weight_kg = None

    db.session.commit()
    return jsonify({'success': True, 'data': {'swapped_count': len(workout_exercises)}})
```

- [ ] **Step 5: Add endpoint test**

APPEND to `tests/calisthenics/test_level_up.py`:

```python
from app.core.auth import create_jwt


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


def test_apply_level_up_swaps_exercise(app, client, db):
    user, program, wo, we, full = _setup(db, telegram_id=93010)
    for d in (3, 2, 1):
        _log_session(db, user, wo, full, amrap_value=15, dow_offset=d)
    diamond = Exercise.query.filter_by(module='calisthenics', name='diamond pushup').first()
    r = client.post(f'/api/calisthenics/program/{program.id}/level-up',
                    json={'from_exercise_id': full.id, 'to_exercise_id': diamond.id},
                    headers=_h(app, user.id))
    assert r.status_code == 200
    db.session.refresh(we)
    assert we.exercise_id == diamond.id


def test_apply_level_up_rejects_when_criteria_not_met(app, client, db):
    user, program, wo, we, full = _setup(db, telegram_id=93011)
    diamond = Exercise.query.filter_by(module='calisthenics', name='diamond pushup').first()
    r = client.post(f'/api/calisthenics/program/{program.id}/level-up',
                    json={'from_exercise_id': full.id, 'to_exercise_id': diamond.id},
                    headers=_h(app, user.id))
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'LEVEL_UP_NOT_READY'
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/calisthenics/test_level_up.py -v
```

Expected: 7 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/modules/calisthenics/level_up.py app/modules/calisthenics/routes.py tests/calisthenics/test_level_up.py
git commit -m "feat: calisthenics level-up logic and apply endpoint"
```

---

## Task 9: POST /program/<id>/regenerate

**Files:**
- Modify: `app/modules/calisthenics/routes.py`
- Modify: `tests/calisthenics/test_program_endpoints.py`

- [ ] **Step 1: Write failing test**

APPEND to `tests/calisthenics/test_program_endpoints.py`:

```python
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
```

- [ ] **Step 2: Add endpoint to routes.py**

```python
@bp.route('/calisthenics/program/<int:program_id>/regenerate', methods=['POST'])
@require_auth
def post_regenerate(program_id):
    user = db.session.get(User, g.user_id)
    program = Program.query.filter_by(
        id=program_id, user_id=g.user_id, module='calisthenics'
    ).first()
    if not program:
        return jsonify({'success': False, 'error': {
            'code': 'PROGRAM_NOT_FOUND', 'message': 'Program not found',
        }}), 404

    profile = CalisthenicsProfile.query.filter_by(user_id=g.user_id).first()
    last_assessment = (CalisthenicsAssessment.query
                       .filter_by(user_id=g.user_id)
                       .order_by(CalisthenicsAssessment.assessed_at.desc())
                       .first())
    if not profile or not last_assessment:
        return jsonify({'success': False, 'error': {
            'code': 'ASSESSMENT_REQUIRED',
            'message': 'Take the assessment again before regenerating',
        }}), 400

    try:
        program_dict = generate_calisthenics_program(user, profile, last_assessment)
        new_program = save_calisthenics_program_from_dict(g.user_id, program_dict)
        # save_calisthenics_program_from_dict already archives prior active programs
    except ValueError as e:
        return jsonify({'success': False, 'error': {
            'code': 'AI_GENERATION_FAILED', 'message': str(e),
        }}), 500

    return jsonify({'success': True, 'data': _serialize_program(new_program)})
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/calisthenics/test_program_endpoints.py -v
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add app/modules/calisthenics/routes.py tests/calisthenics/test_program_endpoints.py
git commit -m "feat: calisthenics POST /program/<id>/regenerate"
```

---

## Task 10: Frontend — Calisthenics home (no program → Create → loading → active)

**Files:**
- Modify: `app/templates/index.html`

This task has no backend tests. Manual verification.

- [ ] **Step 1: Replace current "Програма тренувань — незабаром" with state-aware home**

Find `renderCalisthenicsHome()` function in index.html. Replace it entirely with this new version:

```javascript
function renderCalisthenicsHome() {
  const el = document.getElementById('train-content');
  const a = S.calisthenicsLastAssessment;
  const program = S.calisthenicsProgram;
  const today = S.calisthenicsToday;
  const weekOverview = S.calisthenicsWeekOverview;

  const assessedDate = a ? new Date(a.assessed_at).toLocaleDateString('uk-UA',
    { day: 'numeric', month: 'long' }) : null;

  const lastAssessSmall = a ? `
    <div class="cali-assess-card" style="margin-top:16px">
      <div class="cali-assess-card-title">Остання оцінка · ${assessedDate}</div>
      <div class="cali-assess-grid">
        ${a.pushups != null ? `<div class="cali-assess-stat"><div class="cali-assess-stat-val">${a.pushups}</div><div class="cali-assess-stat-label">Віджимань</div></div>` : ''}
        ${a.plank != null ? `<div class="cali-assess-stat"><div class="cali-assess-stat-val">${a.plank}с</div><div class="cali-assess-stat-label">Планка</div></div>` : ''}
        ${a.squats != null ? `<div class="cali-assess-stat"><div class="cali-assess-stat-val">${a.squats}</div><div class="cali-assess-stat-label">Присідань</div</div>` : ''}
      </div>
      <button class="cali-next-btn" style="margin-top:12px" onclick="renderCalisthenicsAssessment()">Пройти тест знову</button>
    </div>` : '';

  // STATE A — no program yet
  if (!program) {
    el.innerHTML = `
      <div class="cali-home">
        ${a ? lastAssessSmall : `
          <div class="cali-assess-card">
            <div class="cali-assess-card-title">Базова оцінка</div>
            <div style="color:var(--muted);font-size:13px;margin-bottom:12px">Пройди стартовий тест щоб система склала програму під тебе</div>
            <button class="cali-next-btn" onclick="renderCalisthenicsAssessment()">Почати тест</button>
          </div>`}
        ${a ? `
          <div class="cali-assess-card">
            <div class="cali-assess-card-title">Програма</div>
            <div style="color:var(--muted);font-size:13px;margin-bottom:12px">Згенеруємо персональний план на основі твоєї оцінки</div>
            <button class="cali-next-btn" onclick="caliGenerateProgram()">Створити програму</button>
          </div>` : ''}
      </div>`;
    return;
  }

  // STATE B — active program
  const todayCard = !today ? '' : (today.rest_day ? `
    <div class="cali-assess-card">
      <div class="cali-assess-card-title">Сьогодні</div>
      <div style="font-size:18px;margin-bottom:8px">Відпочинок 💤</div>
      <div style="font-size:13px;color:var(--muted)">Якщо є настрій — обери тренування нижче</div>
    </div>` : `
    <div class="cali-assess-card">
      <div class="cali-assess-card-title">Сьогодні${today.ad_hoc ? ' · Позапланове' : ''}</div>
      <div style="font-size:20px;font-weight:700;margin-bottom:6px">${today.name}</div>
      ${today.estimated_duration_min ? `<div style="font-size:13px;color:var(--muted);margin-bottom:8px">~${today.estimated_duration_min} хв · ${(today.exercises||[]).length} вправ</div>` : ''}
      <button class="cali-next-btn" onclick="caliStartSession(${today.id})">Почати тренування</button>
    </div>`);

  const overviewCard = weekOverview && weekOverview.workouts.length ? `
    <div class="cali-assess-card">
      <div class="cali-assess-card-title">Інше тренування цього тижня</div>
      ${weekOverview.workouts.map(w => `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)">
          <div>
            <div style="font-size:14px">${w.name}</div>
            <div style="font-size:11px;color:var(--muted)">${{0:'Пн',1:'Вт',2:'Ср',3:'Чт',4:'Пт',5:'Сб',6:'Нд'}[w.day_of_week] || ''}</div>
          </div>
          ${{
            'done': '<span style="font-size:12px;color:var(--muted)">✓ зроблено</span>',
            'today': `<button class="cali-next-btn" style="width:auto;padding:6px 12px;font-size:12px" onclick="caliStartSession(${w.id})">→</button>`,
            'upcoming': `<button class="cali-next-btn" style="width:auto;padding:6px 12px;font-size:12px;background:transparent;border:1px solid var(--border)" onclick="caliStartSession(${w.id})">Почати</button>`,
            'missed': `<button class="cali-next-btn" style="width:auto;padding:6px 12px;font-size:12px;background:transparent;border:1px solid var(--border)" onclick="caliStartSession(${w.id})">Почати</button>`,
          }[w.status] || ''}
        </div>`).join('')}
    </div>` : '';

  el.innerHTML = `
    <div class="cali-home">
      ${todayCard}
      ${overviewCard}
      ${lastAssessSmall}
    </div>`;
}


async function caliGenerateProgram() {
  const el = document.getElementById('train-content');
  el.innerHTML = `
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:60vh">
      <div style="width:48px;height:48px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin 1s linear infinite;margin-bottom:20px"></div>
      <div style="font-family:'Barlow Condensed',sans-serif;font-size:18px;text-transform:uppercase;letter-spacing:.05em">Створюю твою програму…</div>
      <div style="font-size:13px;color:var(--muted);margin-top:8px">Це займе 5-15 секунд</div>
    </div>
    <style>@keyframes spin{to{transform:rotate(360deg)}}</style>`;

  const r = await api('POST', '/api/calisthenics/program/generate');
  if (!r.success) {
    alert('Не вдалось створити програму: ' + (r.error?.message || 'спробуй ще раз'));
    renderCalisthenicsHome();
    return;
  }
  S.calisthenicsProgram = r.data;
  // Load today + week overview
  await caliReloadProgramData();
  renderCalisthenicsHome();
}


async function caliReloadProgramData() {
  const [todayR, overviewR] = await Promise.all([
    api('GET', '/api/calisthenics/today'),
    api('GET', '/api/training/week-overview'),
  ]);
  S.calisthenicsToday = todayR.success ? todayR.data : null;
  S.calisthenicsWeekOverview = overviewR.success ? overviewR.data : null;
}
```

- [ ] **Step 2: Update `loadCalisthenicsMode()` to also fetch program**

Find the existing `loadCalisthenicsMode` function. Update it:

```javascript
async function loadCalisthenicsMode() {
  const r = await api('GET', '/api/calisthenics/profile');
  if (!r.success) {
    const el = document.getElementById('train-content');
    el.innerHTML = `<div style="color:var(--muted);font-size:13px;text-align:center;padding:40px">Не вдалось завантажити профіль. Спробуй пізніше.</div>`;
    return;
  }
  if (r.data === null) {
    renderCalisthenicsWizard();
    return;
  }
  S.calisthenicsProfile = r.data;

  const ar = await api('GET', '/api/calisthenics/assessment/history');
  S.calisthenicsLastAssessment = (ar && ar.success && ar.data && ar.data.length > 0) ? ar.data[0] : null;

  const programR = await api('GET', '/api/calisthenics/program/active');
  S.calisthenicsProgram = programR.success ? programR.data : null;
  if (S.calisthenicsProgram) {
    await caliReloadProgramData();
  }
  renderCalisthenicsHome();
}
```

- [ ] **Step 3: Add state fields to `S`**

Find `const S = {`. Add after `calisthenicsLastAssessment: null,`:

```javascript
  calisthenicsProgram: null,
  calisthenicsToday: null,
  calisthenicsWeekOverview: null,
  calisthenicsActiveSession: null,
```

- [ ] **Step 4: Run smoke**

```bash
pytest -q
```

Expected: all tests pass (no backend changes).

- [ ] **Step 5: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: calisthenics home with create-program flow and today card"
```

---

## Task 11: Frontend — Calisthenics workout view (state C with logging)

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Add CSS for workout view**

Find the calisthenics CSS block. Insert before `/* ── CALISTHENICS HOME ── */`:

```css
    /* ── CALISTHENICS WORKOUT ── */
    .cali-workout { flex: 1; overflow-y: auto; padding: 16px; }
    .cali-workout-header { margin-bottom: 16px; }
    .cali-workout-title { font-family: 'Barlow Condensed', sans-serif; font-size: 22px;
      font-weight: 800; text-transform: uppercase; letter-spacing: .05em; }
    .cali-workout-sub { font-size: 12px; color: var(--muted); margin-top: 4px; }
    .cali-ex-card { background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; padding: 14px; margin-bottom: 12px; }
    .cali-ex-name { font-size: 16px; font-weight: 700; margin-bottom: 4px; }
    .cali-ex-target { font-size: 12px; color: var(--muted); margin-bottom: 10px; }
    .cali-set-row { display: flex; align-items: center; justify-content: space-between;
      padding: 8px 0; border-top: 1px solid var(--border); }
    .cali-set-label { font-size: 13px; color: var(--muted); width: 60px; }
    .cali-set-actions { display: flex; gap: 8px; flex: 1; justify-content: flex-end; }
    .cali-set-btn { padding: 6px 12px; border-radius: 6px; font-size: 12px;
      cursor: pointer; border: 1px solid var(--border); background: transparent; color: var(--text); }
    .cali-set-btn.done { background: var(--accent); color: #fff; border-color: var(--accent); }
    .cali-set-input { width: 70px; padding: 6px; background: transparent;
      border: 1px solid var(--border); border-radius: 6px; color: var(--text);
      font-size: 14px; text-align: center; }
    .cali-complete-btn { width: 100%; padding: 14px; background: var(--accent); color: #fff;
      border: none; border-radius: 10px; font-family: 'Barlow Condensed', sans-serif;
      font-size: 16px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
      cursor: pointer; margin-top: 16px; }
```

- [ ] **Step 2: Add session start + workout view JS**

Find the calisthenics JS block. APPEND these functions:

```javascript
async function caliStartSession(workoutId) {
  const r = await api('POST', '/api/calisthenics/session/start', { workout_id: workoutId });
  if (!r.success) {
    alert('Не вдалось почати: ' + (r.error?.message || ''));
    return;
  }
  // Fetch the workout details (we have it from /today if matches)
  const today = S.calisthenicsToday;
  let workout = (today && today.id === workoutId) ? today : null;
  if (!workout) {
    // Fall back to scanning the program for this workout
    const p = S.calisthenicsProgram;
    if (p) {
      for (const m of p.mesocycles) for (const w of m.weeks) for (const wo of w.workouts) {
        if (wo.id === workoutId) workout = wo;
      }
    }
  }
  if (!workout) {
    alert('Не вдалось знайти тренування');
    return;
  }
  S.calisthenicsActiveSession = { session_id: r.data.session_id, workout, logged: {} };
  renderCalisthenicsWorkout();
}


function renderCalisthenicsWorkout() {
  const el = document.getElementById('train-content');
  const sess = S.calisthenicsActiveSession;
  const w = sess.workout;
  const exHtml = (w.exercises || []).map(ex => {
    const unit = ex.unit || (ex.sets[0] && ex.sets[0].target_seconds != null ? 'seconds' : 'reps');
    const targetText = (s) => unit === 'seconds'
      ? (s.target_seconds + 'с' + (s.is_amrap ? ' · AMRAP' : ''))
      : (s.target_reps + (s.is_amrap ? ' · AMRAP' : ''));
    const setsHtml = (ex.sets || []).map(s => {
      const logged = (sess.logged[ex.id] || {})[s.set_number];
      if (s.is_amrap) {
        return `
          <div class="cali-set-row">
            <div class="cali-set-label">Set ${s.set_number}</div>
            <div style="font-size:11px;color:var(--muted);width:80px">${targetText(s)}</div>
            <div class="cali-set-actions">
              <input class="cali-set-input" type="number" min="0"
                placeholder="${unit === 'seconds' ? s.target_seconds : '?'}"
                id="cali-set-${ex.id}-${s.set_number}"
                value="${logged != null ? logged : ''}">
              <button class="cali-set-btn ${logged != null ? 'done' : ''}" onclick="caliLogAmrapSet(${ex.id},${s.set_number},${unit === 'seconds' ? 1 : 0})">${logged != null ? '✓' : 'Записати'}</button>
            </div>
          </div>`;
      }
      return `
        <div class="cali-set-row">
          <div class="cali-set-label">Set ${s.set_number}</div>
          <div style="font-size:11px;color:var(--muted);width:80px">${targetText(s)}</div>
          <div class="cali-set-actions">
            <button class="cali-set-btn ${logged != null ? 'done' : ''}" onclick="caliLogPlannedSet(${ex.id},${s.set_number},${unit === 'seconds' ? (s.target_seconds || 0) : 0},'${s.target_reps || ''}',${unit === 'seconds' ? 1 : 0})">${logged != null ? '✓ Зроблено' : '✓ Зробила'}</button>
            <button class="cali-set-btn" onclick="caliManualLog(${ex.id},${s.set_number},${unit === 'seconds' ? 1 : 0})">✏ Інакше</button>
          </div>
        </div>`;
    }).join('');
    return `
      <div class="cali-ex-card">
        <div class="cali-ex-name">${ex.exercise_name}</div>
        <div class="cali-ex-target">${ex.tempo || ''} ${ex.coaching_notes || ''}</div>
        ${setsHtml}
      </div>`;
  }).join('');

  el.innerHTML = `
    <div class="cali-workout">
      <div class="cali-workout-header">
        <div class="cali-workout-title">${w.name}</div>
        <div class="cali-workout-sub">${(w.exercises||[]).length} вправ${w.estimated_duration_min ? ` · ~${w.estimated_duration_min} хв` : ''}</div>
      </div>
      ${exHtml}
      <button class="cali-complete-btn" onclick="caliCompleteSession()">Завершити тренування</button>
    </div>`;
}


function _parseRepsTarget(targetReps) {
  if (!targetReps) return 0;
  const m = targetReps.match(/(\d+)(?:-(\d+))?/);
  if (!m) return 0;
  return parseInt(m[2] || m[1]);  // upper bound or single value
}


async function caliLogPlannedSet(exId, setNumber, targetSeconds, targetReps, isSeconds) {
  const sess = S.calisthenicsActiveSession;
  const value = isSeconds ? targetSeconds : _parseRepsTarget(targetReps);
  const body = isSeconds
    ? { workout_exercise_id: exId, set_number: setNumber, actual_reps: null, actual_seconds: value }
    : { workout_exercise_id: exId, set_number: setNumber, actual_reps: value, actual_seconds: null };
  const r = await api('POST', `/api/calisthenics/session/${sess.session_id}/log-set`, body);
  if (r.success) {
    sess.logged[exId] = sess.logged[exId] || {};
    sess.logged[exId][setNumber] = value;
    renderCalisthenicsWorkout();
  }
}


async function caliManualLog(exId, setNumber, isSeconds) {
  const value = prompt(isSeconds ? 'Скільки секунд?' : 'Скільки повторень?');
  if (value == null) return;
  const v = parseInt(value);
  if (isNaN(v) || v < 0) return;
  const sess = S.calisthenicsActiveSession;
  const body = isSeconds
    ? { workout_exercise_id: exId, set_number: setNumber, actual_reps: null, actual_seconds: v }
    : { workout_exercise_id: exId, set_number: setNumber, actual_reps: v, actual_seconds: null };
  const r = await api('POST', `/api/calisthenics/session/${sess.session_id}/log-set`, body);
  if (r.success) {
    sess.logged[exId] = sess.logged[exId] || {};
    sess.logged[exId][setNumber] = v;
    renderCalisthenicsWorkout();
  }
}


async function caliLogAmrapSet(exId, setNumber, isSeconds) {
  const inputEl = document.getElementById(`cali-set-${exId}-${setNumber}`);
  const v = parseInt(inputEl.value);
  if (isNaN(v) || v < 0) {
    alert('Введи число ≥ 0');
    return;
  }
  const sess = S.calisthenicsActiveSession;
  const body = isSeconds
    ? { workout_exercise_id: exId, set_number: setNumber, actual_reps: null, actual_seconds: v }
    : { workout_exercise_id: exId, set_number: setNumber, actual_reps: v, actual_seconds: null };
  const r = await api('POST', `/api/calisthenics/session/${sess.session_id}/log-set`, body);
  if (r.success) {
    sess.logged[exId] = sess.logged[exId] || {};
    sess.logged[exId][setNumber] = v;
    renderCalisthenicsWorkout();
  }
}


async function caliCompleteSession() {
  const sess = S.calisthenicsActiveSession;
  const r = await api('POST', `/api/calisthenics/session/${sess.session_id}/complete`, {});
  if (!r.success) {
    alert('Не вдалось завершити: ' + (r.error?.message || ''));
    return;
  }
  S.calisthenicsActiveSession = null;
  const suggestions = (r.data && r.data.level_up_suggestions) || [];
  if (suggestions.length > 0) {
    showLevelUpDialog(suggestions[0]);
  } else {
    await caliReloadProgramData();
    renderCalisthenicsHome();
  }
}


function showLevelUpDialog(s) {
  // Implemented in Task 12
  caliReloadProgramData().then(() => renderCalisthenicsHome());
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
git commit -m "feat: calisthenics workout view with set logging UX"
```

---

## Task 12: Frontend — Level-up dialog + Program tab + re-assessment banner

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Replace `showLevelUpDialog` with real implementation**

Find the placeholder `function showLevelUpDialog(s)` from Task 11. Replace with:

```javascript
function showLevelUpDialog(s) {
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:1000;display:flex;align-items:center;justify-content:center;padding:20px';
  overlay.innerHTML = `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:14px;padding:22px;max-width:340px;width:100%">
      <div style="font-size:32px;margin-bottom:8px">🎉</div>
      <div style="font-family:'Barlow Condensed',sans-serif;font-size:20px;font-weight:800;text-transform:uppercase;margin-bottom:8px">Готова до наступного рівня!</div>
      <div style="font-size:14px;color:var(--muted);margin-bottom:14px">Ти 3 рази поспіль зробила <b>${s.exercise_name_current}</b> з запасом. Час спробувати <b>${s.exercise_name_next}</b>.</div>
      <button class="cali-next-btn" onclick="caliApplyLevelUp(${s.exercise_id_current},${s.exercise_id_next})">Так, перейти</button>
      <button class="cali-next-btn" style="background:transparent;color:var(--text);border:1px solid var(--border);margin-top:8px" onclick="this.closest('div[style*=fixed]').remove();caliReloadProgramData().then(()=>renderCalisthenicsHome())">Поки що ні</button>
    </div>`;
  document.body.appendChild(overlay);
}


async function caliApplyLevelUp(fromId, toId) {
  const programId = S.calisthenicsProgram.id;
  const r = await api('POST', `/api/calisthenics/program/${programId}/level-up`,
    { from_exercise_id: fromId, to_exercise_id: toId });
  document.querySelectorAll('div[style*=fixed]').forEach(e => e.remove());
  if (r.success) {
    // Reload program
    const progR = await api('GET', '/api/calisthenics/program/active');
    S.calisthenicsProgram = progR.success ? progR.data : null;
  }
  await caliReloadProgramData();
  renderCalisthenicsHome();
}
```

- [ ] **Step 2: Update Program tab to render calisthenics program**

Find `loadProgramTab()`. Replace the calisthenics short-circuit with full rendering:

```javascript
async function loadProgramTab() {
  if (S.activeModule === 'calisthenics') {
    const el = document.getElementById('program-content');
    const p = S.calisthenicsProgram;
    if (!p) {
      el.innerHTML = `<div style="color:var(--muted);font-size:13px;text-align:center;padding:40px">Програми ще нема. Створи її через таб Train.</div>`;
      return;
    }
    el.innerHTML = `
      <div style="padding:16px">
        <div style="font-family:'Barlow Condensed',sans-serif;font-size:24px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;margin-bottom:4px">${p.name}</div>
        <div style="font-size:13px;color:var(--muted);margin-bottom:20px">${p.total_weeks} тижнів · ${p.periodization_type}</div>
        ${(p.mesocycles || []).map(m => `
          <div style="margin-bottom:18px">
            <div style="font-weight:700;margin-bottom:8px">${m.name}</div>
            ${(m.weeks || []).map(w => `
              <div style="margin-bottom:14px">
                <div style="font-size:12px;color:var(--muted);margin-bottom:6px">Тиждень ${w.week_number}</div>
                ${(w.workouts || []).map(wo => `
                  <div class="cali-assess-card" style="margin-bottom:8px;padding:12px">
                    <div style="font-weight:700;margin-bottom:4px">${{0:'Пн',1:'Вт',2:'Ср',3:'Чт',4:'Пт',5:'Сб',6:'Нд'}[wo.day_of_week]} · ${wo.name}</div>
                    <div style="font-size:11px;color:var(--muted);margin-bottom:6px">${wo.target_muscle_groups || ''}${wo.estimated_duration_min ? ` · ~${wo.estimated_duration_min} хв` : ''}</div>
                    ${(wo.exercises || []).map(ex => `
                      <div style="font-size:13px;padding:4px 0;border-top:1px solid var(--border)">
                        ${ex.exercise_name} · ${ex.sets ? ex.sets.length : 0} × ${(ex.sets && ex.sets[0]) ? (ex.sets[0].target_seconds ? ex.sets[0].target_seconds+'с' : ex.sets[0].target_reps) : '?'}
                      </div>`).join('')}
                  </div>`).join('')}
              </div>`).join('')}
          </div>`).join('')}
      </div>`;
    return;
  }
  // ... existing gym branch unchanged ...
```

(Keep all the existing gym `loadProgramTab` code below this branch.)

- [ ] **Step 3: Add end-of-block re-assessment banner**

Update `renderCalisthenicsHome()` to add banner check at top. Look at completed sessions count vs `total_weeks * workouts_per_week` — if reached → banner.

Find the start of `renderCalisthenicsHome` body, after the `program` variable extraction. Add:

```javascript
  let endOfBlockBanner = '';
  if (program && weekOverview && weekOverview.workouts.length > 0) {
    // Estimate completed for whole program from sessions in week (simplified: if all workouts of week marked done across enough weeks)
    // For v1 use a simpler signal: total completed sessions >= total_weeks * workouts_per_week
    const target = program.total_weeks * weekOverview.workouts.length;
    const done = (S.calisthenicsCompletedCount || 0);
    if (done >= target) {
      endOfBlockBanner = `
        <div class="cali-assess-card" style="background:#f59e0b14;border-color:#f59e0b">
          <div class="cali-assess-card-title">🏆 Блок завершено!</div>
          <div style="font-size:13px;margin-bottom:10px">Пройди тест щоб виміряти прогрес → новий блок</div>
          <button class="cali-next-btn" onclick="renderCalisthenicsAssessment()">Пройти тест</button>
        </div>`;
    }
  }
```

And insert `${endOfBlockBanner}` at the top of the home `el.innerHTML` block (before `${todayCard}`).

Update `caliReloadProgramData` to fetch session count (simple endpoint not strictly needed — we can derive from week-overview by summing across weeks, or skip in v1. For now, store a placeholder):

```javascript
async function caliReloadProgramData() {
  const [todayR, overviewR] = await Promise.all([
    api('GET', '/api/calisthenics/today'),
    api('GET', '/api/training/week-overview'),
  ]);
  S.calisthenicsToday = todayR.success ? todayR.data : null;
  S.calisthenicsWeekOverview = overviewR.success ? overviewR.data : null;
  // Completed count: count week-overview workouts with status==='done', multiplied by week_number progress (simplified)
  S.calisthenicsCompletedCount = (overviewR.data?.workouts || []).filter(w => w.status === 'done').length;
}
```

(In v1 this is approximate — only counts current-week dones. Refine in a later iteration.)

- [ ] **Step 4: Update assessment submit to refresh state and offer regenerate**

Find `caliSubmitAssessment`. After successful save, if a program already exists, prompt:

```javascript
async function caliSubmitAssessment() {
  // ... existing collect logic ...
  const r = await api('POST', '/api/calisthenics/assessment', body);
  if (r.success) {
    S.calisthenicsLastAssessment = r.data;
    if (S.calisthenicsProgram) {
      if (confirm('Зберегти результати. Створити новий блок програми?')) {
        const programId = S.calisthenicsProgram.id;
        const regen = await api('POST', `/api/calisthenics/program/${programId}/regenerate`);
        if (regen.success) {
          S.calisthenicsProgram = regen.data;
          await caliReloadProgramData();
        }
      }
    }
    renderCalisthenicsHome();
  }
}
```

- [ ] **Step 5: Smoke test**

```bash
pytest -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: calisthenics level-up dialog, program tab, re-assessment banner"
```

---

## Task 13: Documentation — calisthenics_progressions.md

**Files:**
- Create: `docs/calisthenics_progressions.md`

- [ ] **Step 1: Create the doc**

Create `docs/calisthenics_progressions.md`:

```markdown
# Calisthenics Progression Chains

This document defines the closed list of progression exercises used by the calisthenics module. The list is seeded into the `exercises` table via the `h8i9j0k1l2m3` migration. The AI generation prompt in `app/modules/calisthenics/coach.py` references these by name — adding a new exercise requires both seeding it via migration and adjusting the AI prompt's level heuristics if needed.

## Push (10 levels)
0. wall pushup — feet stand-distance from wall, hands shoulder-width
1. incline pushup — hands on bench/chair, body angled
2. knee pushup — knees on floor, full ROM
3. full pushup — feet on floor, hands shoulder-width
4. diamond pushup — hands together forming diamond
5. decline pushup — feet elevated
6. archer pushup — one arm bent, other straight
7. pseudo planche pushup — hands at hips, lean forward
8. one-arm pushup negative — slow eccentric only
9. one-arm pushup — full ROM

## Pull (8 levels) — requires pullup bar / dip bars / rings
0. dead hang (seconds)
1. scapular pull
2. australian pullup — body horizontal under bar
3. negative pullup — slow lowering only
4. band-assisted pullup
5. full pullup
6. archer pullup
7. one-arm pullup negative

## Squat (6 levels)
0. assisted squat — holding support
1. full bodyweight squat
2. reverse lunge
3. bulgarian split squat — back foot elevated
4. pistol squat negative
5. pistol squat — full single-leg

## Core dynamic (5 levels)
0. dead bug
1. hanging knee raise — requires bar
2. hanging leg raise — requires bar
3. toes-to-bar — requires bar
4. dragon flag negative

## Core static (5 levels, all in seconds)
0. forearm plank
1. hollow body hold
2. l-sit tuck
3. l-sit
4. v-sit progression

## Lunge (4 levels)
0. reverse lunge
1. walking lunge
2. jumping lunge
3. shrimp squat regression

## Promotion criteria
Computed by `compute_level_up_suggestions()` in `app/modules/calisthenics/level_up.py`:
- Reps: AMRAP value ≥ `target_upper_bound + 3` for all of the last 3 completed sessions.
- Seconds: AMRAP value ≥ `target_seconds + 10` for all of the last 3 completed sessions.

## Equipment requirements
- pull chain → requires one of: pullup_bar, dip_bars, rings
- core_dynamic levels 1-4 → requires bar (same set)
- pseudo planche, one-arm progressions → require sturdy floor; skip if user has wrist injury
```

- [ ] **Step 2: Commit**

```bash
git add docs/calisthenics_progressions.md
git commit -m "docs: add calisthenics progressions reference"
```

---

## Final Verification

After all tasks:

```bash
cd /Users/natalie/body-coach-ai/.worktrees/feature/calisthenics-plan
pytest -q
```

Expected: all tests pass (170+ counting new ones).

Manual browser test plan:
1. As user with no calisthenics profile → switch to calisthenics → wizard
2. Complete wizard + assessment → home shows "Створити програму" button
3. Tap → loading screen → ~10s → home with active program + Today card
4. Tap "Почати тренування" → workout view with exercises and sets
5. Log first 2 sets via "✓ Зробила" → both turn green
6. Log AMRAP set with high number → tap "Завершити" → if level-up criteria met (after 3 sessions), dialog appears
7. Switch to gym → see gym program (no calisthenics data leaks)
8. Switch back → calisthenics state preserved
9. Open Program tab → calisthenics program renders correctly
10. Pass assessment again → prompts "create new block" → confirms → new program

---

## Self-Review Done

- All 9 spec endpoints have a task ✅
- All 5 model column additions covered in Task 1 ✅
- Level-up logic (deterministic, no AI) implemented as pure function in Task 8 ✅
- Module isolation enforced via Task 2 ✅
- Universal week-overview built in Task 3 ✅
- Frontend covers all 3 home states + workout view + level-up + program tab ✅
- Documentation in Task 13 ✅
- No "TBD" or placeholder steps remaining ✅
- One known gap to verify during Task 7: `LoggedSet.actual_seconds` column. If missing in current schema, add it to Task 1's migration before proceeding past Task 7. Tests will surface this immediately.
