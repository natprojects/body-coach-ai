# Profile, Program Tab & Exercise Insights Design

## Goal

Add three features to the Body Coach AI app:
1. **Personal Profile** — view and edit all user data, accessible via top-right icon
2. **Program Tab** — full training program viewer with collapsible structure in bottom nav
3. **Exercise Insights** — AI-generated per-exercise explanations (why chosen, expected outcome, modifications), manually triggered by user

## Architecture

Two new API modules added to existing Flask blueprint pattern. One DB migration. Frontend gains one new overlay and one new tab. AI insights use a single batch Claude call.

**Tech Stack:** Flask, SQLAlchemy, SQLite, Claude Sonnet 4.6, Telegram Mini App SPA

---

## 1. Database

### Migration: add columns to `workout_exercises`

```sql
ALTER TABLE workout_exercises ADD COLUMN selection_reason TEXT;
ALTER TABLE workout_exercises ADD COLUMN expected_outcome TEXT;
ALTER TABLE workout_exercises ADD COLUMN modifications_applied TEXT;
```

All nullable. `modifications_applied = null` means no modification was needed — not shown in UI.

---

## 2. API Endpoints

### Profile

**`GET /api/users/me`**
Returns full User record — all 35 fields. Requires JWT auth.

Response:
```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "Natalie",
    "gender": "female",
    "age": 25,
    "weight_kg": 60.0,
    "height_cm": 165.0,
    "body_fat_pct": 20.0,
    "goal_primary": "hypertrophy",
    "goal_secondary": ["strength"],
    "level": "advanced",
    "training_days_per_week": 4,
    "session_duration_min": 60,
    "equipment": ["full_gym"],
    "injuries_current": [],
    "injuries_history": [],
    "postural_issues": [],
    "mobility_issues": [],
    "muscle_imbalances": [],
    "menstrual_tracking": false,
    "cycle_length_days": null,
    "last_period_date": null,
    "training_likes": "...",
    "training_dislikes": "...",
    "previous_methods": [],
    "had_coach_before": false,
    "motivation_type": "progress"
  }
}
```

**`PATCH /api/users/me`**
Updates any subset of User fields. Requires JWT auth. Accepts partial body — only provided fields are updated.

Allowed fields: all non-auth User fields (excludes `id`, `telegram_id`, `username`, `password_hash`, `onboarding_completed_at`, `created_at`).

Response: same shape as GET /api/users/me.

---

### Program

**`GET /api/training/program/full`**
Returns the active program with all mesocycles, weeks, workouts, exercises, sets, and insights.

Response:
```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "Natalie – Hypertrophy Block",
    "periodization_type": "linear",
    "total_weeks": 8,
    "current_week": 2,
    "insights_generated": true,
    "mesocycles": [
      {
        "id": 1,
        "name": "Accumulation",
        "order_index": 0,
        "weeks_count": 8,
        "weeks": [
          {
            "week_number": 1,
            "workouts": [
              {
                "id": 1,
                "name": "Upper A",
                "day_of_week": 0,
                "exercises": [
                  {
                    "workout_exercise_id": 1,
                    "exercise_name": "Bench Press",
                    "order_index": 0,
                    "sets": [
                      {"set_number": 1, "target_reps": "8-10", "target_weight_kg": 60.0, "target_rpe": 7.0, "rest_seconds": 120}
                    ],
                    "selection_reason": "...",
                    "expected_outcome": "...",
                    "modifications_applied": null
                  }
                ]
              }
            ]
          }
        ]
      }
    ]
  }
}
```

`current_week` is computed as `(days_since_program_created // 7) + 1`.
`insights_generated` is `true` if all WorkoutExercises in this program have non-null `selection_reason`.

**`POST /api/training/program/insights`**
Triggers batch AI generation of insights for all exercises in the active program.

- If all exercises already have `selection_reason` set → returns immediately with `{success: true, count: N, already_done: true}`.
- Otherwise → calls `generate_exercise_insights(program, user)` → updates DB → returns `{success: true, count: N}`.

---

## 3. AI Insights Generation

Function: `generate_exercise_insights(program, user)` in `app/modules/training/coach.py`

