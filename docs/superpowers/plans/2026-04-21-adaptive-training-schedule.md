# Adaptive Training Schedule Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow training on any day — if today has no scheduled workout, show the next incomplete workout of the current program week instead of a rest day.

**Architecture:** Add `_get_active_workout(week, user_id)` helper to `routes.py` that first checks for a scheduled workout today, then falls back to the next incomplete workout by `order_index`. Both `training_today` and `recommendations_today` endpoints switch to using this helper. Frontend renders a small "Позапланове тренування" badge when the response includes `ad_hoc: true`.

**Tech Stack:** Flask, SQLAlchemy, SQLite, Vanilla JS (Telegram Mini App)

---

## File Map

- **Modify:** `app/modules/training/routes.py` — add `_get_active_workout`, update two endpoints
- **Create:** `tests/training/test_adaptive_schedule.py` — 5 new tests
- **Modify:** `app/templates/index.html` — ad_hoc badge in hero card

---

### Task 1: Backend — `_get_active_workout` helper + `training_today`

**Files:**
- Modify: `app/modules/training/routes.py:143-167`
- Create: `tests/training/test_adaptive_schedule.py`

- [ ] **Step 1: Create the test file with 4 tests**

Create `tests/training/test_adaptive_schedule.py`:

```python
from datetime import date, datetime
from app.core.models import User
from app.core.auth import create_jwt
from app.modules.training.coach import save_program_from_dict
from app.modules.training.models import Mesocycle, ProgramWeek, Workout, WorkoutSession


def _off_days():
    """Two day_of_week values guaranteed to not be today."""
    today = date.today().weekday()
    return (today + 2) % 7, (today + 4) % 7


def _make_user(db):
    user = User(
        telegram_id=80101, name='AdaptTest', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='intermediate', training_days_per_week=3, session_duration_min=60,
        equipment=['full_gym'], onboarding_completed_at=datetime.utcnow()
    )
    db.session.add(user)
    db.session.commit()
    return user


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


def _make_two_workout_program(user_id, day1, day2):
    """Program with Workout A on day1 (order 0) and Workout B on day2 (order 1)."""
    return save_program_from_dict(user_id, {
        "name": "Adaptive Test", "periodization_type": "linear", "total_weeks": 4,
        "mesocycles": [{"name": "Block", "order_index": 0, "weeks_count": 4, "weeks": [{
            "week_number": 1, "notes": None, "workouts": [
                {"day_of_week": day1, "name": "Workout A", "order_index": 0, "exercises": [{
                    "exercise_name": "Squat", "order_index": 0, "notes": None,
                    "sets": [{"set_number": 1, "target_reps": "8-10",
                              "target_weight_kg": 60.0, "target_rpe": 7.0, "rest_seconds": 90}]
                }]},
                {"day_of_week": day2, "name": "Workout B", "order_index": 1, "exercises": [{
                    "exercise_name": "Bench Press", "order_index": 0, "notes": None,
                    "sets": [{"set_number": 1, "target_reps": "8-10",
                              "target_weight_kg": 50.0, "target_rpe": 7.0, "rest_seconds": 90}]
                }]},
            ]
        }]}]
    })


def test_ad_hoc_returns_next_incomplete_workout(client, app, db):
    """On an unscheduled day, returns first incomplete workout with ad_hoc=True."""
    day1, day2 = _off_days()
    user = _make_user(db)
    _make_two_workout_program(user.id, day1, day2)

    resp = client.get('/api/training/today', headers=_h(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data.get('rest_day') is not True
    assert data['name'] == 'Workout A'
    assert data['ad_hoc'] is True


def test_scheduled_day_no_ad_hoc(client, app, db):
    """On a scheduled day, ad_hoc key is absent from response."""
    today_dow = date.today().weekday()
    user = _make_user(db)
    save_program_from_dict(user.id, {
        "name": "Sched Test", "periodization_type": "linear", "total_weeks": 4,
        "mesocycles": [{"name": "Block", "order_index": 0, "weeks_count": 4, "weeks": [{
            "week_number": 1, "notes": None, "workouts": [{
                "day_of_week": today_dow, "name": "Today Workout", "order_index": 0,
                "exercises": [{"exercise_name": "Deadlift", "order_index": 0, "notes": None,
                               "sets": [{"set_number": 1, "target_reps": "5",
                                         "target_weight_kg": 80.0, "target_rpe": 8.0,
                                         "rest_seconds": 180}]}]
            }]
        }]}]
    })

    resp = client.get('/api/training/today', headers=_h(app, user.id))
    data = resp.get_json()['data']
    assert data['name'] == 'Today Workout'
    assert 'ad_hoc' not in data


def test_all_completed_returns_rest_day(client, app, db):
    """When all workouts in the week are completed, returns rest_day=True."""
    day1, day2 = _off_days()
    user = _make_user(db)
    program = _make_two_workout_program(user.id, day1, day2)

    mesocycle = Mesocycle.query.filter_by(program_id=program.id).first()
    week = ProgramWeek.query.filter_by(mesocycle_id=mesocycle.id, week_number=1).first()
    for wo in Workout.query.filter_by(program_week_id=week.id).all():
        db.session.add(WorkoutSession(
            user_id=user.id, workout_id=wo.id, date=date.today(), status='completed'
        ))
    db.session.commit()

    resp = client.get('/api/training/today', headers=_h(app, user.id))
    data = resp.get_json()['data']
    assert data.get('rest_day') is True


def test_ad_hoc_skips_completed_workouts(client, app, db):
    """When Workout A is completed, returns Workout B with ad_hoc=True."""
    day1, day2 = _off_days()
    user = _make_user(db)
    program = _make_two_workout_program(user.id, day1, day2)

    mesocycle = Mesocycle.query.filter_by(program_id=program.id).first()
    week = ProgramWeek.query.filter_by(mesocycle_id=mesocycle.id, week_number=1).first()
    workout_a = Workout.query.filter_by(program_week_id=week.id, order_index=0).first()
    db.session.add(WorkoutSession(
        user_id=user.id, workout_id=workout_a.id, date=date.today(), status='completed'
    ))
    db.session.commit()

    resp = client.get('/api/training/today', headers=_h(app, user.id))
    data = resp.get_json()['data']
    assert data['name'] == 'Workout B'
    assert data['ad_hoc'] is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/training/test_adaptive_schedule.py -v
```

