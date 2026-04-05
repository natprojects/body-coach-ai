# Nutrition Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Nutrition module foundation: profile setup wizard, BMR/TDEE/macro/water calculations, AI chat for ingredient-based meal advice, and meal logging for variety tracking.

**Architecture:** New Blueprint at `app/modules/nutrition/` mirrors training/coach pattern. Pure calculation functions in `calculator.py`. Context builder in `context.py` aggregates cross-module data for the AI system prompt. Chat reuses `stream_chat()` from `app/core/ai.py` (module='nutrition'), which persists to AIConversation table.

**Tech Stack:** Flask Blueprint, SQLAlchemy, Anthropic API (claude-sonnet-4-6), SSE streaming, vanilla JS

---

### Task 1: DB Migration — nutrition_profiles + meal_logs tables

**Files:**
- Create: `migrations/versions/a1b2c3d4e5f6_add_nutrition_tables.py`

- [ ] **Step 1: Write the migration file**

```python
"""add nutrition tables

Revision ID: a1b2c3d4e5f6
Revises: 3ee87c1b43f1
Create Date: 2026-04-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '3ee87c1b43f1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'nutrition_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('diet_type', sa.String(20), nullable=True),
        sa.Column('allergies', sa.JSON(), nullable=True),
        sa.Column('cooking_skill', sa.String(20), nullable=True),
        sa.Column('budget', sa.String(20), nullable=True),
        sa.Column('activity_outside', sa.String(20), nullable=True),
        sa.Column('bmr', sa.Float(), nullable=True),
        sa.Column('tdee', sa.Float(), nullable=True),
        sa.Column('calorie_target', sa.Float(), nullable=True),
        sa.Column('protein_g', sa.Float(), nullable=True),
        sa.Column('fat_g', sa.Float(), nullable=True),
        sa.Column('carbs_g', sa.Float(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_table(
        'meal_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('logged_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('meal_logs')
    op.drop_table('nutrition_profiles')
```

- [ ] **Step 2: Run the migration**

```bash
flask db upgrade
```

Expected output includes: `Running upgrade 3ee87c1b43f1 -> a1b2c3d4e5f6, add nutrition tables`

- [ ] **Step 3: Verify tables exist**

```bash
python -c "
from app import create_app
from app.extensions import db
app = create_app()
with app.app_context():
    names = db.engine.table_names()
    print([t for t in names if 'nutrition' in t or 'meal' in t])
"
```

Expected: `['meal_logs', 'nutrition_profiles']`

- [ ] **Step 4: Commit**

```bash
git add migrations/versions/a1b2c3d4e5f6_add_nutrition_tables.py
git commit -m "feat: add nutrition_profiles and meal_logs tables"
```

---

### Task 2: Calculator — pure functions + tests

**Files:**
- Create: `app/modules/nutrition/calculator.py`
- Create: `tests/nutrition/__init__.py`
- Create: `tests/nutrition/test_calculator.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/nutrition/test_calculator.py
import pytest
from app.modules.nutrition.calculator import (
    calc_bmr, calc_tdee, calc_calorie_target, calc_macros, calc_water_ml
)


def test_bmr_female():
    # 10*60 + 6.25*165 - 5*25 - 161 = 600 + 1031.25 - 125 - 161 = 1345.25
    assert calc_bmr(60.0, 165.0, 25, 'female') == pytest.approx(1345.25, abs=0.1)


def test_bmr_male():
    # 10*80 + 6.25*180 - 5*30 + 5 = 800 + 1125 - 150 + 5 = 1780
    assert calc_bmr(80.0, 180.0, 30, 'male') == pytest.approx(1780.0, abs=0.1)


def test_tdee_sedentary_no_training():
    # 1400 * (1.2 + 0.0) = 1680
    assert calc_tdee(1400.0, 'sedentary', 0) == pytest.approx(1680.0, abs=0.1)


def test_tdee_lightly_3_days():
    # 1400 * (1.375 + 0.10) = 1400 * 1.475 = 2065
    assert calc_tdee(1400.0, 'lightly', 3) == pytest.approx(2065.0, abs=0.1)


def test_tdee_moderately_5_days():
    # 1400 * (1.55 + 0.175) = 1400 * 1.725 = 2415
    assert calc_tdee(1400.0, 'moderately', 5) == pytest.approx(2415.0, abs=0.1)


def test_tdee_very_7_days():
    # 1400 * (1.725 + 0.25) = 1400 * 1.975 = 2765
    assert calc_tdee(1400.0, 'very', 7) == pytest.approx(2765.0, abs=0.1)


def test_calorie_target_fat_loss():
    assert calc_calorie_target(2000.0, 'fat_loss') == pytest.approx(1600.0)


def test_calorie_target_hypertrophy():
    assert calc_calorie_target(2000.0, 'hypertrophy') == pytest.approx(2250.0)


def test_calorie_target_strength():
    assert calc_calorie_target(2000.0, 'strength') == pytest.approx(2250.0)


def test_calorie_target_maintenance():
    assert calc_calorie_target(2000.0, 'general_fitness') == pytest.approx(2000.0)


def test_macros_standard():
    # weight=66kg, calories=2000
    # protein = 2.0 * 66 = 132g
    # fat = 2000 * 0.28 / 9 ≈ 62.2g
    # carbs = (2000 - 132*4 - 62.2*9) / 4 > 0
    result = calc_macros(66.0, 2000.0)
    assert result['protein_g'] == 132.0
    assert result['fat_g'] == pytest.approx(62.2, abs=0.5)
    assert result['carbs_g'] > 0


def test_macros_no_negative_carbs():
    # very high body weight, low calories → carbs clamped to 0
    result = calc_macros(120.0, 1200.0)
    assert result['carbs_g'] >= 0


def test_water_ml():
    assert calc_water_ml(60.0) == 1950.0   # 60 * 32.5
    assert calc_water_ml(80.0) == 2600.0   # 80 * 32.5
```

