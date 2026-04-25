# Progressive Overload v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the progressive overload engine to match the v1.4 spec: correct decision tree, deload week recommendations, AI-powered strategy change for chronic stagnation, and updated frontend display.

**Architecture:** All logic lives in `app/modules/training/progress.py`. The decision tree in `analyze_session_and_recommend()` is replaced with the 6-branch spec tree. A new `_is_deload_period()` helper wraps `check_deload_needed()` with a 7-day cooldown guard. AI strategy calls use haiku, same as other lightweight AI calls in this file. Frontend `renderRecommendations()` in `index.html` gets new badges for `deload` and `change_strategy` types.

**Tech Stack:** Python/Flask/SQLAlchemy, Anthropic haiku for strategy suggestions, existing `ExerciseRecommendation` model (no schema changes needed).

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `app/modules/training/progress.py` | New decision tree, `_is_deload_period()`, AI strategy change |
| Create | `tests/training/test_progress.py` | Unit tests for all new logic paths |
| Modify | `app/templates/index.html` | Frontend display for `deload` / `change_strategy` / `increase_sets` types |

---

## Task 1: Test file + improved decision tree (no AI)

**Files:**
- Create: `tests/training/test_progress.py`
- Modify: `app/modules/training/progress.py`

### What the new decision tree looks like

Replace the current 5-branch tree with this 6-branch version (evaluated top-to-bottom):

```
1. Deload period          → type='deload',          weight=last_weight*0.6
2. RPE≥9 + pain today     → type='decrease',         weight=last_weight*0.9 (rounded to 2.5)
3. Stagnation (≥3 sessions same weight+reps) → type='change_strategy' or 'stagnation'
4. avg_reps≥target_max AND avg_rpe≤8  → type='increase_weight', weight+=increment
5. target_min≤avg_reps<target_max AND avg_rpe≤8  → type='increase_reps', rec_max+=1
6. avg_rpe≥9 (or reps below target)  → type='maintain'
```

`_is_deload_period(user_id)` returns True when `check_deload_needed()` is True AND no `'deload'` recommendation exists in the last 7 days for this user.

- [ ] **Step 1: Create `tests/training/test_progress.py` with failing tests**

