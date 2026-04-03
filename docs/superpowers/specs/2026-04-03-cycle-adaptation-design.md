# Menstrual Cycle Adaptation — Design Spec (v1.0)

**Goal:** Adapt training recommendations based on the user's menstrual cycle phase, shown as a pre-workout card with "Adapt / Ignore" choice.

---

## Overview

When a female user with `menstrual_tracking=true` and `last_period_date` set taps "Почати тренування", a cycle phase card appears before the session starts. The card shows the current phase, key recommendations, and auto-calculated weight adaptations. The user can apply adaptations or ignore them.

---

## Data Model

### Existing fields (no migration needed for these)

**User model (`app/core/models.py`):**
- `menstrual_tracking` (Boolean, default False)
- `cycle_length_days` (Integer, nullable) — default 28 if null
- `last_period_date` (Date, nullable)

**DailyCheckin model (`app/core/models.py`):**
- `cycle_day` (Integer, nullable) — manual override: if set in today's checkin, use instead of calculated day

### New fields (one migration)

**WorkoutSession model (`app/modules/training/models.py`):**
- `cycle_phase` (String(20), nullable) — phase at time of session ('menstrual' / 'follicular' / 'ovulation' / 'luteal')
- `cycle_adapted` (Boolean, default False) — whether user chose "Adapt"

---

## Phase Calculation

```python
cycle_day = (date.today() - user.last_period_date).days % (user.cycle_length_days or 28) + 1
```

If `DailyCheckin.cycle_day` exists for today → override calculated `cycle_day`.

### Phase ranges

| Phase | Days | Weight modifier | PR allowed | Card shown |
|-------|------|----------------|------------|------------|
| menstrual | 1–5 | 1.0 (no auto-reduction) | yes | Only if today's checkin has energy < 5 |
| follicular | 6–11 | 1.0 | yes | No card — small badge only ("💪 best time for PRs") |
| ovulation | 12–16 | 1.0 | yes | Yes — joint laxity warning + plyometrics flag |
| luteal | 17–(cycle_length) | 0.9 (−10%) | no | Yes — weight reduction + technique focus |

---

## Backend

### New file: `app/modules/training/cycle.py`

Three public functions:

**`get_cycle_phase(user) → dict`**

Returns:
```python
{
    "phase": "luteal",           # menstrual | follicular | ovulation | luteal
    "cycle_day": 19,
    "modifier": 0.9,             # weight multiplier to apply
    "show_card": True,           # whether to show pre-workout card
    "phase_title": "Лютеальна фаза",
    "phase_description": "Знижена працездатність — це нормально. −10% ваги, без рекордів.",
    "warnings": [],              # list of string warnings (e.g. plyometrics)
    "pr_allowed": False,
}
```

Returns `{"show_card": False}` if `menstrual_tracking=False` or `last_period_date=None`.

`show_card` logic by phase:
- menstrual: True only if today's `DailyCheckin.energy_level < 5` (otherwise just badge)
- follicular: always False (badge only)
- ovulation: always True (ligament warning)
- luteal: always True (weight modifier)

`get_cycle_phase` reads today's `DailyCheckin` for the user to check energy level.

**`get_cycle_adaptations(user, today_recommendations) → list`**

Takes the user's current `ExerciseRecommendation` list for today.

For each recommendation:
- Apply `modifier` to `recommended_weight_kg` → `adapted_weight`
- For ovulation phase: `adapted_weight = original_weight` (no modifier), but call haiku AI if exercise is plyometric → suggest lower-impact alternative in `ai_note`
- For luteal phase: call haiku AI for heavy compound exercises (squat, deadlift, bench press, overhead press) → suggest lighter variation or note

Returns:
```python
[
    {
        "exercise_name": "Присід зі штангою",
        "exercise_id": 3,
        "original_weight": 70.0,
        "adapted_weight": 63.0,           # round to nearest 2.5kg
        "ai_note": "Заміни на goblet squat 28kg × 12 — легше на суглоби."  # or None
    },
    ...
]
```