- [ ] **Step 2: Create empty `tests/nutrition/__init__.py`**

Create an empty file at `tests/nutrition/__init__.py`.

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/nutrition/test_calculator.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.modules.nutrition'`

- [ ] **Step 4: Implement `app/modules/nutrition/calculator.py`**

```python
# app/modules/nutrition/calculator.py
BASE_FACTORS = {
    'sedentary':  1.20,
    'lightly':    1.375,
    'moderately': 1.55,
    'very':       1.725,
}

GOAL_ADJUSTMENTS = {
    'fat_loss':    -400,
    'hypertrophy': +250,
    'strength':    +250,
}


def _training_bonus(training_days_per_week: int) -> float:
    if training_days_per_week <= 1:
        return 0.0
    elif training_days_per_week <= 3:
        return 0.10
    elif training_days_per_week <= 5:
        return 0.175
    else:
        return 0.25


def calc_bmr(weight_kg: float, height_cm: float, age: int, gender: str) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base - 161 if gender == 'female' else base + 5


def calc_tdee(bmr: float, activity_outside: str, training_days_per_week: int) -> float:
    base = BASE_FACTORS[activity_outside]
    bonus = _training_bonus(training_days_per_week)
    return bmr * (base + bonus)


def calc_calorie_target(tdee: float, goal_primary: str) -> float:
    return tdee + GOAL_ADJUSTMENTS.get(goal_primary, 0)


def calc_macros(weight_kg: float, calorie_target: float) -> dict:
    protein_g = round(2.0 * weight_kg, 1)
    fat_g     = round(calorie_target * 0.28 / 9, 1)
    carbs_g   = round((calorie_target - protein_g * 4 - fat_g * 9) / 4, 1)
    carbs_g   = max(0.0, carbs_g)
    return {'protein_g': protein_g, 'fat_g': fat_g, 'carbs_g': carbs_g}


def calc_water_ml(weight_kg: float) -> float:
    return round(weight_kg * 32.5)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/nutrition/test_calculator.py -v
```

Expected: `13 passed`

- [ ] **Step 6: Commit**

```bash
git add app/modules/nutrition/calculator.py tests/nutrition/__init__.py tests/nutrition/test_calculator.py
git commit -m "feat: add nutrition calculator (BMR/TDEE/macros/water)"
```

---

### Task 3: Models + Blueprint Registration

**Files:**
- Create: `app/modules/nutrition/__init__.py`
- Create: `app/modules/nutrition/models.py`
- Modify: `app/__init__.py`

- [ ] **Step 1: Write failing model tests**

```python
# tests/nutrition/test_routes.py
from datetime import date, datetime
import pytest
from app.core.models import User
from app.modules.nutrition.models import NutritionProfile, MealLog
from app.extensions import db as _db


def _make_user(db):
    u = User(
        telegram_id=50001, name='NutrTest', gender='female', age=28,
        weight_kg=65.0, height_cm=168.0, goal_primary='fat_loss',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['home'], onboarding_completed_at=datetime.utcnow(),
    )
    db.session.add(u)
    db.session.commit()
    return u


def test_nutrition_profile_creation(app, db):
    user = _make_user(db)
    profile = NutritionProfile(
        user_id=user.id, diet_type='omnivore', allergies=['lactose'],
        cooking_skill='beginner', budget='medium', activity_outside='sedentary',
        bmr=1500.0, tdee=1800.0, calorie_target=1400.0,
        protein_g=130.0, fat_g=43.6, carbs_g=175.0,
    )
    db.session.add(profile)
    db.session.commit()
    fetched = NutritionProfile.query.filter_by(user_id=user.id).first()
    assert fetched is not None
    assert fetched.diet_type == 'omnivore'
    assert fetched.allergies == ['lactose']


def test_meal_log_creation(app, db):
    user = _make_user(db)
    log = MealLog(user_id=user.id, date=date.today(), description='Гречка з куркою')
    db.session.add(log)
    db.session.commit()
    fetched = MealLog.query.filter_by(user_id=user.id).first()
    assert fetched.description == 'Гречка з куркою'
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/nutrition/test_routes.py::test_nutrition_profile_creation tests/nutrition/test_routes.py::test_meal_log_creation -v
```

Expected: `ImportError: cannot import name 'NutritionProfile'`

- [ ] **Step 3: Create `app/modules/nutrition/models.py`**

```python
from datetime import datetime
from app.extensions import db


class NutritionProfile(db.Model):
    __tablename__ = 'nutrition_profiles'
    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    diet_type        = db.Column(db.String(20))
    allergies        = db.Column(db.JSON)
    cooking_skill    = db.Column(db.String(20))
    budget           = db.Column(db.String(20))
    activity_outside = db.Column(db.String(20))
    bmr              = db.Column(db.Float)
    tdee             = db.Column(db.Float)
    calorie_target   = db.Column(db.Float)
    protein_g        = db.Column(db.Float)
    fat_g            = db.Column(db.Float)
    carbs_g          = db.Column(db.Float)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MealLog(db.Model):
    __tablename__ = 'meal_logs'
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date        = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=False)
    logged_at   = db.Column(db.DateTime, default=datetime.utcnow)
```

- [ ] **Step 4: Create `app/modules/nutrition/__init__.py`**

```python
from flask import Blueprint

bp = Blueprint('nutrition', __name__)

from . import routes  # noqa: F401, E402
from . import models  # noqa: F401, E402
```

- [ ] **Step 5: Register the blueprint in `app/__init__.py`**

Add after the coach blueprint block (after line `app.register_blueprint(coach_bp, url_prefix='/api')`):

```python
    from .modules.nutrition import bp as nutrition_bp
    app.register_blueprint(nutrition_bp, url_prefix='/api')
```

Note: the models are imported inside `nutrition/__init__.py`, so no separate model import is needed in `app/__init__.py`.

- [ ] **Step 6: Create a stub `app/modules/nutrition/routes.py`** so the blueprint import doesn't fail before routes are written:

```python
from . import bp  # noqa — routes added in later tasks
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
pytest tests/nutrition/test_routes.py::test_nutrition_profile_creation tests/nutrition/test_routes.py::test_meal_log_creation -v
```

Expected: `2 passed`

- [ ] **Step 8: Commit**

```bash
git add app/modules/nutrition/__init__.py app/modules/nutrition/models.py app/modules/nutrition/routes.py app/__init__.py tests/nutrition/test_routes.py
git commit -m "feat: add nutrition blueprint, models, and blueprint registration"
```

---

### Task 4: Profile Routes — GET + POST /api/nutrition/profile

**Files:**
- Modify: `app/modules/nutrition/routes.py`
- Modify: `tests/nutrition/test_routes.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/nutrition/test_routes.py`:

```python
from app.core.auth import create_jwt


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


def test_get_profile_no_profile(app, client, db):
    user = _make_user(db)
    r = client.get('/api/nutrition/profile', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['data'] is None


def test_get_profile_missing_weight(app, client, db):
    u = User(telegram_id=50002, name='NoWeight', onboarding_completed_at=datetime.utcnow())
    db.session.add(u)
    db.session.commit()
    r = client.get('/api/nutrition/profile', headers=_h(app, u.id))
    assert r.status_code == 400
    assert 'onboarding' in r.get_json()['error']['message'].lower()


def test_post_profile_creates_and_calculates(app, client, db):
    user = _make_user(db)  # female, 65kg, 168cm, age 28, fat_loss, 3 days/week
    body = {
        'diet_type': 'omnivore',
        'allergies': ['lactose'],
        'cooking_skill': 'beginner',
        'budget': 'medium',
        'activity_outside': 'sedentary',
    }
    r = client.post('/api/nutrition/profile', json=body, headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()['data']
    assert data['diet_type'] == 'omnivore'
    assert data['allergies'] == ['lactose']
    assert data['calorie_target'] > 0
    assert data['protein_g'] == 130.0   # 2.0 * 65
    assert data['water_ml'] == 2112.5   # 65 * 32.5


def test_post_profile_upserts(app, client, db):
    user = _make_user(db)
    body = {'diet_type': 'vegan', 'allergies': [], 'cooking_skill': 'advanced',
            'budget': 'high', 'activity_outside': 'moderately'}
    client.post('/api/nutrition/profile', json=body, headers=_h(app, user.id))
    body['diet_type'] = 'vegetarian'
    r = client.post('/api/nutrition/profile', json=body, headers=_h(app, user.id))
    assert r.get_json()['data']['diet_type'] == 'vegetarian'
    assert NutritionProfile.query.filter_by(user_id=user.id).count() == 1


def test_get_profile_returns_water_ml(app, client, db):
    user = _make_user(db)
    body = {'diet_type': 'omnivore', 'allergies': [], 'cooking_skill': 'intermediate',
            'budget': 'medium', 'activity_outside': 'lightly'}
    client.post('/api/nutrition/profile', json=body, headers=_h(app, user.id))
    r = client.get('/api/nutrition/profile', headers=_h(app, user.id))
    data = r.get_json()['data']
    assert 'water_ml' in data
    assert data['water_ml'] == 65.0 * 32.5
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/nutrition/test_routes.py::test_get_profile_no_profile tests/nutrition/test_routes.py::test_post_profile_creates_and_calculates -v
```

Expected: `404 NOT FOUND` (routes not implemented yet)

- [ ] **Step 3: Replace `app/modules/nutrition/routes.py` with full implementation**

```python
from datetime import date, timedelta
from flask import g, jsonify, request, Response, stream_with_context
from app.core.auth import require_auth
from app.core.models import User, AIConversation
from app.extensions import db
from . import bp
from .models import NutritionProfile, MealLog
from .calculator import calc_bmr, calc_tdee, calc_calorie_target, calc_macros, calc_water_ml


def _compute_and_save(profile: NutritionProfile, user: User) -> None:
    """Recalculate BMR/TDEE/macros and persist to profile."""
    bmr = calc_bmr(user.weight_kg, user.height_cm, user.age, user.gender)
    tdee = calc_tdee(bmr, profile.activity_outside, user.training_days_per_week or 0)
    calorie_target = calc_calorie_target(tdee, user.goal_primary)
    macros = calc_macros(user.weight_kg, calorie_target)
    profile.bmr = round(bmr, 1)
    profile.tdee = round(tdee, 1)
    profile.calorie_target = round(calorie_target, 1)
    profile.protein_g = macros['protein_g']
    profile.fat_g = macros['fat_g']
    profile.carbs_g = macros['carbs_g']


def _profile_to_dict(profile: NutritionProfile, user: User) -> dict:
    return {
        'diet_type':       profile.diet_type,
        'allergies':       profile.allergies or [],
        'cooking_skill':   profile.cooking_skill,
        'budget':          profile.budget,
        'activity_outside': profile.activity_outside,
        'calorie_target':  profile.calorie_target,
        'protein_g':       profile.protein_g,
        'fat_g':           profile.fat_g,
        'carbs_g':         profile.carbs_g,
        'water_ml':        calc_water_ml(user.weight_kg),
    }


@bp.route('/nutrition/profile', methods=['GET'])
@require_auth
def get_nutrition_profile():
    user = User.query.get(g.user_id)
    if not user.weight_kg or not user.height_cm:
        return jsonify({'success': False, 'error': {
            'code': 'INCOMPLETE_ONBOARDING',
            'message': 'Complete onboarding first (weight and height required)',
        }}), 400
    profile = NutritionProfile.query.filter_by(user_id=g.user_id).first()
    if not profile:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': _profile_to_dict(profile, user)})


@bp.route('/nutrition/profile', methods=['POST'])
@require_auth
def set_nutrition_profile():
    user = User.query.get(g.user_id)
    if not user.weight_kg or not user.height_cm:
        return jsonify({'success': False, 'error': {
            'code': 'INCOMPLETE_ONBOARDING',
            'message': 'Complete onboarding first (weight and height required)',
        }}), 400
    data = request.json or {}
    profile = NutritionProfile.query.filter_by(user_id=g.user_id).first()
    if not profile:
        profile = NutritionProfile(user_id=g.user_id)
        db.session.add(profile)
    profile.diet_type        = data.get('diet_type', profile.diet_type)
    profile.allergies        = data.get('allergies', profile.allergies)
    profile.cooking_skill    = data.get('cooking_skill', profile.cooking_skill)
    profile.budget           = data.get('budget', profile.budget)
    profile.activity_outside = data.get('activity_outside', profile.activity_outside)
    _compute_and_save(profile, user)
    db.session.commit()
    return jsonify({'success': True, 'data': _profile_to_dict(profile, user)})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/nutrition/test_routes.py::test_get_profile_no_profile tests/nutrition/test_routes.py::test_get_profile_missing_weight tests/nutrition/test_routes.py::test_post_profile_creates_and_calculates tests/nutrition/test_routes.py::test_post_profile_upserts tests/nutrition/test_routes.py::test_get_profile_returns_water_ml -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add app/modules/nutrition/routes.py tests/nutrition/test_routes.py
git commit -m "feat: add nutrition profile GET/POST endpoints"
```