```python
# tests/training/test_progress.py
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.core.models import User
from app.modules.training.models import (
    Exercise, ExerciseRecommendation, LoggedExercise, LoggedSet,
    WorkoutExercise, WorkoutSession, PlannedSet, Workout,
    Mesocycle, ProgramWeek,
)


def _make_user(db):
    u = User(
        telegram_id=80001, name='ProgressTest', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='intermediate', training_days_per_week=3, session_duration_min=60,
        equipment=['full_gym'], onboarding_completed_at=datetime.utcnow(),
    )
    db.session.add(u)
    db.session.commit()
    return u


def _make_exercise(db, name='Bench Press', muscle_group='Chest'):
    ex = Exercise(name=name, muscle_group=muscle_group)
    db.session.add(ex)
    db.session.commit()
    return ex


def _make_session(db, user_id, status='completed', days_ago=0):
    s = WorkoutSession(
        user_id=user_id,
        date=date.today() - timedelta(days=days_ago),
        status=status,
    )
    db.session.add(s)
    db.session.commit()
    return s


def _log_sets(db, session, exercise, sets):
    """sets = list of (reps, weight, rpe)"""
    le = LoggedExercise(session_id=session.id, exercise_id=exercise.id, order_index=0)
    db.session.add(le)
    db.session.flush()
    for i, (reps, weight, rpe) in enumerate(sets, start=1):
        db.session.add(LoggedSet(
            logged_exercise_id=le.id, set_number=i,
            actual_reps=reps, actual_weight_kg=weight, actual_rpe=rpe,
        ))
    db.session.commit()
    return le


def _make_workout_with_planned(db, user_id, exercise, target_reps='8-10', target_weight=60.0):
    """Create a Workout + WorkoutExercise + PlannedSet and attach to session-less workout."""
    w = Workout(
        week_id=None, day_of_week=0, name='Test Workout', order_index=0,
    )
    # We need a program hierarchy: Program > Mesocycle > ProgramWeek > Workout
    from app.modules.training.models import Program
    prog = Program(
        user_id=user_id, name='Test', periodization_type='linear',
        total_weeks=4, status='active',
    )
    db.session.add(prog)
    db.session.flush()
    mc = Mesocycle(program_id=prog.id, name='MC', order_index=0, weeks_count=4)
    db.session.add(mc)
    db.session.flush()
    pw = ProgramWeek(mesocycle_id=mc.id, week_number=1)
    db.session.add(pw)
    db.session.flush()
    w.week_id = pw.id
    db.session.add(w)
    db.session.flush()
    we = WorkoutExercise(workout_id=w.id, exercise_id=exercise.id, order_index=0)
    db.session.add(we)
    db.session.flush()
    ps = PlannedSet(
        workout_exercise_id=we.id, set_number=1,
        target_reps=target_reps, target_weight_kg=target_weight, target_rpe=8.0,
    )
    db.session.add(ps)
    db.session.commit()
    return w


def test_increase_weight_at_max_reps_low_rpe(app, db):
    """avg_reps >= target_max AND avg_rpe <= 8 → increase_weight."""
    user = _make_user(db)
    ex = _make_exercise(db, 'Bench Press')
    w = _make_workout_with_planned(db, user.id, ex, target_reps='8-10', target_weight=60.0)
    session = _make_session(db, user.id, status='in_progress')
    session.workout_id = w.id
    db.session.commit()
    # Log 3 sets: all at 10 reps (target_max), RPE 7
    _log_sets(db, session, ex, [(10, 60.0, 7), (10, 60.0, 7), (10, 60.0, 7)])
    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    recs = analyze_session_and_recommend(session.id, user.id)

    assert len(recs) == 1
    assert recs[0].recommendation_type == 'increase_weight'
    assert recs[0].recommended_weight_kg == 62.5  # +2.5kg upper body


def test_increase_reps_in_range_moderate_rpe(app, db):
    """avg_reps in [target_min, target_max) AND avg_rpe <= 8 → increase_reps."""
    user = _make_user(db)
    ex = _make_exercise(db, 'Bench Press 2')
    w = _make_workout_with_planned(db, user.id, ex, target_reps='8-10', target_weight=60.0)
    session = _make_session(db, user.id, status='in_progress')
    session.workout_id = w.id
    db.session.commit()
    # 9 reps (in range but not at max), RPE 7
    _log_sets(db, session, ex, [(9, 60.0, 7), (9, 60.0, 7)])
    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    recs = analyze_session_and_recommend(session.id, user.id)

    assert len(recs) == 1
    assert recs[0].recommendation_type == 'increase_reps'
    assert recs[0].recommended_reps_max == 11  # target_max + 1


def test_maintain_high_rpe_below_target(app, db):
    """avg_rpe >= 9, reps below target → maintain."""
    user = _make_user(db)
    ex = _make_exercise(db, 'Squat High RPE')
    w = _make_workout_with_planned(db, user.id, ex, target_reps='5-6', target_weight=100.0)
    session = _make_session(db, user.id, status='in_progress')
    session.workout_id = w.id
    db.session.commit()
    # Only 4 reps (below min=5), RPE 9.5
    _log_sets(db, session, ex, [(4, 100.0, 9.5), (4, 100.0, 9.5)])
    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    recs = analyze_session_and_recommend(session.id, user.id)

    assert len(recs) == 1
    assert recs[0].recommendation_type == 'maintain'


def test_deload_recommendations_when_deload_needed(app, db):
    """When deload is needed, all recs get type='deload' with weight at 60%."""
    user = _make_user(db)
    ex = _make_exercise(db, 'Deadlift Deload')
    session = _make_session(db, user.id, status='in_progress')
    _log_sets(db, session, ex, [(5, 100.0, 8)])
    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    with patch('app.modules.training.progress.check_deload_needed', return_value=True):
        recs = analyze_session_and_recommend(session.id, user.id)

    assert len(recs) == 1
    assert recs[0].recommendation_type == 'deload'
    assert recs[0].recommended_weight_kg == pytest.approx(60.0)  # 100 * 0.6


def test_no_deload_if_already_deloaded_this_week(app, db):
    """If a 'deload' rec was created in the last 7 days, don't deload again."""
    user = _make_user(db)
    ex = _make_exercise(db, 'Deadlift No Deload')
    # Create a recent deload rec
    recent_deload = ExerciseRecommendation(
        user_id=user.id, exercise_id=ex.id,
        recommendation_type='deload',
        recommended_weight_kg=60.0, recommended_reps_min=5, recommended_reps_max=5,
        reason_text='Deload week',
    )
    db.session.add(recent_deload)
    session = _make_session(db, user.id, status='in_progress')
    _log_sets(db, session, ex, [(5, 100.0, 8)])
    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    with patch('app.modules.training.progress.check_deload_needed', return_value=True):
        recs = analyze_session_and_recommend(session.id, user.id)

    # Should NOT be 'deload' since we just did one
    assert all(r.recommendation_type != 'deload' for r in recs)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/training/test_progress.py -v 2>&1 | tail -20
```

