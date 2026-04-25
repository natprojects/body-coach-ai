# Calisthenics Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Calisthenics module foundation: mode switcher (gym/calisthenics), profile wizard, and assessment session with history tracking.

**Architecture:** Add `active_module` field to `User`, create `app/modules/calisthenics/` blueprint following the nutrition module pattern, add `PATCH /api/user/active-module` to core routes, and update the Train/Program tabs in `index.html` with a segment control and calisthenics-specific UI.

**Tech Stack:** Flask, SQLAlchemy, SQLite, Alembic, Vanilla JS (Telegram Mini App)

---

## File Map

- **Modify:** `app/core/models.py` — add `active_module` to `User`
- **Modify:** `app/core/routes.py` — add `PATCH /api/user/active-module`
- **Create:** `migrations/versions/g7h8i9j0k1l2_add_calisthenics_tables.py`
- **Create:** `app/modules/calisthenics/__init__.py`
- **Create:** `app/modules/calisthenics/models.py` — `CalisthenicsProfile`, `CalisthenicsAssessment`
- **Create:** `app/modules/calisthenics/routes.py` — profile + assessment endpoints
- **Modify:** `app/__init__.py` — register calisthenics blueprint
- **Modify:** `app/templates/index.html` — module switcher, wizard, assessment UI
- **Create:** `tests/calisthenics/__init__.py`
- **Create:** `tests/calisthenics/test_routes.py`

---

### Task 1: DB migration — `active_module` + calisthenics tables

**Files:**
- Modify: `app/core/models.py`
- Create: `migrations/versions/g7h8i9j0k1l2_add_calisthenics_tables.py`

- [ ] **Step 1: Add `active_module` to User model**

In `app/core/models.py`, add after the `created_at` line:

```python
    active_module = db.Column(db.String(20), default='gym', nullable=False, server_default='gym')
```

The full User model ends with:
```python
    onboarding_completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    active_module = db.Column(db.String(20), default='gym', nullable=False, server_default='gym')
```

- [ ] **Step 2: Create the migration file**

Create `migrations/versions/g7h8i9j0k1l2_add_calisthenics_tables.py`:

```python
"""add calisthenics tables and active_module

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Branch Labels: None
Depends On: None
"""
from alembic import op
import sqlalchemy as sa

revision = 'g7h8i9j0k1l2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    # Add active_module to users
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('active_module', sa.String(20), nullable=False, server_default='gym')
        )

    # Create calisthenics_profiles
    op.create_table(
        'calisthenics_profiles',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), unique=True, nullable=False),
        sa.Column('goals', sa.JSON, nullable=True),
        sa.Column('equipment', sa.JSON, nullable=True),
        sa.Column('days_per_week', sa.Integer, nullable=True),
        sa.Column('session_duration_min', sa.Integer, nullable=True),
        sa.Column('injuries', sa.JSON, nullable=True),
        sa.Column('motivation', sa.String(50), nullable=True),
        sa.Column('updated_at', sa.DateTime, server_default=sa.func.now()),
    )

    # Create calisthenics_assessments
    op.create_table(
        'calisthenics_assessments',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('assessed_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('pullups', sa.Integer, nullable=True),
        sa.Column('australian_pullups', sa.Integer, nullable=True),
        sa.Column('pushups', sa.Integer, nullable=True),
        sa.Column('pike_pushups', sa.Integer, nullable=True),
        sa.Column('squats', sa.Integer, nullable=True),
        sa.Column('superman_hold', sa.Integer, nullable=True),
        sa.Column('plank', sa.Integer, nullable=True),
        sa.Column('hollow_body', sa.Integer, nullable=True),
        sa.Column('lunges', sa.Integer, nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
    )


def downgrade():
    op.drop_table('calisthenics_assessments')
    op.drop_table('calisthenics_profiles')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('active_module')
```

- [ ] **Step 3: Run migration**

```bash
cd /path/to/worktree
flask db upgrade
```

Expected: no errors, tables created.

- [ ] **Step 4: Commit**

```bash
git add app/core/models.py migrations/versions/g7h8i9j0k1l2_add_calisthenics_tables.py
git commit -m "feat: add active_module to User and calisthenics DB tables"
```

---

### Task 2: Calisthenics models + blueprint

**Files:**
- Create: `app/modules/calisthenics/__init__.py`
- Create: `app/modules/calisthenics/models.py`
- Modify: `app/__init__.py`
- Create: `tests/calisthenics/__init__.py`
- Create: `tests/calisthenics/test_routes.py` (model tests only)

- [ ] **Step 1: Write failing model tests**

Create `tests/calisthenics/__init__.py` (empty file).

Create `tests/calisthenics/test_routes.py`:

```python
# tests/calisthenics/test_routes.py
from datetime import datetime
import pytest
from app.core.models import User
from app.core.auth import create_jwt


def _make_user(db, telegram_id=60001):
    u = User(
        telegram_id=telegram_id, name='CaliTest', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['bands', 'dumbbells'], onboarding_completed_at=datetime.utcnow(),
    )
    db.session.add(u)
    db.session.commit()
    return u


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


# ── Model tests ────────────────────────────────────────────────────────────────

def test_calisthenics_profile_creation(app, db):
    from app.modules.calisthenics.models import CalisthenicsProfile
    user = _make_user(db)
    profile = CalisthenicsProfile(
        user_id=user.id,
        goals=['muscle', 'strength'],
        equipment=['floor', 'bands', 'dumbbells'],
        days_per_week=4,
        session_duration_min=45,
        injuries=[],
        motivation='look',
    )
    db.session.add(profile)
    db.session.commit()
    fetched = CalisthenicsProfile.query.filter_by(user_id=user.id).first()
    assert fetched is not None
    assert fetched.goals == ['muscle', 'strength']
    assert fetched.motivation == 'look'


def test_calisthenics_assessment_creation(app, db):
    from app.modules.calisthenics.models import CalisthenicsAssessment
    user = _make_user(db, telegram_id=60002)
    a = CalisthenicsAssessment(
        user_id=user.id,
        pullups=None,
        australian_pullups=8,
        pushups=15,
        pike_pushups=10,
        squats=25,
        superman_hold=30,
        plank=45,
        hollow_body=20,
        lunges=12,
    )
    db.session.add(a)
    db.session.commit()
    fetched = CalisthenicsAssessment.query.filter_by(user_id=user.id).first()
    assert fetched is not None
    assert fetched.pullups is None
    assert fetched.pushups == 15
    assert fetched.plank == 45


def test_user_active_module_default(app, db):
    user = _make_user(db, telegram_id=60003)
    assert user.active_module == 'gym'
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/calisthenics/test_routes.py -v
```

Expected: FAIL — `CalisthenicsProfile` not importable.

- [ ] **Step 3: Create the blueprint**

Create `app/modules/calisthenics/__init__.py`:

```python
from flask import Blueprint

bp = Blueprint('calisthenics', __name__)

from . import routes  # noqa: F401, E402
from . import models  # noqa: F401, E402
```

- [ ] **Step 4: Create models**

Create `app/modules/calisthenics/models.py`:

```python
from datetime import datetime
from app.extensions import db


class CalisthenicsProfile(db.Model):
    __tablename__ = 'calisthenics_profiles'
    id                   = db.Column(db.Integer, primary_key=True)
    user_id              = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    goals                = db.Column(db.JSON)
    # ['muscle', 'strength', 'skill', 'weight_loss', 'endurance']
    equipment            = db.Column(db.JSON)
    # ['none', 'floor', 'bands', 'dumbbells', 'pullup_bar', 'dip_bars', 'rings', 'parallettes']
    days_per_week        = db.Column(db.Integer)
    session_duration_min = db.Column(db.Integer)
    injuries             = db.Column(db.JSON)
    motivation           = db.Column(db.String(50))
    # 'look' | 'feel' | 'achieve' | 'health'
    updated_at           = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CalisthenicsAssessment(db.Model):
    __tablename__ = 'calisthenics_assessments'
    id                  = db.Column(db.Integer, primary_key=True)
    user_id             = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assessed_at         = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    pullups             = db.Column(db.Integer, nullable=True)
    australian_pullups  = db.Column(db.Integer, nullable=True)
    pushups             = db.Column(db.Integer, nullable=True)
    pike_pushups        = db.Column(db.Integer, nullable=True)
    squats              = db.Column(db.Integer, nullable=True)
    superman_hold       = db.Column(db.Integer, nullable=True)
    plank               = db.Column(db.Integer, nullable=True)
    hollow_body         = db.Column(db.Integer, nullable=True)
    lunges              = db.Column(db.Integer, nullable=True)
    notes               = db.Column(db.Text, nullable=True)
```

- [ ] **Step 5: Create a minimal routes.py stub** (blueprint needs it to import)

Create `app/modules/calisthenics/routes.py`:

```python
from flask import g, jsonify, request
from app.core.auth import require_auth
from app.extensions import db
from . import bp
from .models import CalisthenicsProfile, CalisthenicsAssessment
```

(Just the imports — endpoints added in Task 3.)

- [ ] **Step 6: Register the blueprint in `app/__init__.py`**

In `app/__init__.py`, add after the nutrition blueprint registration:

```python
    from .modules.calisthenics import bp as calisthenics_bp
    app.register_blueprint(calisthenics_bp, url_prefix='/api')
```

Also add the models import at the top of create_app (with other model imports):

```python
    from .modules.calisthenics import models as calisthenics_models  # noqa: F401
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
pytest tests/calisthenics/test_routes.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 8: Run full suite**

```bash
pytest -q
```

Expected: all previously passing tests still pass.

- [ ] **Step 9: Commit**

```bash
git add app/modules/calisthenics/ app/__init__.py tests/calisthenics/
git commit -m "feat: add calisthenics blueprint and models"
```

---

### Task 3: `PATCH /api/user/active-module` endpoint

**Files:**
- Modify: `app/core/routes.py`
- Modify: `tests/calisthenics/test_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/calisthenics/test_routes.py`:

```python
# ── active-module endpoint ─────────────────────────────────────────────────────