---

### Task 5: Meal Log Routes — GET + POST /api/nutrition/meals/log

**Files:**
- Modify: `app/modules/nutrition/routes.py`
- Modify: `tests/nutrition/test_routes.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/nutrition/test_routes.py`:

```python
from datetime import timedelta


def test_post_meal_log(app, client, db):
    user = _make_user(db)
    r = client.post('/api/nutrition/meals/log',
                    json={'description': 'Гречка з куркою і овочами'},
                    headers=_h(app, user.id))
    assert r.status_code == 200
    assert r.get_json()['success'] is True
    log = MealLog.query.filter_by(user_id=user.id).first()
    assert log.description == 'Гречка з куркою і овочами'
    assert log.date == date.today()


def test_post_meal_log_requires_description(app, client, db):
    user = _make_user(db)
    r = client.post('/api/nutrition/meals/log', json={}, headers=_h(app, user.id))
    assert r.status_code == 400


def test_get_meal_log_returns_14_days(app, client, db):
    user = _make_user(db)
    today = date.today()
    db.session.add(MealLog(user_id=user.id, date=today, description='Сьогодні'))
    db.session.add(MealLog(user_id=user.id, date=today - timedelta(days=10), description='10 днів тому'))
    db.session.add(MealLog(user_id=user.id, date=today - timedelta(days=20), description='20 днів тому'))
    db.session.commit()
    r = client.get('/api/nutrition/meals/log', headers=_h(app, user.id))
    assert r.status_code == 200
    entries = r.get_json()['data']
    descs = [e['description'] for e in entries]
    assert 'Сьогодні' in descs
    assert '10 днів тому' in descs
    assert '20 днів тому' not in descs
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/nutrition/test_routes.py::test_post_meal_log tests/nutrition/test_routes.py::test_get_meal_log_returns_14_days -v
```

Expected: `404 NOT FOUND`

- [ ] **Step 3: Add meal log routes to `app/modules/nutrition/routes.py`**

Append after the profile routes:

```python
@bp.route('/nutrition/meals/log', methods=['POST'])
@require_auth
def log_meal():
    data = request.json or {}
    description = (data.get('description') or '').strip()
    if not description:
        return jsonify({'success': False, 'error': {
            'code': 'EMPTY', 'message': 'description required',
        }}), 400
    entry = MealLog(user_id=g.user_id, date=date.today(), description=description)
    db.session.add(entry)
    db.session.commit()
    return jsonify({'success': True, 'data': {
        'id': entry.id,
        'date': entry.date.isoformat(),
        'description': entry.description,
    }})


@bp.route('/nutrition/meals/log', methods=['GET'])
@require_auth
def get_meal_log():
    since = date.today() - timedelta(days=14)
    entries = (MealLog.query
               .filter(MealLog.user_id == g.user_id, MealLog.date >= since)
               .order_by(MealLog.date.desc(), MealLog.logged_at.desc())
               .all())
    return jsonify({'success': True, 'data': [
        {
            'id': e.id,
            'date': e.date.isoformat(),
            'description': e.description,
            'logged_at': e.logged_at.isoformat() if e.logged_at else None,
        }
        for e in entries
    ]})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/nutrition/test_routes.py::test_post_meal_log tests/nutrition/test_routes.py::test_post_meal_log_requires_description tests/nutrition/test_routes.py::test_get_meal_log_returns_14_days -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add app/modules/nutrition/routes.py tests/nutrition/test_routes.py
git commit -m "feat: add meal log GET/POST endpoints"
```

---

### Task 6: Context Builder — build_nutrition_context()

**Files:**
- Create: `app/modules/nutrition/context.py`
- Create: `tests/nutrition/test_context.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/nutrition/test_context.py
from datetime import date, timedelta, datetime
from app.core.models import User, DailyCheckin
from app.modules.nutrition.models import NutritionProfile, MealLog
from app.modules.nutrition.context import build_nutrition_context
from app.extensions import db


def _make_full_user(db):
    u = User(
        telegram_id=60001, name='CtxTest', gender='female', age=28,
        weight_kg=65.0, height_cm=168.0, goal_primary='fat_loss',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['home'], onboarding_completed_at=datetime.utcnow(),
    )
    db.session.add(u)
    db.session.commit()
    return u


def test_context_no_profile(app, db):
    user = _make_full_user(db)
    ctx = build_nutrition_context(user.id)
    assert 'not set up' in ctx


def test_context_with_profile(app, db):
    user = _make_full_user(db)
    p = NutritionProfile(
        user_id=user.id, diet_type='omnivore', allergies=['lactose'],
        calorie_target=1400.0, protein_g=130.0, fat_g=43.6, carbs_g=175.0,
        activity_outside='sedentary',
    )
    db.session.add(p)
    db.session.commit()
    ctx = build_nutrition_context(user.id)
    assert 'omnivore' in ctx
    assert '1400' in ctx
    assert 'lactose' in ctx


def test_context_includes_recent_meals(app, db):
    user = _make_full_user(db)
    today = date.today()
    db.session.add(MealLog(user_id=user.id, date=today, description='Вівсянка з ягодами'))
    db.session.add(MealLog(user_id=user.id, date=today - timedelta(days=10),
                           description='Стара страва'))
    db.session.commit()
    ctx = build_nutrition_context(user.id)
    assert 'Вівсянка з ягодами' in ctx
    assert 'Стара страва' not in ctx   # older than 7 days


def test_context_includes_todays_checkin(app, db):
    user = _make_full_user(db)
    checkin = DailyCheckin(user_id=user.id, date=date.today(), energy_level=7, sleep_quality=8)
    db.session.add(checkin)
    db.session.commit()
    ctx = build_nutrition_context(user.id)
    assert '7' in ctx   # energy level present
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/nutrition/test_context.py -v
```