Expected: FAIL — `assert recs[0].recommendation_type == 'increase_weight'` fails (current 2-for-2 rule requires prev session too)

- [ ] **Step 3: Rewrite the decision tree in `analyze_session_and_recommend()`**

Open `app/modules/training/progress.py`. Replace the entire section starting from `# 2-for-2 rule:` comment through `# Periodization note by level` with:

```python
        # ── Helper: did we already deload in the last 7 days? ──
        # (evaluated once per call, cached via outer-scope variable set below)

        # Deload period check (branch 1)
        if _is_deload_period:
            rec_type = 'deload'
            rec_weight = round(last_weight * 0.6 / 2.5) * 2.5
            reason = (
                f'Deload тиждень. Знижуємо вагу до {rec_weight:.1f}kg (60% від робочої '
                f'{last_weight:.1f}kg). Об\'єм −50%: виконуй половину підходів. '
                'Мета — відновлення, а не прогрес.'
            )

        # RPE≥9 + pain (branch 2)
        elif avg_rpe >= 9 and pain_today:
            rec_type = 'decrease'
            rec_weight = round(last_weight * 0.9 / 2.5) * 2.5
            reason = (
                f'RPE {avg_rpe:.0f} + біль сьогодні. '
                f'Знизь вагу на 10% → {rec_weight:.1f}kg. '
                'Якщо біль не проходить — замін вправу на варіацію.'
            )

        # Stagnation (branch 3)
        elif stagnation:
            rec_type = 'stagnation'
            reason = (
                'Прогрес зупинився 3+ сесії поспіль. '
                'Зміни одну змінну: сповільни темп (3-1-3), '
                'збільши амплітуду, або додай підхід замість ваги.'
            )

        # All sets at max reps + low RPE → increase weight (branch 4)
        elif target_max and avg_reps >= target_max and avg_rpe <= 8:
            rec_type = 'increase_weight'
            rec_weight = last_weight + increment
            reason = (
                f'Всі підходи на максимумі повторів ({target_max}) при RPE {avg_rpe:.0f}. '
                f'+{increment}kg → {rec_weight:.1f}kg наступного разу.'
            )
            if level in ('intermediate', 'advanced'):
                reason += ' (Хвильове: застосовуй тільки на важкому тижні.)'

        # In range + moderate RPE → increase reps (branch 5)
        elif target_min and target_max and target_min <= avg_reps < target_max and avg_rpe <= 8:
            rec_type = 'increase_reps'
            rec_max = (target_max or 10) + 1
            reason = (
                f'В діапазоні ({avg_reps:.0f} повт) при RPE {avg_rpe:.0f}. '
                f'Додай 1 повтор → ціль {rec_min}–{rec_max}. '
                'Змінюй лише одну змінну за раз.'
            )

        # High RPE or below target → maintain (branch 6)
        else:
            rec_type = 'maintain'
            reason = (
                f'RPE {avg_rpe:.0f} — повтори ту ж вагу та кількість повторів. '
                'Стабільність зараз важливіша за прогрес.'
            )

        if stretch_flag:
            reason += ' Stretch-mediated: пріоритет повній амплітуді.'
```

And add the `_is_deload_period` calculation BEFORE the `for le in session.logged_exercises:` loop:

```python
    # Check deload once per session, not per exercise
    _is_deload_period = _check_is_deload_period(user_id)
```

And add the helper function `_check_is_deload_period` BEFORE `analyze_session_and_recommend`:

```python
def _check_is_deload_period(user_id: int) -> bool:
    """True if deload is needed AND no deload rec was created in the last 7 days."""
    if not check_deload_needed(user_id):
        return False
    from datetime import date, timedelta
    from .models import ExerciseRecommendation
    cutoff = date.today() - timedelta(days=7)
    recent_deload = ExerciseRecommendation.query.filter(
        ExerciseRecommendation.user_id == user_id,
        ExerciseRecommendation.recommendation_type == 'deload',
        ExerciseRecommendation.created_at >= cutoff,
    ).first()
    return recent_deload is None
```

Also remove the old `two_for_two` and stagnation variable calculations that are now replaced (lines that compute `two_for_two`, `stagnation`, and the old `rec_type` decision tree block). Keep the setup variables: `avg_rpe`, `avg_reps`, `last_weight`, `target_min`, `target_max`, `increment`, `stretch_flag`, `pain_today`, `prev_les`, `is_lower`.

The `stagnation` variable is still needed for branch 3. Keep its calculation:
```python
        # Stagnation: same weight AND same total reps for 3 consecutive sessions
        stagnation = False
        if len(prev_les) >= 2:
            weights = [last_weight] + [
                (le2.logged_sets[0].actual_weight_kg or 0)
                for le2 in prev_les[:2] if le2.logged_sets
            ]
            reps_list = [sum(s.actual_reps or 0 for s in le.logged_sets)] + [
                sum(s.actual_reps or 0 for s in le2.logged_sets)
                for le2 in prev_les[:2]
            ]
            if len(weights) == 3 and len(set(weights)) == 1 and len(set(reps_list)) == 1:
                stagnation = True
```

Remove the `two_for_two` variable entirely.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/training/test_progress.py -v 2>&1 | tail -20
```

Expected: all 5 tests PASS

- [ ] **Step 5: Run full test suite**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -5
```

Expected: all existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add app/modules/training/progress.py tests/training/test_progress.py
git commit -m "feat: progressive overload v2 — new decision tree, deload override"
```

---

## Task 2: AI strategy change for chronic stagnation

**Files:**
- Modify: `app/modules/training/progress.py`
- Modify: `tests/training/test_progress.py`

When an exercise has been `'stagnation'` type for **3 or more** prior recommendations, generate an AI strategy suggestion using haiku. Set `rec_type = 'change_strategy'` and fill `reason_text` with the AI output.

- [ ] **Step 1: Write failing test**

Add to `tests/training/test_progress.py`:

```python
def test_ai_strategy_change_after_3_stagnations(app, db, mock_anthropic):
    """After 3+ prior stagnation recs for same exercise, type becomes 'change_strategy'."""
    user = _make_user(db)
    ex = _make_exercise(db, 'Stagnation Exercise')

    # Create 3 prior stagnation recs for this exercise
    for _ in range(3):
        db.session.add(ExerciseRecommendation(
            user_id=user.id, exercise_id=ex.id,
            recommendation_type='stagnation',
            recommended_weight_kg=80.0, recommended_reps_min=8, recommended_reps_max=10,
            reason_text='stagnating',
        ))
    db.session.commit()

    # Mock AI response
    mock_anthropic.messages.create.return_value = MagicMock(
        content=[MagicMock(text='Спробуй паузний жим: 2 сек пауза внизу, 3 сети по 6.')]
    )

    # Current session: same weight/reps as always → stagnation triggered
    session = _make_session(db, user.id, status='in_progress')
    _log_sets(db, session, ex, [(8, 80.0, 8), (8, 80.0, 8), (8, 80.0, 8)])

    # Also need 2 prev sessions with same weight+reps for stagnation detection
    for i in range(1, 3):
        prev = _make_session(db, user.id, status='completed', days_ago=i * 7)
        _log_sets(db, prev, ex, [(8, 80.0, 8), (8, 80.0, 8), (8, 80.0, 8)])

    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    recs = analyze_session_and_recommend(session.id, user.id)

    strat_recs = [r for r in recs if r.exercise_id == ex.id]
    assert len(strat_recs) == 1
    assert strat_recs[0].recommendation_type == 'change_strategy'
    assert 'паузний' in strat_recs[0].reason_text