def test_patch_active_module_to_calisthenics(app, client, db):
    user = _make_user(db, telegram_id=60004)
    assert user.active_module == 'gym'
    r = client.patch(
        '/api/user/active-module',
        json={'module': 'calisthenics'},
        headers=_h(app, user.id),
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['data']['active_module'] == 'calisthenics'
    db.session.refresh(user)
    assert user.active_module == 'calisthenics'


def test_patch_active_module_back_to_gym(app, client, db):
    user = _make_user(db, telegram_id=60005)
    user.active_module = 'calisthenics'
    db.session.commit()
    r = client.patch(
        '/api/user/active-module',
        json={'module': 'gym'},
        headers=_h(app, user.id),
    )
    assert r.status_code == 200
    assert r.get_json()['data']['active_module'] == 'gym'


def test_patch_active_module_invalid_value(app, client, db):
    user = _make_user(db, telegram_id=60006)
    r = client.patch(
        '/api/user/active-module',
        json={'module': 'yoga'},
        headers=_h(app, user.id),
    )
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'INVALID_MODULE'


def test_patch_active_module_requires_auth(app, client, db):
    r = client.patch('/api/user/active-module', json={'module': 'calisthenics'})
    assert r.status_code == 401
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/calisthenics/test_routes.py::test_patch_active_module_to_calisthenics tests/calisthenics/test_routes.py::test_patch_active_module_invalid_value -v
```

Expected: FAIL — 404 (endpoint not found).

- [ ] **Step 3: Add endpoint to `app/core/routes.py`**

In `app/core/routes.py`, add before the final line (after `patch_user_me`):

```python
_VALID_MODULES = {'gym', 'calisthenics'}


@bp.route('/user/active-module', methods=['PATCH'])
@require_auth
def patch_active_module():
    data = request.json or {}
    module = data.get('module')
    if module not in _VALID_MODULES:
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_MODULE',
            'message': f"module must be one of: {', '.join(sorted(_VALID_MODULES))}",
        }}), 400
    user = db.session.get(User, g.user_id)
    user.active_module = module
    db.session.commit()
    return jsonify({'success': True, 'data': {'active_module': user.active_module}})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/calisthenics/test_routes.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/core/routes.py tests/calisthenics/test_routes.py
git commit -m "feat: add PATCH /api/user/active-module endpoint"
```

---

### Task 4: Calisthenics profile endpoints (GET + POST)

**Files:**
- Modify: `app/modules/calisthenics/routes.py`
- Modify: `tests/calisthenics/test_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/calisthenics/test_routes.py`:

```python
# ── Profile endpoints ──────────────────────────────────────────────────────────

def test_get_profile_no_profile(app, client, db):
    user = _make_user(db, telegram_id=60007)
    r = client.get('/api/calisthenics/profile', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['data'] is None


def test_post_profile_creates(app, client, db):
    user = _make_user(db, telegram_id=60008)
    body = {
        'goals': ['muscle', 'strength'],
        'equipment': ['floor', 'bands', 'dumbbells'],
        'days_per_week': 4,
        'session_duration_min': 45,
        'injuries': [],
        'motivation': 'look',
    }
    r = client.post('/api/calisthenics/profile', json=body, headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['goals'] == ['muscle', 'strength']
    assert data['equipment'] == ['floor', 'bands', 'dumbbells']
    assert data['days_per_week'] == 4
    assert data['motivation'] == 'look'


def test_post_profile_updates_existing(app, client, db):
    from app.modules.calisthenics.models import CalisthenicsProfile
    user = _make_user(db, telegram_id=60009)
    existing = CalisthenicsProfile(user_id=user.id, goals=['muscle'], motivation='look')
    db.session.add(existing)
    db.session.commit()
    r = client.post(
        '/api/calisthenics/profile',
        json={'goals': ['strength', 'endurance'], 'motivation': 'achieve',
              'equipment': ['bands'], 'days_per_week': 3, 'session_duration_min': 30,
              'injuries': []},
        headers=_h(app, user.id),
    )
    assert r.status_code == 200
    assert r.get_json()['data']['goals'] == ['strength', 'endurance']
    assert CalisthenicsProfile.query.filter_by(user_id=user.id).count() == 1


def test_post_profile_invalid_days(app, client, db):
    user = _make_user(db, telegram_id=60010)
    r = client.post(
        '/api/calisthenics/profile',
        json={'goals': ['muscle'], 'equipment': [], 'days_per_week': 0,
              'session_duration_min': 45, 'injuries': [], 'motivation': 'look'},
        headers=_h(app, user.id),
    )
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'INVALID_FIELD'


def test_post_profile_invalid_motivation(app, client, db):
    user = _make_user(db, telegram_id=60011)
    r = client.post(
        '/api/calisthenics/profile',
        json={'goals': ['muscle'], 'equipment': [], 'days_per_week': 3,
              'session_duration_min': 45, 'injuries': [], 'motivation': 'money'},
        headers=_h(app, user.id),
    )
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'INVALID_FIELD'
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/calisthenics/test_routes.py::test_get_profile_no_profile tests/calisthenics/test_routes.py::test_post_profile_creates -v
```

Expected: FAIL — 404.

- [ ] **Step 3: Implement profile endpoints in `routes.py`**

Replace the contents of `app/modules/calisthenics/routes.py` with:

```python
from datetime import datetime
from flask import g, jsonify, request
from app.core.auth import require_auth
from app.core.models import User
from app.extensions import db
from . import bp
from .models import CalisthenicsProfile, CalisthenicsAssessment

_VALID_GOALS = {'muscle', 'strength', 'skill', 'weight_loss', 'endurance'}
_VALID_EQUIPMENT = {'none', 'floor', 'bands', 'dumbbells', 'pullup_bar', 'dip_bars', 'rings', 'parallettes'}
_VALID_MOTIVATION = {'look', 'feel', 'achieve', 'health'}
_PULLUP_EQUIPMENT = {'pullup_bar', 'dip_bars', 'rings'}


def _profile_to_dict(profile: CalisthenicsProfile) -> dict:
    return {
        'goals':                profile.goals or [],
        'equipment':            profile.equipment or [],
        'days_per_week':        profile.days_per_week,
        'session_duration_min': profile.session_duration_min,
        'injuries':             profile.injuries or [],
        'motivation':           profile.motivation,
    }


def _assessment_to_dict(a: CalisthenicsAssessment) -> dict:
    return {
        'id':                 a.id,
        'assessed_at':        a.assessed_at.isoformat(),
        'pullups':            a.pullups,
        'australian_pullups': a.australian_pullups,
        'pushups':            a.pushups,
        'pike_pushups':       a.pike_pushups,
        'squats':             a.squats,
        'superman_hold':      a.superman_hold,
        'plank':              a.plank,
        'hollow_body':        a.hollow_body,
        'lunges':             a.lunges,
        'notes':              a.notes,
    }


@bp.route('/calisthenics/profile', methods=['GET'])
@require_auth
def get_calisthenics_profile():
    profile = CalisthenicsProfile.query.filter_by(user_id=g.user_id).first()
    if not profile:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': _profile_to_dict(profile)})


@bp.route('/calisthenics/profile', methods=['POST'])
@require_auth
def set_calisthenics_profile():
    data = request.json or {}

    goals = data.get('goals')
    equipment = data.get('equipment', [])
    days_per_week = data.get('days_per_week')
    session_duration_min = data.get('session_duration_min')
    injuries = data.get('injuries', [])
    motivation = data.get('motivation')

    # Validate
    if not goals or not isinstance(goals, list) or not all(g in _VALID_GOALS for g in goals):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': f"goals must be a non-empty list from: {', '.join(sorted(_VALID_GOALS))}",
        }}), 400
    if not isinstance(equipment, list) or not all(e in _VALID_EQUIPMENT for e in equipment):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': f"equipment items must be from: {', '.join(sorted(_VALID_EQUIPMENT))}",
        }}), 400
    if not isinstance(days_per_week, int) or not (1 <= days_per_week <= 7):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': 'days_per_week must be an integer between 1 and 7',
        }}), 400
    if not isinstance(session_duration_min, int) or not (15 <= session_duration_min <= 180):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': 'session_duration_min must be between 15 and 180',
        }}), 400
    if motivation not in _VALID_MOTIVATION:
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': f"motivation must be one of: {', '.join(sorted(_VALID_MOTIVATION))}",
        }}), 400

    profile = CalisthenicsProfile.query.filter_by(user_id=g.user_id).first()
    is_new = profile is None
    if is_new:
        profile = CalisthenicsProfile(user_id=g.user_id)
    profile.goals = goals
    profile.equipment = equipment
    profile.days_per_week = days_per_week
    profile.session_duration_min = session_duration_min
    profile.injuries = injuries
    profile.motivation = motivation
    if is_new:
        db.session.add(profile)
    db.session.commit()
    return jsonify({'success': True, 'data': _profile_to_dict(profile)})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/calisthenics/test_routes.py -v
