# Adaptive Training Schedule — Design Spec (v1.0)

**Goal:** Allow training on any day of the week — if today has no scheduled workout, the app shows the next incomplete workout of the current program week instead of a rest day.

---

## Problem

`GET /training/today` and `GET /training/recommendations/today` both use `date.today().weekday()` to find a workout. If the program has no workout on that day, they return `rest_day: true` / empty recommendations — blocking the user from training.

---

## Solution

Extract a shared helper `_get_active_workout(week, user_id)` that replaces the `day_of_week` lookup with a two-step check:

1. **Scheduled workout today?** — look up `Workout` by `day_of_week == today.weekday()` (existing logic).
2. **No scheduled workout?** — find the first workout in the week (ordered by `order_index`) that has no completed `WorkoutSession` by this user. Return it with `ad_hoc=True`.
3. **All workouts done?** — return `None` (rest day, week complete).

A workout is "completed" if a `WorkoutSession` exists with `workout_id == workout.id`, `user_id == user_id`, and `status == 'completed'`.

---

## Architecture

Only `routes.py` changes — no schema changes, no new files.

### New helper (added to `routes.py`)

```python
def _get_active_workout(week, user_id):
    """Return (workout, is_ad_hoc) for today, or (None, False) if rest."""
    from datetime import date as _date
    today_dow = _date.today().weekday()

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

    # 3. All done
    return None, False
```

### Endpoints updated

**`GET /training/today`** — replace the `today_dow` + `Workout.query.filter_by` block:

```python
workout, is_ad_hoc = _get_active_workout(week, g.user_id)
if not workout:
    return jsonify({'success': True, 'data': {'rest_day': True}})
data = _serialize_workout_with_sets(workout)
if is_ad_hoc:
    data['ad_hoc'] = True
return jsonify({'success': True, 'data': data})
```

**`GET /training/recommendations/today`** — same replacement:

```python
workout, _ = _get_active_workout(week, g.user_id)
if not workout:
    return jsonify({'success': True, 'data': {'recommendations': [], 'deload_needed': False}})
# rest of function unchanged — uses workout.workout_exercises
```

`POST /training/session/start` — **no change** (already accepts `workout_id` in request body).

---

## Frontend (`index.html`)

When `data.ad_hoc === true`, show the workout normally but add a small label under the workout name:

```
Позапланове тренування
```

No other UI change. Rest day message stays the same when `data.rest_day === true`.

---

## Response shape

`GET /training/today` on an ad-hoc day:

```json
{
  "success": true,
  "data": {
    "id": 12,
    "name": "Push A",
    "day_of_week": 0,
    "ad_hoc": true,
    ...
  }
}
```

`data.day_of_week` still reflects the originally scheduled day (Monday = 0) — the frontend can display it if needed.

---

## What does NOT change

- `Workout.day_of_week` field — still stored and returned, still used to display the program schedule
- Program generation logic
- Session start / log-set / complete endpoints
- Any other training endpoints

---

## Tests

### Backend (`tests/training/test_adaptive_schedule.py`)

1. **Rest day with incomplete workout → returns next workout with `ad_hoc: true`** — program has workouts on Mon and Thu; hit endpoint on Wed → get Mon's workout with `ad_hoc: true`.
2. **Scheduled day → returns workout without `ad_hoc`** — hit on Mon → `ad_hoc` absent.
3. **All workouts completed → returns `rest_day: true`** — mark all week's workouts as completed; hit on Wed → rest day.
4. **Ad-hoc skips already-completed workouts** — Mon workout completed, hit on Tue → returns Thu workout with `ad_hoc: true`.
5. **`recommendations_today` on ad-hoc day returns recs** — same program/day setup; endpoint returns non-empty recommendations.