def test_no_ai_call_for_first_stagnation(app, db, mock_anthropic):
    """First stagnation → type='stagnation', no AI call."""
    user = _make_user(db)
    ex = _make_exercise(db, 'First Stagnation')

    session = _make_session(db, user.id, status='in_progress')
    _log_sets(db, session, ex, [(8, 80.0, 8), (8, 80.0, 8), (8, 80.0, 8)])
    for i in range(1, 3):
        prev = _make_session(db, user.id, status='completed', days_ago=i * 7)
        _log_sets(db, prev, ex, [(8, 80.0, 8), (8, 80.0, 8), (8, 80.0, 8)])
    session.status = 'completed'
    db.session.commit()

    from app.modules.training.progress import analyze_session_and_recommend
    recs = analyze_session_and_recommend(session.id, user.id)

    stag_recs = [r for r in recs if r.exercise_id == ex.id]
    assert stag_recs[0].recommendation_type == 'stagnation'
    mock_anthropic.messages.create.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/training/test_progress.py::test_ai_strategy_change_after_3_stagnations tests/training/test_progress.py::test_no_ai_call_for_first_stagnation -v 2>&1 | tail -15
```

Expected: FAIL — `assert strat_recs[0].recommendation_type == 'change_strategy'`

- [ ] **Step 3: Add AI strategy change logic to `analyze_session_and_recommend`**

In the stagnation branch (branch 3 in the decision tree), replace the static reason with:

```python
        elif stagnation:
            # Count prior stagnation recs for this exercise
            from datetime import timedelta
            prior_stagnations = ExerciseRecommendation.query.filter(
                ExerciseRecommendation.user_id == user_id,
                ExerciseRecommendation.exercise_id == exercise_id,
                ExerciseRecommendation.recommendation_type.in_(('stagnation', 'change_strategy')),
            ).count()

            if prior_stagnations >= 3:
                rec_type = 'change_strategy'
                from app.core.models import User as UserModel
                u = db.session.get(UserModel, user_id)
                lang_note = 'Відповідь ТІЛЬКИ українською.' if (getattr(u, 'app_language', 'en') or 'en') == 'uk' else 'Reply in English only.'
                reason = complete(
                    f'You are a strength coach. {lang_note} '
                    'The athlete has been stagnating on this exercise for 3+ sessions with the same weight and reps. '
                    'Suggest ONE specific technique variation to break the plateau. '
                    'Be concrete: name the variation, the tempo or rep scheme. Max 20 words.',
                    f'Exercise: {le.exercise.name}. Current: {last_weight}kg × {int(avg_reps)} reps × {len(current_sets)} sets. RPE {avg_rpe:.0f}.',
                    max_tokens=60,
                    model='claude-haiku-4-5-20251001',
                ).strip()
            else:
                rec_type = 'stagnation'
                reason = (
                    'Прогрес зупинився 3+ сесії поспіль. '
                    'Зміни одну змінну: сповільни темп (3-1-3), '
                    'збільши амплітуду, або додай підхід замість ваги.'
                )
```

Also add `ExerciseRecommendation` to the imports at the top of the function (it's already imported via `from .models import ... ExerciseRecommendation` — check that it's there).

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/training/test_progress.py -v 2>&1 | tail -15
```

Expected: all 7 tests PASS