Expected: `ImportError: cannot import name 'build_nutrition_context'`

- [ ] **Step 3: Create `app/modules/nutrition/context.py`**

```python
from datetime import date, timedelta
from app.extensions import db
from app.core.models import User, DailyCheckin
from app.modules.nutrition.models import NutritionProfile, MealLog


def build_nutrition_context(user_id: int) -> str:
    parts = ['\n## Nutrition Context']

    profile = NutritionProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        parts.append('Nutrition profile: not set up yet.')
    else:
        allergies_str = ', '.join(profile.allergies) if profile.allergies else 'none'
        parts.append(
            f'Diet: {profile.diet_type} | Allergies: {allergies_str} | '
            f'Skill: {profile.cooking_skill} | Budget: {profile.budget}'
        )
        parts.append(
            f'Targets: {profile.calorie_target} kcal | '
            f'Protein {profile.protein_g}g | Fat {profile.fat_g}g | Carbs {profile.carbs_g}g'
        )

    since = date.today() - timedelta(days=7)
    logs = (MealLog.query
            .filter(MealLog.user_id == user_id, MealLog.date >= since)
            .order_by(MealLog.date.desc())
            .limit(20)
            .all())
    if logs:
        parts.append('\nRecent meals (last 7 days):')
        for log in logs:
            parts.append(f'  {log.date}: {log.description}')
    else:
        parts.append('\nNo meals logged recently.')

    checkin = DailyCheckin.query.filter_by(user_id=user_id, date=date.today()).first()
    if checkin:
        parts.append(
            f'\nToday check-in: Energy {checkin.energy_level}/10, Sleep {checkin.sleep_quality}/10'
        )

    return '\n'.join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/nutrition/test_context.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add app/modules/nutrition/context.py tests/nutrition/test_context.py
git commit -m "feat: add nutrition context builder"
```

---

### Task 7: Chat Routes — GET thread + POST message (streaming)

**Files:**
- Modify: `app/modules/nutrition/routes.py`
- Modify: `tests/nutrition/test_routes.py`

Chat uses `stream_chat()` from `app/core/ai.py` with `module='nutrition'`, which stores messages in the existing `AIConversation` table. No new DB models needed.

- [ ] **Step 1: Write failing tests**

Add to `tests/nutrition/test_routes.py`:

```python
from unittest.mock import MagicMock, patch


def test_get_chat_thread_empty(app, client, db):
    user = _make_user(db)
    r = client.get('/api/nutrition/chat/thread', headers=_h(app, user.id))
    assert r.status_code == 200
    data = r.get_json()
    assert data['success'] is True
    assert data['data']['messages'] == []


def test_post_chat_message_streams(app, client, db):
    user = _make_user(db)
    profile = NutritionProfile(
        user_id=user.id, diet_type='omnivore', allergies=[],
        cooking_skill='beginner', budget='medium', activity_outside='sedentary',
        calorie_target=1400.0, protein_g=130.0, fat_g=43.6, carbs_g=175.0,
    )
    db.session.add(profile)
    db.session.commit()

    mock_client = MagicMock()
    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.text_stream = iter(['Спробуй ', 'вівсянку.'])
    mock_client.messages.stream.return_value = mock_stream

    with patch('app.core.ai.get_client', return_value=mock_client):
        r = client.post('/api/nutrition/chat/message',
                        json={'content': 'Що з яєць?'},
                        headers=_h(app, user.id))

    assert r.status_code == 200
    assert 'Спробуй' in r.data.decode('utf-8')


def test_post_chat_message_requires_content(app, client, db):
    user = _make_user(db)
    r = client.post('/api/nutrition/chat/message', json={}, headers=_h(app, user.id))
    assert r.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/nutrition/test_routes.py::test_get_chat_thread_empty tests/nutrition/test_routes.py::test_post_chat_message_streams -v
```

Expected: `404 NOT FOUND`

- [ ] **Step 3: Add imports and chat routes to `app/modules/nutrition/routes.py`**

At the top of the file, add to imports:

```python
from app.core.ai import stream_chat
from app.core.models import AIConversation
from .context import build_nutrition_context
```

Append the two route functions after the meal log routes:

```python
@bp.route('/nutrition/chat/thread', methods=['GET'])
@require_auth
def get_nutrition_thread():
    messages = (AIConversation.query
                .filter_by(user_id=g.user_id, module='nutrition')
                .order_by(AIConversation.created_at.desc())
                .limit(20)
                .all())
    return jsonify({'success': True, 'data': {
        'messages': [
            {'role': m.role, 'content': m.content, 'created_at': m.created_at.isoformat()}
            for m in reversed(messages)
        ],
    }})


@bp.route('/nutrition/chat/message', methods=['POST'])
@require_auth
def nutrition_chat_message():
    data = request.json or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'success': False, 'error': {
            'code': 'EMPTY', 'message': 'content required',
        }}), 400

    nutrition_context = build_nutrition_context(g.user_id)

    def generate():
        for chunk in stream_chat(g.user_id, 'nutrition', content,
                                  extra_context=nutrition_context):
            yield f"data: {chunk.replace(chr(10), ' ')}\n\n"
        yield 'data: [DONE]\n\n'

    return Response(stream_with_context(generate()), mimetype='text/event-stream')
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/nutrition/test_routes.py::test_get_chat_thread_empty tests/nutrition/test_routes.py::test_post_chat_message_streams tests/nutrition/test_routes.py::test_post_chat_message_requires_content -v
```