```

Expected: all 12 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/modules/calisthenics/routes.py tests/calisthenics/test_routes.py
git commit -m "feat: add calisthenics profile GET/POST endpoints"
```

---

### Task 5: Assessment endpoints (POST + GET history)

**Files:**
- Modify: `app/modules/calisthenics/routes.py`
- Modify: `tests/calisthenics/test_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/calisthenics/test_routes.py`:

```python
# ── Assessment endpoints ───────────────────────────────────────────────────────

def _make_profile(db, user_id):
    from app.modules.calisthenics.models import CalisthenicsProfile
    p = CalisthenicsProfile(
        user_id=user_id, goals=['muscle'], equipment=['floor', 'bands', 'dumbbells'],
        days_per_week=4, session_duration_min=45, injuries=[], motivation='look',
    )
    db.session.add(p)
    db.session.commit()
    return p


def test_post_assessment_saves_results(app, client, db):
    user = _make_user(db, telegram_id=60012)
    _make_profile(db, user.id)
    body = {
        'pullups': None,
        'australian_pullups': 8,
        'pushups': 15,
        'pike_pushups': 10,
        'squats': 25,
        'superman_hold': 30,
        'plank': 45,
        'hollow_body': 20,
        'lunges': 12,
        'notes': 'First assessment',
    }
    r = client.post('/api/calisthenics/assessment', json=body, headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['id'] is not None
    assert data['pullups'] is None
    assert data['pushups'] == 15
    assert data['plank'] == 45
    assert data['notes'] == 'First assessment'


def test_post_assessment_requires_profile(app, client, db):
    user = _make_user(db, telegram_id=60013)
    r = client.post(
        '/api/calisthenics/assessment',
        json={'pushups': 10, 'squats': 20, 'plank': 30, 'hollow_body': 15,
              'lunges': 10, 'australian_pullups': 5, 'pike_pushups': 8,
              'superman_hold': 20},
        headers=_h(app, user.id),
    )
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'PROFILE_REQUIRED'


def test_post_assessment_invalid_field(app, client, db):
    user = _make_user(db, telegram_id=60014)
    _make_profile(db, user.id)
    r = client.post(
        '/api/calisthenics/assessment',
        json={'pushups': -1, 'squats': 20, 'plank': 30, 'hollow_body': 15,
              'lunges': 10, 'australian_pullups': 5, 'pike_pushups': 8,
              'superman_hold': 20},
        headers=_h(app, user.id),
    )
    assert r.status_code == 400
    assert r.get_json()['error']['code'] == 'INVALID_FIELD'


def test_get_assessment_history_returns_all(app, client, db):
    from app.modules.calisthenics.models import CalisthenicsAssessment
    user = _make_user(db, telegram_id=60015)
    _make_profile(db, user.id)
    for i in range(3):
        db.session.add(CalisthenicsAssessment(
            user_id=user.id, pushups=10 + i, squats=20, plank=30,
            hollow_body=15, lunges=10, australian_pullups=5,
            pike_pushups=8, superman_hold=20,
        ))
    db.session.commit()
    r = client.get('/api/calisthenics/assessment/history', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert len(data) == 3
    # newest first
    assert data[0]['pushups'] >= data[1]['pushups']


def test_get_assessment_history_empty(app, client, db):
    user = _make_user(db, telegram_id=60016)
    r = client.get('/api/calisthenics/assessment/history', headers=_h(app, user.id))
    assert r.status_code == 200
    assert r.get_json()['data'] == []
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/calisthenics/test_routes.py::test_post_assessment_saves_results tests/calisthenics/test_routes.py::test_get_assessment_history_returns_all -v
```