Expected: all 4 tests FAIL — `ad_hoc` key missing, `rest_day` returned when it shouldn't be.

- [ ] **Step 3: Add `_get_active_workout` helper to `routes.py`**

In `app/modules/training/routes.py`, add this function right before the `# ── Today's workout ───` comment (around line 143):

```python
def _get_active_workout(week, user_id):
    """Return (workout, is_ad_hoc). is_ad_hoc=True when training on unscheduled day."""
    today_dow = date.today().weekday()

    # 1. Scheduled workout today
    scheduled = Workout.query.filter_by(
        program_week_id=week.id, day_of_week=today_dow
    ).first()
    if scheduled:
        return scheduled, False

    # 2. Next incomplete workout this week
    week_workouts = (Workout.query
                     .filter_by(program_week_id=week.id)
                     .order_by(Workout.order_index)
                     .all())
    if not week_workouts:
        return None, False

    completed_ids = {
        s.workout_id for s in
        WorkoutSession.query.filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.workout_id.in_([w.id for w in week_workouts]),
            WorkoutSession.status == 'completed',
        ).all()
    }
    for w in week_workouts:
        if w.id not in completed_ids:
            return w, True

    return None, False
```

- [ ] **Step 4: Update `training_today` to use the helper**

In `app/modules/training/routes.py`, replace lines 152–167 (the `today_dow` block inside `training_today`):

**Before:**
```python
    today_dow = date.today().weekday()
    days_elapsed = (date.today() - program.created_at.date()).days
    current_week_num = (days_elapsed // 7) + 1

    week = (ProgramWeek.query
            .join(Mesocycle)
            .filter(Mesocycle.program_id == program.id, ProgramWeek.week_number == current_week_num)
            .first())
    if not week:
        return jsonify({'success': True, 'data': None})

    workout = Workout.query.filter_by(program_week_id=week.id, day_of_week=today_dow).first()
    if not workout:
        return jsonify({'success': True, 'data': {'rest_day': True}})

    return jsonify({'success': True, 'data': _serialize_workout_with_sets(workout)})
```

**After:**
```python
    days_elapsed = (date.today() - program.created_at.date()).days
    current_week_num = (days_elapsed // 7) + 1

    week = (ProgramWeek.query
            .join(Mesocycle)
            .filter(Mesocycle.program_id == program.id, ProgramWeek.week_number == current_week_num)
            .first())
    if not week:
        return jsonify({'success': True, 'data': None})

    workout, is_ad_hoc = _get_active_workout(week, g.user_id)
    if not workout:
        return jsonify({'success': True, 'data': {'rest_day': True}})

    data = _serialize_workout_with_sets(workout)
    if is_ad_hoc:
        data['ad_hoc'] = True
    return jsonify({'success': True, 'data': data})
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/training/test_adaptive_schedule.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 6: Run full suite to check no regressions**

```bash
pytest -q
```

Expected: all previously passing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add app/modules/training/routes.py tests/training/test_adaptive_schedule.py
git commit -m "feat: add adaptive workout scheduling — fall back to next incomplete workout"
```