Expected: `3 passed`

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add app/modules/nutrition/routes.py tests/nutrition/test_routes.py
git commit -m "feat: add nutrition chat routes (GET thread + POST streaming message)"
```

---

### Task 8: Frontend — Setup wizard + targets card + AI chat UI

**Files:**
- Modify: `app/templates/index.html`

This task replaces the nutrition "coming soon" placeholder with the full UI.

- [ ] **Step 1: Add CSS for nutrition components**

Find `.coach-send-btn:disabled { opacity: .35; cursor: default; }` and add immediately after it:

```css
    /* ── Nutrition ── */
    #panel-nutrition { overflow: hidden; padding: 0; gap: 0; flex-direction: column; }
    #nutrition-setup { display: flex; flex-direction: column; align-items: center;
      justify-content: center; height: 100%; padding: 24px; }
    .nutr-setup-step { display: none; flex-direction: column; align-items: center;
      width: 100%; gap: 12px; }
    .nutr-setup-step.active { display: flex; }
    .nutr-setup-title { font-family: 'Barlow Condensed', sans-serif; font-size: 22px;
      color: var(--text); text-align: center; margin-bottom: 8px; }
    .nutr-setup-opts { display: flex; flex-wrap: wrap; gap: 10px; justify-content: center;
      width: 100%; }
    .nutr-opt-btn { background: var(--card); border: 1px solid var(--border);
      border-radius: 8px; color: var(--text); padding: 10px 16px; font-size: 14px;
      cursor: pointer; }
    .nutr-opt-btn.selected { border-color: var(--accent); color: var(--accent); }
    .nutr-opt-btn:active { background: var(--surface); }
    .nutr-skip-btn { background: none; border: none; color: var(--muted); font-size: 13px;
      margin-top: 4px; cursor: pointer; }
    #nutrition-main { display: none; flex-direction: column; height: 100%; overflow: hidden; }
    .nutr-targets-card { display: flex; gap: 18px; align-items: center; padding: 10px 16px;
      border-bottom: 1px solid var(--border); flex-shrink: 0; flex-wrap: wrap; }
    .nutr-target-item { font-size: 13px; color: var(--muted); }
    .nutr-target-val { font-family: 'Barlow Condensed', sans-serif; font-size: 16px;
      color: var(--text); }
    .nutr-messages { flex: 1; overflow-y: auto; padding: 14px 14px 8px;
      display: flex; flex-direction: column; gap: 10px; }
    .nutr-msg-user { align-self: flex-end; background: var(--accent); color: #fff;
      border-radius: 12px 12px 4px 12px; padding: 8px 12px; max-width: 80%; font-size: 14px; }
    .nutr-msg-ai { align-self: flex-start; background: var(--card);
      border-radius: 12px 12px 12px 4px; padding: 8px 12px; max-width: 90%;
      font-size: 14px; color: var(--text); line-height: 1.5; }
    .nutr-input-area { display: flex; align-items: flex-end; gap: 8px; padding: 10px 14px;
      border-top: 1px solid var(--border); flex-shrink: 0; }
    #nutr-input { flex: 1; background: var(--card); border: 1px solid var(--border);
      border-radius: 8px; color: var(--text); font-size: 14px; padding: 8px 12px;
      resize: none; max-height: 80px; }
    #nutr-input:focus { border-color: var(--accent); outline: none; }
    .nutr-send-btn { width: 38px; height: 38px; background: var(--accent); border: none;
      border-radius: 50%; color: #fff; font-size: 18px; cursor: pointer; flex-shrink: 0; }
    .nutr-send-btn:disabled { opacity: .35; cursor: default; }
    .nutr-log-btn { width: 38px; height: 38px; background: var(--card);
      border: 1px solid var(--border); border-radius: 50%; color: var(--accent);
      font-size: 16px; cursor: pointer; flex-shrink: 0; }
```

- [ ] **Step 2: Replace the nutrition panel HTML**

Find:
```html
    <div class="tab-panel" id="panel-nutrition">
      <div class="coming-soon"><div class="cs-line"></div><div class="cs-text">Nutrition</div><div class="cs-line"></div></div>
    </div>
```

Replace with:
```html
    <div class="tab-panel" id="panel-nutrition">
      <!-- Setup wizard (shown on first open) -->
      <div id="nutrition-setup">
        <div class="nutr-setup-step active" id="nutr-step-1">
          <div class="nutr-setup-title">Який тип дієти?</div>
          <div class="nutr-setup-opts">
            <button class="nutr-opt-btn" onclick="nutrSelectOpt(this,'diet_type','omnivore')">Всеїдний</button>
            <button class="nutr-opt-btn" onclick="nutrSelectOpt(this,'diet_type','vegetarian')">Вегетаріанець</button>
            <button class="nutr-opt-btn" onclick="nutrSelectOpt(this,'diet_type','vegan')">Веган</button>
            <button class="nutr-opt-btn" onclick="nutrSelectOpt(this,'diet_type','pescatarian')">Пескетаріанець</button>
          </div>
        </div>
        <div class="nutr-setup-step" id="nutr-step-2">
          <div class="nutr-setup-title">Алергії або непереносимості?</div>
          <div class="nutr-setup-opts">
            <button class="nutr-opt-btn" onclick="nutrToggleAllergy(this,'gluten')">Глютен</button>
            <button class="nutr-opt-btn" onclick="nutrToggleAllergy(this,'lactose')">Лактоза</button>
            <button class="nutr-opt-btn" onclick="nutrToggleAllergy(this,'nuts')">Горіхи</button>
            <button class="nutr-opt-btn" onclick="nutrToggleAllergy(this,'eggs')">Яйця</button>
            <button class="nutr-opt-btn" onclick="nutrToggleAllergy(this,'shellfish')">Морепродукти</button>
            <button class="nutr-opt-btn" onclick="nutrToggleAllergy(this,'soy')">Соя</button>
          </div>
          <button class="nutr-skip-btn" onclick="nutrNextStep(2)">Пропустити →</button>
          <button class="btn" onclick="nutrNextStep(2)" style="margin-top:8px;width:100%">Далі →</button>
        </div>
        <div class="nutr-setup-step" id="nutr-step-3">
          <div class="nutr-setup-title">Активність поза тренуваннями?</div>
          <div class="nutr-setup-opts">
            <button class="nutr-opt-btn" onclick="nutrSelectOpt(this,'activity_outside','sedentary')">Сидяча</button>
            <button class="nutr-opt-btn" onclick="nutrSelectOpt(this,'activity_outside','lightly')">Легка</button>
            <button class="nutr-opt-btn" onclick="nutrSelectOpt(this,'activity_outside','moderately')">Помірна</button>
            <button class="nutr-opt-btn" onclick="nutrSelectOpt(this,'activity_outside','very')">Висока</button>
          </div>
        </div>
        <div class="nutr-setup-step" id="nutr-step-4">
          <div class="nutr-setup-title">Кулінарні навички?</div>
          <div class="nutr-setup-opts">
            <button class="nutr-opt-btn" onclick="nutrSelectOpt(this,'cooking_skill','beginner')">Початківець</button>
            <button class="nutr-opt-btn" onclick="nutrSelectOpt(this,'cooking_skill','intermediate')">Середній</button>
            <button class="nutr-opt-btn" onclick="nutrSelectOpt(this,'cooking_skill','advanced')">Досвідчений</button>
          </div>
        </div>
        <div class="nutr-setup-step" id="nutr-step-5">
          <div class="nutr-setup-title">Харчовий бюджет?</div>
          <div class="nutr-setup-opts">
            <button class="nutr-opt-btn" onclick="nutrSelectOpt(this,'budget','low')">Низький</button>
            <button class="nutr-opt-btn" onclick="nutrSelectOpt(this,'budget','medium')">Середній</button>
            <button class="nutr-opt-btn" onclick="nutrSelectOpt(this,'budget','high')">Високий</button>
          </div>
        </div>
      </div>
      <!-- Main view (after setup) -->
      <div id="nutrition-main">
        <div class="nutr-targets-card" id="nutr-targets-card"></div>
        <div class="nutr-messages" id="nutr-messages"></div>
        <div class="nutr-input-area">
          <textarea id="nutr-input" placeholder="Що є в холодильнику?" rows="1"></textarea>
          <button class="nutr-log-btn" id="nutr-log-btn" onclick="logLastNutrMeal()" title="Записати як прийом їжі">✓</button>
          <button class="nutr-send-btn" id="nutr-send-btn" onclick="sendNutrMessage()">↑</button>
        </div>
      </div>
    </div>
```

- [ ] **Step 3: Add state variables**

In the `S = {` block, find `cycleAdaptation: null,` and add after it:

```javascript
  nutritionProfile: null,   // profile + targets from GET /api/nutrition/profile
  lastNutrAiMessage: null,  // last AI response text (for ✓ log button)
```

- [ ] **Step 4: Add nutrition JS functions**

Find the comment `// ── SESSION ──` and add the following block immediately before it:

```javascript
// ── NUTRITION ──
const _nutrData = {diet_type: null, allergies: [], activity_outside: null, cooking_skill: null, budget: null};

function nutrSelectOpt(btn, field, value) {
  const step = btn.closest('.nutr-setup-step');
  step.querySelectorAll('.nutr-opt-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  _nutrData[field] = value;
  const stepNum = parseInt(step.id.replace('nutr-step-', ''));
  setTimeout(() => nutrNextStep(stepNum), 300);
}

function nutrToggleAllergy(btn, allergy) {
  btn.classList.toggle('selected');
  if (btn.classList.contains('selected')) {
    if (!_nutrData.allergies.includes(allergy)) _nutrData.allergies.push(allergy);
  } else {
    _nutrData.allergies = _nutrData.allergies.filter(a => a !== allergy);
  }
}

function nutrNextStep(currentStep) {
  document.getElementById('nutr-step-' + currentStep).classList.remove('active');
  if (currentStep < 5) {
    document.getElementById('nutr-step-' + (currentStep + 1)).classList.add('active');
  } else {
    _submitNutrSetup();
  }
}

async function _submitNutrSetup() {
  const r = await api('POST', '/api/nutrition/profile', _nutrData);
  if (r.success) { S.nutritionProfile = r.data; renderNutritionTab(); }
}

async function loadNutritionTab() {
  const r = await api('GET', '/api/nutrition/profile');
  if (!r.success) return;
  if (!r.data) { renderNutritionSetup(); return; }
  S.nutritionProfile = r.data;
  renderNutritionTab();
}

function renderNutritionSetup() {
  document.getElementById('nutrition-setup').style.display = 'flex';
  document.getElementById('nutrition-main').style.display = 'none';
  document.querySelectorAll('.nutr-setup-step').forEach(s => s.classList.remove('active'));
  document.getElementById('nutr-step-1').classList.add('active');
}

async function renderNutritionTab() {
  document.getElementById('nutrition-setup').style.display = 'none';
  document.getElementById('nutrition-main').style.display = 'flex';
  const p = S.nutritionProfile;
  const water = (p.water_ml / 1000).toFixed(2);
  document.getElementById('nutr-targets-card').innerHTML =
    `<span class="nutr-target-item">\uD83D\uDD25 <span class="nutr-target-val">${Math.round(p.calorie_target)}</span> ккал</span>` +
    `<span class="nutr-target-item">\uD83E\uDD69 <span class="nutr-target-val">${Math.round(p.protein_g)}г</span></span>` +
    `<span class="nutr-target-item">\uD83D\uDCA7 <span class="nutr-target-val">${water}л</span></span>`;
  const cr = await api('GET', '/api/nutrition/chat/thread');
  if (cr.success) _renderNutrMessages(cr.data.messages);
}

function _renderNutrMessages(messages) {
  const container = document.getElementById('nutr-messages');
  container.innerHTML = '';
  for (const m of messages) {
    const div = document.createElement('div');
    div.className = m.role === 'user' ? 'nutr-msg-user' : 'nutr-msg-ai';
    div.textContent = m.content;
    container.appendChild(div);
  }
  container.scrollTop = container.scrollHeight;
}

async function sendNutrMessage() {
  const input = document.getElementById('nutr-input');
  const content = input.value.trim();
  if (!content) return;
  const sendBtn = document.getElementById('nutr-send-btn');
  sendBtn.disabled = true;
  input.value = '';
  const container = document.getElementById('nutr-messages');

  const userDiv = document.createElement('div');
  userDiv.className = 'nutr-msg-user';
  userDiv.textContent = content;
  container.appendChild(userDiv);

  const aiDiv = document.createElement('div');
  aiDiv.className = 'nutr-msg-ai';
  container.appendChild(aiDiv);
  container.scrollTop = container.scrollHeight;

  let fullText = '';
  try {
    const resp = await fetch('/api/nutrition/chat/message', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + S.jwt},
      body: JSON.stringify({content}),
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      for (const line of decoder.decode(value).split('\n')) {
        if (!line.startsWith('data: ')) continue;
        const chunk = line.slice(6);
        if (chunk === '[DONE]') break;
        fullText += chunk + ' ';
        aiDiv.textContent = fullText;
        container.scrollTop = container.scrollHeight;
      }
    }
    S.lastNutrAiMessage = fullText.trim();
  } finally {
    sendBtn.disabled = false;
  }
}

async function logLastNutrMeal() {
  if (!S.lastNutrAiMessage) return;
  const description = S.lastNutrAiMessage.slice(0, 200);
  const r = await api('POST', '/api/nutrition/meals/log', {description});
  if (r.success) {
    const btn = document.getElementById('nutr-log-btn');
    btn.textContent = '\u2713\u2713';
    setTimeout(() => { btn.textContent = '\u2713'; }, 1500);
  }
}
```

- [ ] **Step 5: Hook into `switchTab()`**

In the `switchTab()` function, find:
```javascript
  if (name === 'coach') loadCoachTab();
```

Add immediately after:
```javascript
  if (name === 'nutrition') loadNutritionTab();
```

- [ ] **Step 6: Manual test**

```bash
python run.py
```

Open app in browser and verify:
1. Click Nutrition tab → setup wizard shows (step 1: diet type)
2. Select diet type → auto-advances to step 2 (allergies)
3. Toggle allergy chips → click "Далі" to advance
4. Complete steps 3–5 → targets card appears with calories, protein, water
5. Type a message ("є яйця та картопля") → AI streams a response
6. Tap ✓ → log button briefly shows ✓✓, meal is logged
7. Leave and return to Nutrition tab → chat history preserved

- [ ] **Step 7: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: add nutrition tab UI (setup wizard + targets card + AI chat)"
```

---

## Self-Review

### Spec Coverage

| Requirement | Task |
|---|---|
| NutritionProfile model (all columns) | Task 3 |
| MealLog model | Task 3 |
| Alembic migration (both tables) | Task 1 |
| BMR — Mifflin-St Jeor (female/male) | Task 2 |
| TDEE — base factor + training bonus | Task 2 |
| Calorie target by goal (fat_loss/hypertrophy/strength/other) | Task 2 |
| Macros (protein 2g/kg, fat 28%, carbs remainder, clamp ≥ 0) | Task 2 |
| Water recommendation (32.5 ml/kg) | Task 2 |
| Blueprint registered in `app/__init__.py` | Task 3 |
| GET /api/nutrition/profile → null if no profile | Task 4 |
| GET /api/nutrition/profile → 400 if weight/height missing | Task 4 |
| GET /api/nutrition/profile → water_ml on-the-fly | Task 4 |
| POST /api/nutrition/profile → upsert + recalculate | Task 4 |
| POST /api/nutrition/meals/log | Task 5 |
| GET /api/nutrition/meals/log → 14 days | Task 5 |
| build_nutrition_context() → profile + meals + checkin | Task 6 |
| GET /api/nutrition/chat/thread → last 20 messages | Task 7 |
| POST /api/nutrition/chat/message → streaming SSE | Task 7 |
| Nutrition context injected into AI system prompt | Task 7 |
| Setup wizard 5 steps (diet, allergies, activity, skill, budget) | Task 8 |
| Skip button on allergies step | Task 8 |
| Auto-advance on single-select steps | Task 8 |
| Targets card (calories, protein, water) | Task 8 |
| Chat messages area with history on load | Task 8 |
| Streaming AI response rendered incrementally | Task 8 |
| ✓ button logs last AI message as meal | Task 8 |
| `switchTab('nutrition')` → `loadNutritionTab()` | Task 8 |

### Out of scope (confirmed)
Meal Plan, Supplements, calorie counting, food database, macro tracking, notifications.

### Type Consistency
- `calc_bmr / calc_tdee / calc_calorie_target / calc_macros / calc_water_ml` — defined Task 2, used Task 4 ✓
- `NutritionProfile / MealLog` — defined Task 3, used Tasks 4/5/6/7 ✓
- `build_nutrition_context(user_id)` — defined Task 6, imported in Task 7 routes ✓
- `_nutrData` — defined Task 8 JS, used in wizard functions Task 8 ✓
- `S.nutritionProfile / S.lastNutrAiMessage` — added to `S` in Task 8, used in Task 8 functions ✓