Expected: FAIL — 404.

- [ ] **Step 3: Add assessment endpoints to `routes.py`**

Append to `app/modules/calisthenics/routes.py`:

```python
_ALWAYS_REQUIRED_FIELDS = [
    'australian_pullups', 'pushups', 'pike_pushups', 'squats',
    'superman_hold', 'plank', 'hollow_body', 'lunges',
]


@bp.route('/calisthenics/assessment', methods=['POST'])
@require_auth
def post_assessment():
    profile = CalisthenicsProfile.query.filter_by(user_id=g.user_id).first()
    if not profile:
        return jsonify({'success': False, 'error': {
            'code': 'PROFILE_REQUIRED',
            'message': 'Complete the calisthenics profile setup first',
        }}), 400

    data = request.json or {}

    # Validate always-required fields: must be int >= 0
    for field in _ALWAYS_REQUIRED_FIELDS:
        val = data.get(field)
        if not isinstance(val, int) or val < 0:
            return jsonify({'success': False, 'error': {
                'code': 'INVALID_FIELD',
                'message': f"{field} must be an integer >= 0",
            }}), 400

    # pullups: None allowed (no equipment), or int >= 0
    pullups = data.get('pullups')
    if pullups is not None and (not isinstance(pullups, int) or pullups < 0):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': 'pullups must be an integer >= 0 or null',
        }}), 400

    assessment = CalisthenicsAssessment(
        user_id=g.user_id,
        pullups=pullups,
        australian_pullups=data['australian_pullups'],
        pushups=data['pushups'],
        pike_pushups=data['pike_pushups'],
        squats=data['squats'],
        superman_hold=data['superman_hold'],
        plank=data['plank'],
        hollow_body=data['hollow_body'],
        lunges=data['lunges'],
        notes=data.get('notes'),
    )
    db.session.add(assessment)
    db.session.commit()
    return jsonify({'success': True, 'data': _assessment_to_dict(assessment)})


@bp.route('/calisthenics/assessment/history', methods=['GET'])
@require_auth
def get_assessment_history():
    assessments = (CalisthenicsAssessment.query
                   .filter_by(user_id=g.user_id)
                   .order_by(CalisthenicsAssessment.assessed_at.desc())
                   .all())
    return jsonify({'success': True, 'data': [_assessment_to_dict(a) for a in assessments]})
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/calisthenics/test_routes.py -v
```