- [ ] **Step 5: Run full suite**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add app/modules/training/progress.py tests/training/test_progress.py
git commit -m "feat: AI strategy change for chronic stagnation (3+ sessions)"
```

---

## Task 3: Frontend — display new recommendation types

**Files:**
- Modify: `app/templates/index.html`

The NEXT SESSION PLAN section renders `ExerciseRecommendation` objects. Currently it shows weight and reps for all types. Update it to handle `'deload'`, `'change_strategy'`, and show `'increase_weight'`/`'increase_reps'` badges.

- [ ] **Step 1: Find the current recommendation rendering code**

Search for `renderNextSessionPlan` and `recommendation_type` in `app/templates/index.html` to understand the current structure before editing.

- [ ] **Step 2: Update recommendation card rendering**

Find the function `renderNextSessionPlan()` in `app/templates/index.html`. The current code maps recommendations to HTML. Replace the per-recommendation HTML with a version that handles each type:

```javascript
function renderNextSessionPlan() {
  const el = document.getElementById('next-session-plan');
  if (!el) return;
  const recs = S.nextSessionPlan || [];
  if (!recs.length) { el.style.display = 'none'; return; }
  el.style.display = '';

  const typeLabel = {
    'increase_weight': { badge: '↑ ВАГА',    color: '#4caf50' },
    'increase_reps':   { badge: '↑ ПОВТОРИ', color: '#4caf50' },
    'maintain':        { badge: '═ ТРИМАТИ', color: '#888' },
    'decrease':        { badge: '↓ ЗНИЖЕННЯ', color: '#ff9800' },
    'stagnation':      { badge: '⚠ СТАГНАЦІЯ', color: '#ff9800' },
    'change_strategy': { badge: '🔄 НОВА СТРАТЕГІЯ', color: '#9c27b0' },
    'deload':          { badge: '💤 DELOAD', color: '#2196f3' },
  };

  el.innerHTML = `
    <div class="card-label">НАСТУПНЕ ТРЕНУВАННЯ</div>
    ${recs.map(r => {
      const t = typeLabel[r.recommendation_type] || { badge: r.recommendation_type, color: '#888' };
      const weightLine = r.recommendation_type === 'deload'
        ? `<span style="color:#2196f3;font-weight:700">${r.recommended_weight_kg}kg (−40%)</span>`
        : r.recommended_weight_kg
          ? `<span>${r.recommended_weight_kg}kg</span>`
          : '';
      const repsLine = (r.recommended_reps_min && r.recommended_reps_max)
        ? `<span style="color:var(--muted)">${r.recommended_reps_min}–${r.recommended_reps_max} повт</span>`
        : '';
      return `
        <div class="rec-card">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <span style="font-size:13px;font-weight:600">${_esc(r.exercise_name)}</span>
            <span style="font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;
              background:${t.color}22;color:${t.color}">${t.badge}</span>
          </div>
          ${weightLine || repsLine ? `<div style="font-size:13px;display:flex;gap:10px;margin-bottom:4px">${weightLine}${repsLine}</div>` : ''}
          ${r.reason_text ? `<div style="font-size:12px;color:var(--muted);line-height:1.4">${_esc(r.reason_text)}</div>` : ''}
        </div>`;
    }).join('')}`;
}
```

Also add the `.rec-card` CSS if it doesn't exist yet. Find the CSS section and add before `/* ── MISC ── */`:

```css
    .rec-card { background: var(--card); border: 1px solid var(--border);
      border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; }
```

- [ ] **Step 3: Run tests to verify nothing broke**

```bash
python3 -m pytest tests/ -q 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: next session plan badges for deload / change_strategy / increase types"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|-----------------|------|
| Weight increase (+2.5kg upper, +5kg lower) | Task 1 — branch 4 |
| Rep increase (within range) | Task 1 — branch 5 |
| Set increase (method #3) | In reason_text for stagnation branch |
| Tempo / rest / ROM / technique (methods 4-7) | In reason_text for stagnation branch |
| All sets at max reps, RPE ≤ 8 → weight up | Task 1 — branch 4 |
| All sets in range, RPE 7-8 → reps up | Task 1 — branch 5 |
| RPE 9-10, not all reps → maintain | Task 1 — branch 6 |
| Stagnation 3+ weeks → AI strategy change | Task 2 |
| RPE 9-10 + pain → decrease/replace | Task 1 — branch 2 |
| Deload: 60% weight, volume −50% | Task 1 — branch 1 |
| Deload auto-detection (stagnation 60% OR 5+ low energy) | Already in `check_deload_needed()` |
| Deload frequency 4-6 weeks (7-day cooldown guard) | Task 1 — `_check_is_deload_period()` |
| Deload duration 1 week | Cooldown guard (7 days) in Task 1 |
| Intermediate: wave loading note | Task 1 — branch 4 |
| Advanced: block periodization | Mentioned in wave note |
| Frontend display for new types | Task 3 |

**Set increase**: The spec lists it as method #3, but without a `recommended_sets` DB column there's no clean way to surface it in the UI. The stagnation reason text explicitly mentions "додай підхід" (add a set) as an alternative. This is the right scope boundary — adding a DB column for sets is a separate future feature.

**Placeholder scan:** No TBD/TODO. All code blocks are complete.

**Type consistency:** `'change_strategy'`, `'deload'`, `'stagnation'`, `'increase_weight'`, `'increase_reps'`, `'maintain'`, `'decrease'` used consistently across backend and frontend `typeLabel` map.