AI calls: haiku, max_tokens=60, only for compound/plyometric exercises, max 3 AI calls per session.

**`_is_plyometric(exercise_name: str) → bool`**

Keyword check: jump, box jump, burpee, hop, bound, стрибок, бурпі.

### New endpoint: `GET /api/training/cycle/phase`

Auth: Bearer JWT (same as all training endpoints).

Query param: `workout_id` (optional) — used to fetch today's targets for adaptation preview.

Response:
```json
{
  "success": true,
  "data": {
    "phase": "luteal",
    "cycle_day": 19,
    "show_card": true,
    "modifier": 0.9,
    "phase_title": "Лютеальна фаза",
    "phase_description": "Знижена працездатність — це нормально. −10% ваги, без рекордів.",
    "warnings": [],
    "pr_allowed": false,
    "adaptations": [
      {
        "exercise_name": "Присід зі штангою",
        "exercise_id": 3,
        "original_weight": 70.0,
        "adapted_weight": 63.0,
        "ai_note": "Або goblet squat 28kg × 12 — легше на суглоби."
      }
    ]
  }
}
```

### Modified: `POST /api/training/session/start`

Accepts two new optional body fields:
```json
{
  "workout_id": 5,
  "cycle_phase": "luteal",
  "cycle_adapted": true
}
```

Saves to `WorkoutSession.cycle_phase` and `WorkoutSession.cycle_adapted`.

---

## Frontend (`app/templates/index.html`)

### Changed flow for "Почати тренування"

```
startWorkout()
  → GET /api/training/cycle/phase?workout_id=X
  → if show_card == false: proceed directly to session/start
  → if show_card == true: show cycle overlay
      → user taps "АДАПТУВАТИ":
          S.cycleAdaptation = { modifier, adaptations }
          session/start with { cycle_phase, cycle_adapted: true }
          renderTodayTargets() shows adapted weights + ai_note in yellow
      → user taps "ІГНОРУВАТИ":
          session/start with { cycle_phase, cycle_adapted: false }
          normal targets, no adaptation
```

### Cycle phase card (overlay)

Reuses existing overlay infrastructure. Content:

```
[phase emoji + title]   • день N
[phase_description]

Адаптації:
• Exercise → Xkg (from Ykg)
  💡 ai_note
...

[АДАПТУВАТИ]    [ІГНОРУВАТИ]
```

Shown via `openOverlay('overlay-cycle')` — new overlay div added to HTML.

### Passive phase badge

Small badge in Train tab header (only when `menstrual_tracking=true` and `last_period_date` set):
- Follicular: `💪 Фолікулярна • день 8`
- Ovulation: `⚠️ Овуляція • день 13`
- Luteal: `🌙 Лютеальна • день 19`
- Menstrual: `🩸 Менструальна • день 2`

Fetched via `GET /api/training/cycle/phase` on tab load (no workout_id → no adaptations, just phase info).

### Adapted targets display

When `S.cycleAdaptation` is set, `renderTodayTargets()` shows:
- Adapted weight instead of original (applied via `modifier`)
- Yellow note card below exercise if `ai_note` present: `💡 [ai_note]`

### Manual cycle day correction in checkin

In the daily checkin form, add a numeric input:
- Label: "День циклу (якщо відрізняється від розрахованого)"
- Only shown if `user.menstrual_tracking == true`
- Saves to `DailyCheckin.cycle_day`

---

## Error handling

- If `last_period_date` is set but in the future → treat as day 1
- If cycle calculation gives `cycle_day > cycle_length_days` → clamp to `cycle_length_days`
- If AI call fails → `ai_note: null`, adaptation still shown with weight modifier only
- If user has no today's recommendations → show phase card without adaptations list

---

## What is NOT in scope

- Nutrition recommendations by phase
- Sleep recommendations by phase
- Cycle tracking history / period log UI
- Push notifications ("your luteal phase starts tomorrow")
- Cycle length learning/adjustment over time