**Collects** all `WorkoutExercise` records for the program (joined with `Exercise` and `Workout`).

**Single Claude call** (model: `claude-sonnet-4-6`, max_tokens: 4096):

System prompt:
```
You are an expert strength and conditioning coach.
Return a JSON array only — no prose, no markdown.
For each exercise, explain why it was chosen for this specific user,
what outcome to expect, and any modification made due to injuries/limitations.
If no modification was needed, set modifications_applied to null.
```

User prompt: user profile (goals, level, injuries, mobility, equipment) + exercise list:
```json
[
  {"workout_exercise_id": 1, "exercise_name": "Bench Press", "workout_name": "Upper A", "day_of_week": 0},
  ...
]
```

Expected response (JSON array, same length as input):
```json
[
  {
    "workout_exercise_id": 1,
    "selection_reason": "Compound horizontal push targeting pectoral hypertrophy...",
    "expected_outcome": "Increased chest mass and anterior delt strength...",
    "modifications_applied": null
  }
]
```

Post-processing: strip markdown fences → `json.loads()` → update each `WorkoutExercise` record in DB.

Token budget: 16 exercises × ~150 tokens/exercise = ~2400 tokens response. Well within 4096 limit.

---

## 4. Frontend

### Profile Overlay (`overlay-profile`)

Triggered by 👤 icon in screen-main header (top-right).

**View mode:**
- Sections: Physical (name, age, gender, weight, height, body fat), Goals (primary goal, secondary goals, level), Training (days/week, session duration, equipment, likes/dislikes), Health (injuries current/history, postural issues, mobility issues, muscle imbalances), Cycle (if menstrual_tracking enabled).
- "Edit Profile" button at bottom.

**Edit mode (same overlay):**
- All fields become editable inputs/selects/textareas.
- "Save" → `PATCH /api/users/me` → back to view mode.
- "Cancel" → back to view mode, no save.

Data source: `GET /api/users/me` on overlay open.

---

### Program Tab (5th bottom nav tab, label "PROGRAM")

Position in nav: Train / **PROGRAM** / Nutrition / Sleep / Coach

**Empty state** (no active program): button "Generate Program" → calls existing `POST /api/training/program/generate`.

**Program loaded state:**
- Program name and total weeks at top.
- "Generate Exercise Insights" button (visible if `insights_generated = false`).
  - On click: shows loading spinner, calls `POST /api/training/program/insights` (timeout: 60s), refreshes program data.
  - If `insights_generated = true`: shows "Insights Ready ✓" (non-clickable, muted style).
- Collapsible accordion: Mesocycle → Week → Workout → Exercises.
  - Current week is expanded by default, highlighted with accent color.
  - Other weeks collapsed.
- Each exercise row:
  ```
  Exercise Name        3×8-10 @60kg RPE7  rest 120s
  ▾ Why this exercise     [selection_reason]
  ▾ Expected outcome      [expected_outcome]
  ▾ Modification ⚠️       [modifications_applied]  (hidden if null)
  ```
  - Insight sections visible only if insights generated; otherwise hidden.

---

## 5. Error Handling

- `PATCH /api/users/me`: unknown fields are silently ignored; invalid types return 400.
- `POST /api/training/program/insights`: if AI returns malformed JSON, returns 500 with message "Failed to generate insights, please try again." DB is not partially updated.
- Profile overlay: failed PATCH shows inline error, stays in edit mode.
- Program insights: failed generation shows error toast, button remains active to retry.

---

## 6. File Changes Summary

| File | Change |
|------|--------|
| `app/core/models.py` | No change (User model already complete) |
| `app/modules/training/models.py` | Add 3 columns to `WorkoutExercise` |
| `migrations/versions/xxxx_add_exercise_insights.py` | New migration |
| `app/core/routes.py` | Add `GET /api/users/me`, `PATCH /api/users/me` |
| `app/modules/training/routes.py` | Add `GET /api/training/program/full`, `POST /api/training/program/insights` |
| `app/modules/training/coach.py` | Add `generate_exercise_insights()` function |
| `app/templates/index.html` | Add overlay-profile, program tab panel, 5th nav item |