Expected: all 17 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/modules/calisthenics/routes.py tests/calisthenics/test_routes.py
git commit -m "feat: add calisthenics assessment POST and history GET endpoints"
```

---

### Task 6: Frontend — module switcher + calisthenics UI

**Files:**
- Modify: `app/templates/index.html`

This task has no backend tests. Manual verification: open app, see switcher, wizard, assessment form.

- [ ] **Step 1: Add `active_module` to state and load it on startup**

In `app/templates/index.html`, find the `const S = {` block (line ~906) and add after `user: null,`:

```javascript
  activeModule: localStorage.getItem('bca_active_module') || 'gym',
  calisthenicsProfile: null,
  calisthenicsLastAssessment: null,
```

- [ ] **Step 2: Add CSS for module switcher**

In the `<style>` block, add after the last CSS rule before `</style>`:

```css
    /* ── MODULE SWITCHER ── */
    .module-switcher { display: flex; gap: 4px; background: var(--card);
      border: 1px solid var(--border); border-radius: 10px; padding: 3px;
      margin: 12px 16px 0; flex-shrink: 0; }
    .module-btn { flex: 1; padding: 7px 0; border: none; background: transparent;
      color: var(--muted); font-family: 'Barlow Condensed', sans-serif;
      font-size: 13px; font-weight: 700; letter-spacing: .08em;
      text-transform: uppercase; border-radius: 7px; cursor: pointer; transition: all .15s; }
    .module-btn.active { background: var(--accent); color: #fff; }

    /* ── CALISTHENICS SETUP ── */
    .cali-setup { flex: 1; overflow-y: auto; padding: 20px 16px 40px; }
    .cali-setup-step { display: none; }
    .cali-setup-step.active { display: block; }
    .cali-setup-title { font-family: 'Barlow Condensed', sans-serif; font-size: 24px;
      font-weight: 800; letter-spacing: .05em; text-transform: uppercase; margin-bottom: 20px; }
    .cali-chip-group { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }
    .cali-chip { padding: 8px 14px; border: 1px solid var(--border); border-radius: 20px;
      background: transparent; color: var(--text); font-size: 13px; cursor: pointer;
      transition: all .15s; }
    .cali-chip.selected { background: var(--accent); border-color: var(--accent); }
    .cali-next-btn { width: 100%; padding: 14px; background: var(--accent); color: #fff;
      border: none; border-radius: 10px; font-family: 'Barlow Condensed', sans-serif;
      font-size: 16px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
      cursor: pointer; margin-top: 8px; }

    /* ── CALISTHENICS ASSESSMENT ── */
    .cali-assessment { flex: 1; overflow-y: auto; padding: 20px 16px 40px; }
    .cali-assess-title { font-family: 'Barlow Condensed', sans-serif; font-size: 22px;
      font-weight: 800; text-transform: uppercase; margin-bottom: 6px; }
    .cali-assess-sub { font-size: 13px; color: var(--muted); margin-bottom: 24px; }
    .cali-exercise-row { display: flex; align-items: center; justify-content: space-between;
      padding: 12px 0; border-bottom: 1px solid var(--border); }
    .cali-exercise-name { font-size: 14px; }
    .cali-exercise-unit { font-size: 11px; color: var(--muted); margin-top: 2px; }
    .cali-exercise-input { width: 70px; padding: 8px; background: var(--card);
      border: 1px solid var(--border); border-radius: 8px; color: var(--text);
      font-size: 16px; text-align: center; }

    /* ── CALISTHENICS HOME ── */
    .cali-home { flex: 1; overflow-y: auto; padding: 16px; }
    .cali-assess-card { background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; padding: 16px; margin-bottom: 16px; }
    .cali-assess-card-title { font-size: 12px; color: var(--muted); text-transform: uppercase;
      letter-spacing: .08em; margin-bottom: 8px; }
    .cali-assess-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
    .cali-assess-stat { text-align: center; }
    .cali-assess-stat-val { font-family: 'Barlow Condensed', sans-serif; font-size: 22px;
      font-weight: 700; }
    .cali-assess-stat-label { font-size: 11px; color: var(--muted); margin-top: 2px; }
```

- [ ] **Step 3: Add module switcher HTML to panel-train**

In `app/templates/index.html`, find the `panel-train` div:

```html
    <div class="tab-panel active" id="panel-train">
      <div id="cycle-phase-badge" class="cycle-phase-badge" style="display:none"></div>
      <div id="train-content"><!-- dynamic --></div>
```

Replace with:

```html
    <div class="tab-panel active" id="panel-train">
      <div class="module-switcher" id="module-switcher">
        <button class="module-btn active" id="module-btn-gym" onclick="switchModule('gym')">Зал</button>
        <button class="module-btn" id="module-btn-calisthenics" onclick="switchModule('calisthenics')">Калістеніка</button>
      </div>
      <div id="cycle-phase-badge" class="cycle-phase-badge" style="display:none"></div>
      <div id="train-content"><!-- dynamic --></div>
```

- [ ] **Step 4: Add calisthenics JavaScript functions**

In `app/templates/index.html`, find the `// ── NUTRITION ──` comment and insert before it:

```javascript
// ── CALISTHENICS ──
const _caliSetupData = { goals: [], equipment: [], days_per_week: null, session_duration_min: null, injuries: [], motivation: null };
let _caliSetupStep = 1;

async function switchModule(mode) {
  S.activeModule = mode;
  localStorage.setItem('bca_active_module', mode);
  // Update switcher buttons
  document.getElementById('module-btn-gym').classList.toggle('active', mode === 'gym');
  document.getElementById('module-btn-calisthenics').classList.toggle('active', mode === 'calisthenics');
  // Save to server
  await api('PATCH', '/api/user/active-module', { module: mode });
  // Re-render train content
  if (mode === 'calisthenics') {
    await loadCalisthenicsMode();
  } else {
    renderTrainContent();  // existing gym render
  }
  // Update program tab if visible
  if (document.getElementById('panel-program').classList.contains('active')) {
    loadProgramTab();
  }
}

async function loadCalisthenicsMode() {
  const r = await api('GET', '/api/calisthenics/profile');
  if (!r.data) {
    renderCalisthenicsWizard();
    return;
  }
  S.calisthenicsProfile = r.data;
  // Load latest assessment
  const ar = await api('GET', '/api/calisthenics/assessment/history');
  S.calisthenicsLastAssessment = (ar.data && ar.data.length > 0) ? ar.data[0] : null;
  renderCalisthenicsHome();
}

function renderCalisthenicsWizard() {
  const el = document.getElementById('train-content');
  _caliSetupStep = 1;
  Object.assign(_caliSetupData, { goals: [], equipment: [], days_per_week: 4, session_duration_min: 45, injuries: [], motivation: null });
  el.innerHTML = `
    <div class="cali-setup">
      <div class="cali-setup-step active" id="cali-step-1">
        <div class="cali-setup-title">Яка твоя ціль?</div>
        <div class="cali-chip-group">
          ${[['muscle','М\'язова маса'],['strength','Сила'],['skill','Скіл'],['weight_loss','Схуднення'],['endurance','Витривалість']].map(([v,l]) =>
            `<button class="cali-chip" data-goal="${v}" onclick="caliToggleGoal(this,'${v}')">${l}</button>`
          ).join('')}
        </div>
        <button class="cali-next-btn" onclick="caliNextStep(1)">Далі →</button>
      </div>
      <div class="cali-setup-step" id="cali-step-2">
        <div class="cali-setup-title">Яке обладнання є?</div>
        <div class="cali-chip-group">
          ${[['floor','Підлога'],['bands','Резинки'],['dumbbells','Гантелі'],['pullup_bar','Турнік'],['dip_bars','Бруси'],['rings','Кільця'],['parallettes','Паралетки']].map(([v,l]) =>
            `<button class="cali-chip" data-equip="${v}" onclick="caliToggleEquip(this,'${v}')">${l}</button>`
          ).join('')}
        </div>
        <button class="cali-next-btn" onclick="caliNextStep(2)">Далі →</button>
      </div>
      <div class="cali-setup-step" id="cali-step-3">
        <div class="cali-setup-title">Скільки разів на тиждень?</div>
        <div class="cali-chip-group">
          ${[2,3,4,5,6].map(d =>
            `<button class="cali-chip" onclick="caliSelectDays(this,${d})">${d} дні</button>`
          ).join('')}
        </div>
        <div class="cali-setup-title" style="margin-top:20px">Тривалість сесії</div>
        <div class="cali-chip-group">
          ${[[30,'30хв'],[45,'45хв'],[60,'60хв'],[90,'90хв']].map(([v,l]) =>
            `<button class="cali-chip" onclick="caliSelectDuration(this,${v})">${l}</button>`
          ).join('')}
        </div>
        <button class="cali-next-btn" onclick="caliNextStep(3)">Далі →</button>
      </div>
      <div class="cali-setup-step" id="cali-step-4">
        <div class="cali-setup-title">Є травми або обмеження?</div>
        <div class="cali-chip-group">
          ${[['no_injuries','Все ок'],['knees','Коліна'],['back','Спина'],['shoulders','Плечі'],['wrists','Зап\'ястки'],['elbows','Лікті']].map(([v,l]) =>
            `<button class="cali-chip" onclick="caliToggleInjury(this,'${v}')">${l}</button>`
          ).join('')}
        </div>
        <button class="cali-next-btn" onclick="caliNextStep(4)">Далі →</button>
      </div>
      <div class="cali-setup-step" id="cali-step-5">
        <div class="cali-setup-title">Що тебе мотивує?</div>
        <div class="cali-chip-group">
          ${[['look','Виглядати'],['feel','Відчувати себе'],['achieve','Досягати'],['health','Здоров\'я']].map(([v,l]) =>
            `<button class="cali-chip" onclick="caliSelectMotivation(this,'${v}')">${l}</button>`
          ).join('')}
        </div>
        <button class="cali-next-btn" id="cali-finish-btn" onclick="caliFinishSetup()">Зберегти →</button>
      </div>
    </div>`;
}

function caliToggleGoal(btn, val) {
  btn.classList.toggle('selected');
  const idx = _caliSetupData.goals.indexOf(val);
  if (idx >= 0) _caliSetupData.goals.splice(idx, 1);
  else _caliSetupData.goals.push(val);
}

function caliToggleEquip(btn, val) {
  btn.classList.toggle('selected');
  const idx = _caliSetupData.equipment.indexOf(val);
  if (idx >= 0) _caliSetupData.equipment.splice(idx, 1);
  else _caliSetupData.equipment.push(val);
}

function caliSelectDays(btn, val) {
  btn.closest('.cali-chip-group').querySelectorAll('.cali-chip').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  _caliSetupData.days_per_week = val;
}

function caliSelectDuration(btn, val) {
  btn.closest('.cali-chip-group').querySelectorAll('.cali-chip').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  _caliSetupData.session_duration_min = val;
}

function caliToggleInjury(btn, val) {
  btn.classList.toggle('selected');
  if (val === 'no_injuries') {
    _caliSetupData.injuries = [];
    return;
  }
  const idx = _caliSetupData.injuries.indexOf(val);
  if (idx >= 0) _caliSetupData.injuries.splice(idx, 1);
  else _caliSetupData.injuries.push(val);
}

function caliSelectMotivation(btn, val) {
  btn.closest('.cali-chip-group').querySelectorAll('.cali-chip').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  _caliSetupData.motivation = val;
}

function caliNextStep(current) {
  document.getElementById(`cali-step-${current}`).classList.remove('active');
  document.getElementById(`cali-step-${current + 1}`).classList.add('active');
  _caliSetupStep = current + 1;
}

async function caliFinishSetup() {
  if (!_caliSetupData.motivation) return;
  if (!_caliSetupData.days_per_week) _caliSetupData.days_per_week = 3;
  if (!_caliSetupData.session_duration_min) _caliSetupData.session_duration_min = 45;
  if (!_caliSetupData.goals.length) _caliSetupData.goals = ['muscle'];
  const btn = document.getElementById('cali-finish-btn');
  btn.disabled = true;
  btn.textContent = 'Збереження...';
  const r = await api('POST', '/api/calisthenics/profile', _caliSetupData);
  if (r.success) {
    S.calisthenicsProfile = r.data;
    renderCalisthenicsAssessment();
  } else {
    btn.disabled = false;
    btn.textContent = 'Зберегти →';
  }
}

function renderCalisthenicsAssessment() {
  const el = document.getElementById('train-content');
  const profile = S.calisthenicsProfile;
  const equip = profile ? (profile.equipment || []) : [];
  const hasPullupGear = equip.some(e => ['pullup_bar', 'dip_bars', 'rings'].includes(e));

  const exercises = [
    ...(hasPullupGear ? [{ key: 'pullups', name: 'Підтягування', unit: 'макс повторів' }] : []),
    { key: 'australian_pullups', name: 'Австралійські підтягування', unit: 'макс повторів' },
    { key: 'pushups', name: 'Віджимання', unit: 'макс повторів' },
    { key: 'pike_pushups', name: 'Pike push-ups', unit: 'макс повторів' },
    { key: 'squats', name: 'Присідання', unit: 'макс повторів' },
    { key: 'superman_hold', name: 'Superman hold', unit: 'секунди' },
    { key: 'plank', name: 'Планка', unit: 'секунди' },
    { key: 'hollow_body', name: 'Hollow body hold', unit: 'секунди' },
    { key: 'lunges', name: 'Випади', unit: 'макс (кожна нога)' },
  ];

  el.innerHTML = `
    <div class="cali-assessment">
      <div class="cali-assess-title">Стартова точка</div>
      <div class="cali-assess-sub">Введи скільки змогла зробити. 0 — теж результат.</div>
      ${exercises.map(ex => `
        <div class="cali-exercise-row">
          <div>
            <div class="cali-exercise-name">${ex.name}</div>
            <div class="cali-exercise-unit">${ex.unit}</div>
          </div>
          <input class="cali-exercise-input" type="number" min="0" id="cali-input-${ex.key}" placeholder="0">
        </div>`).join('')}
      <input class="cali-exercise-input" type="text" id="cali-notes" placeholder="Нотатки (необов'язково)"
        style="width:100%;margin-top:16px;text-align:left;padding:10px">
      <button class="cali-next-btn" style="margin-top:16px" onclick="caliSubmitAssessment()">Зберегти результати</button>
    </div>`;
}

async function caliSubmitAssessment() {
  const profile = S.calisthenicsProfile || {};
  const equip = profile.equipment || [];
  const hasPullupGear = equip.some(e => ['pullup_bar', 'dip_bars', 'rings'].includes(e));

  const getVal = (key) => {
    const el = document.getElementById(`cali-input-${key}`);
    if (!el) return null;
    const v = parseInt(el.value);
    return isNaN(v) ? 0 : Math.max(0, v);
  };

  const body = {
    pullups: hasPullupGear ? getVal('pullups') : null,
    australian_pullups: getVal('australian_pullups'),
    pushups: getVal('pushups'),
    pike_pushups: getVal('pike_pushups'),
    squats: getVal('squats'),
    superman_hold: getVal('superman_hold'),
    plank: getVal('plank'),
    hollow_body: getVal('hollow_body'),
    lunges: getVal('lunges'),
    notes: (document.getElementById('cali-notes') || {}).value || '',
  };

  const r = await api('POST', '/api/calisthenics/assessment', body);
  if (r.success) {
    S.calisthenicsLastAssessment = r.data;
    renderCalisthenicsHome();
  }
}

function renderCalisthenicsHome() {
  const el = document.getElementById('train-content');
  const a = S.calisthenicsLastAssessment;
  const assessedDate = a ? new Date(a.assessed_at).toLocaleDateString('uk-UA', { day: 'numeric', month: 'long' }) : null;

  const statsHtml = a ? `
    <div class="cali-assess-card">
      <div class="cali-assess-card-title">Остання оцінка · ${assessedDate}</div>
      <div class="cali-assess-grid">
        ${a.pushups != null ? `<div class="cali-assess-stat"><div class="cali-assess-stat-val">${a.pushups}</div><div class="cali-assess-stat-label">Віджимань</div></div>` : ''}
        ${a.plank != null ? `<div class="cali-assess-stat"><div class="cali-assess-stat-val">${a.plank}с</div><div class="cali-assess-stat-label">Планка</div></div>` : ''}
        ${a.squats != null ? `<div class="cali-assess-stat"><div class="cali-assess-stat-val">${a.squats}</div><div class="cali-assess-stat-label">Присідань</div></div>` : ''}
      </div>
      <button class="cali-next-btn" style="margin-top:12px" onclick="renderCalisthenicsAssessment()">Пройти тест знову</button>
    </div>` : `
    <div class="cali-assess-card">
      <div class="cali-assess-card-title">Базова оцінка</div>
      <div style="color:var(--muted);font-size:13px;margin-bottom:12px">Пройди стартовий тест щоб відстежувати прогрес</div>
      <button class="cali-next-btn" onclick="renderCalisthenicsAssessment()">Почати тест</button>
    </div>`;

  el.innerHTML = `
    <div class="cali-home">
      ${statsHtml}
      <div style="color:var(--muted);font-size:13px;text-align:center;padding:20px">
        Програма тренувань — незабаром
      </div>
    </div>`;
}
```

- [ ] **Step 5: Load `active_module` on app start and update `switchTab`**

Find in `app/templates/index.html` the section where the app loads on startup. Find `if (name === 'train')` inside `switchTab` and update the function to handle calisthenics:

Find the `switchTab` function body and add at the end of `if (name === 'train')` block:

```javascript
  if (name === 'train') {
    // ... existing cycle phase code ...
    if (S.activeModule === 'calisthenics') {
      await loadCalisthenicsMode();
    }
  }
```

Also find where `S.user` is loaded on app startup (the `loadApp` or initialization function) and add after loading user data:

```javascript
  // Restore module switcher state
  if (S.activeModule === 'calisthenics') {
    document.getElementById('module-btn-gym').classList.remove('active');
    document.getElementById('module-btn-calisthenics').classList.add('active');
  }
```

- [ ] **Step 6: Update Program tab to respect `active_module`**

Find `async function loadProgramTab()` and add at the top of the function body:

```javascript
  if (S.activeModule === 'calisthenics') {
    const el = document.getElementById('program-content');
    el.innerHTML = `<div style="color:var(--muted);font-size:13px;text-align:center;padding:40px">Програма калістеніки — незабаром</div>`;
    return;
  }
```

- [ ] **Step 7: Run full suite (smoke check)**

```bash
pytest -q
```

Expected: all tests pass (no backend change in this task).

- [ ] **Step 8: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: add calisthenics UI — module switcher, setup wizard, assessment screen"
```