---

### Task 2: Backend — update `recommendations_today`

**Files:**
- Modify: `app/modules/training/routes.py:559-584`
- Modify: `tests/training/test_adaptive_schedule.py`

- [ ] **Step 1: Add test for `recommendations_today` on ad-hoc day**

Append to `tests/training/test_adaptive_schedule.py`:

```python
def test_recommendations_today_on_ad_hoc_day(client, app, db):
    """recommendations_today returns recs list on an unscheduled day (not empty dict)."""
    day1, day2 = _off_days()
    user = _make_user(db)
    _make_two_workout_program(user.id, day1, day2)

    resp = client.get('/api/training/recommendations/today', headers=_h(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert 'recommendations' in data
    assert isinstance(data['recommendations'], list)
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/training/test_adaptive_schedule.py::test_recommendations_today_on_ad_hoc_day -v
```

Expected: FAIL — `recommendations` is `[]` (endpoint returns early because it can't find a workout for today's `day_of_week`).

- [ ] **Step 3: Update `recommendations_today` to use `_get_active_workout`**

In `app/modules/training/routes.py`, inside `recommendations_today` replace the `today_dow` block (lines 570–584):

**Before:**
```python
    today_dow = date.today().weekday()
    days_elapsed = (date.today() - program.created_at.date()).days
    current_week_num = min((days_elapsed // 7) + 1, program.total_weeks)

    week = (ProgramWeek.query
            .join(Mesocycle)
            .filter(Mesocycle.program_id == program.id,
                    ProgramWeek.week_number == current_week_num)
            .first())
    if not week:
        return jsonify({'success': True, 'data': {'recommendations': [], 'deload_needed': False}})

    workout = Workout.query.filter_by(program_week_id=week.id, day_of_week=today_dow).first()
    if not workout:
        return jsonify({'success': True, 'data': {'recommendations': [], 'deload_needed': False}})
```

**After:**
```python
    days_elapsed = (date.today() - program.created_at.date()).days
    current_week_num = min((days_elapsed // 7) + 1, program.total_weeks)

    week = (ProgramWeek.query
            .join(Mesocycle)
            .filter(Mesocycle.program_id == program.id,
                    ProgramWeek.week_number == current_week_num)
            .first())
    if not week:
        return jsonify({'success': True, 'data': {'recommendations': [], 'deload_needed': False}})

    workout, _ = _get_active_workout(week, g.user_id)
    if not workout:
        return jsonify({'success': True, 'data': {'recommendations': [], 'deload_needed': False}})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/training/test_adaptive_schedule.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest -q
```

Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add app/modules/training/routes.py tests/training/test_adaptive_schedule.py
git commit -m "feat: recommendations_today uses adaptive workout lookup"
```

---

### Task 3: Frontend — ad_hoc badge in hero card

**Files:**
- Modify: `app/templates/index.html` (around line 1198–1208)

No new backend tests needed — purely a rendering change. The badge only appears when `w.ad_hoc === true`.

- [ ] **Step 1: Add `adHocBadge` variable and insert into hero card**

In `app/templates/index.html`, find this block (around line 1198):

```javascript
  el.innerHTML = deloadBanner + weeklyBtnHtml + `
    <div class="hero-card">
      <div class="hero-label">${t('today_training')}</div>
      <div class="hero-title">${w.name || 'WORKOUT'}</div>
      <div class="hero-stats">
```

Replace with:

```javascript
  const adHocBadge = w.ad_hoc
    ? `<div style="font-size:12px;color:var(--muted);margin-top:2px">Позапланове тренування</div>`
    : '';

  el.innerHTML = deloadBanner + weeklyBtnHtml + `
    <div class="hero-card">
      <div class="hero-label">${t('today_training')}</div>
      <div class="hero-title">${w.name || 'WORKOUT'}</div>
      ${adHocBadge}
      <div class="hero-stats">
```

- [ ] **Step 2: Run full test suite (smoke check)**

```bash
pytest -q
```

Expected: all tests still pass (no backend change in this task).

- [ ] **Step 3: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: show 'Позапланове тренування' badge on ad-hoc training day"
```
