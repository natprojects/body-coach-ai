# Calisthenics Mini-Sessions & Training Stats — Design Spec

**Date:** 2026-04-27
**Module:** Calisthenics (extension)
**Depends on:** Calisthenics Foundation + Plan (already shipped)

**Goal:** Let user pick how many main + optional sessions per week, generate short on-demand mini-sessions of three flavors, see weekly progress and full training history, and have Coach reason over the last 30 days of training (not just the last session).

---

## 1. Scope

### In v1
1. Profile gains `optional_target_per_week` (0–7) — soft target for mini-sessions
2. Schedule editor in regenerate flow — pick `days_per_week` + `optional_target_per_week` before regenerating
3. Three on-demand mini-session types: **stretch / short / skill**, ~10–15 min each, AI-generated
4. Mini-sessions stored as standalone `Workout` rows (no program_week), reuse existing logging
5. "Цього тижня" card on Calisthenics home — `done/target` for main + mini
6. Training history page — last 30 sessions with date, name, kind, exercise count
7. Session detail view — what was done in a specific session (read-only)
8. Coach context expanded with 30-day calisthenics aggregates (replaces last-1-session)

### Out of v1 (deferred)
- Photos / progress pictures
- Charts / graphs (numeric stats only — no SVG/canvas yet)
- Push notifications for "you haven't trained this week"
- Mini-session level-up criterion (only main sessions feed level-up)
- Editing past logged sets

---

## 2. Architecture Principle

Reuse existing `Workout / WorkoutSession / LoggedExercise / LoggedSet` hierarchy. Mini-sessions live as `Workout` rows with `program_week_id=NULL` and `mini_kind` set. The session, exercise, and set logging endpoints work identically for main and mini — the only difference is how the workout was created and how stats group it.

---

## 3. Data Model Changes

### Migration `j0k1l2m3n4o5_add_mini_sessions_and_stats.py`

**`calisthenics_profiles`:**
- `optional_target_per_week` `Integer` NOT NULL, default `0`, server_default `'0'`

**`workout_sessions`:**
- `kind` `String(20)` NOT NULL, default `'main'`, server_default `'main'` — `'main'` | `'mini'`

**`workouts`:**
- `program_week_id` becomes `nullable=True` (was non-null) — mini-sessions don't belong to a program week
- `mini_kind` `String(20)` nullable — `'stretch'` | `'short'` | `'skill'` for mini-sessions, NULL for main workouts

### Backward compatibility

All existing `Workout` rows have `program_week_id` set; making the column nullable doesn't affect them. Existing `WorkoutSession.kind` default to `'main'` server-side.

---

## 4. AI Generation — Mini-Sessions

### File: `app/modules/calisthenics/coach.py`

New function:
```python
def generate_mini_session(user, profile, mini_type: str) -> dict:
    """Generate a 10-15 min mini-session of the given type. Returns parsed JSON dict
    with the same workout schema (name, exercises[], sets[]) as main programs."""
```

Three system prompts (one per type), all sharing structure but with type-specific guidance:

**stretch (10 min target):**
- 5-7 mobility / stretch exercises, 30-60s each
- Target zones: hips, shoulders, spine, posture
- Anchor to user's injuries/limitations from profile (e.g., shoulder injury → emphasize thoracic mobility)
- All exercises in `seconds` unit, no AMRAP

**short (15 min target):**
- 3-4 strength exercises from the user's seeded calisthenics catalog
- 2 sets each, last set AMRAP
- Uses progressions matching user's current main-program level (don't push harder)
- Avoids duplicating today's main workout chain (server passes `today_main_chains` as context)
- All exercises from closed list (same `_calisthenics_exercise_catalog()`)

**skill (10 min target):**
- 1-2 skill progressions
- Examples: L-sit hold, handstand wall hold, planche lean, dragon flag negative
- Focus on form/quality, low volume (3-4 sets × 5-15s holds OR 3 reps with long rest)
- AI picks a skill the user is close to but hasn't mastered (looks at last assessment + main program)

### Save flow

`save_mini_session_from_dict(user_id, mini_type, mini_dict) -> Workout`:
1. Resolves all exercise names against existing seeded calisthenics exercises (raise `ValueError` on miss)
2. Creates `Workout` row with `program_week_id=NULL`, `mini_kind=<type>`, `name=<mini_dict.name>`, `estimated_duration_min=<10/15>`
3. Creates `WorkoutExercise` + `PlannedSet` rows as for main programs
4. Returns `Workout` row (with id) — frontend then calls existing `/session/start` with this workout_id

---

## 5. API Endpoints

All under `/api/calisthenics/`, `@require_auth`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/mini-session/generate` | Body: `{type: 'stretch'\|'short'\|'skill'}`. Generates + saves mini Workout, returns serialized workout (id + exercises + sets) |
| `GET` | `/sessions/history?limit=30` | List recent sessions (main + mini) with summary fields |
| `GET` | `/sessions/<int:session_id>/detail` | Full deserialize of one session: workout structure + logged sets |
| `POST` | `/program/<int:program_id>/regenerate` (extended) | Now accepts optional `days_per_week` + `optional_target_per_week` in body. If passed, updates profile before regenerating |
| `GET` | `/stats/weekly` | This week's progress: `{main_done, main_target, mini_done, mini_target}` |

### Response shapes

`POST /mini-session/generate`:
```json
{"success": true, "data": {
  "workout_id": 123,
  "name": "10хв стретч",
  "mini_kind": "stretch",
  "estimated_duration_min": 10,
  "exercises": [
    {"id": ..., "exercise_id": ..., "exercise_name": "...", "unit": "seconds",
     "sets": [{"set_number": 1, "target_seconds": 30, "is_amrap": false}, ...]}
  ]
}}
```

`GET /sessions/history`:
```json
{"success": true, "data": [
  {"id": 87, "date": "2026-04-26", "kind": "main",
   "workout_name": "Push A", "exercise_count": 5, "duration_min": 35},
  {"id": 88, "date": "2026-04-25", "kind": "mini",
   "workout_name": "10хв стретч", "exercise_count": 6, "duration_min": 10},
  ...
]}
```

`GET /sessions/<id>/detail`:
```json
{"success": true, "data": {
  "id": 87, "date": "2026-04-26", "kind": "main", "status": "completed",
  "workout_name": "Push A",
  "exercises": [
    {"exercise_name": "full pushup", "unit": "reps",
     "logged_sets": [
       {"set_number": 1, "actual_reps": 10},
       {"set_number": 2, "actual_reps": 10},
       {"set_number": 3, "actual_reps": 13}
     ]}
  ]
}}
```

`GET /stats/weekly`:
```json
{"success": true, "data": {
  "week_start": "2026-04-21",
  "main_done": 4, "main_target": 5,
  "mini_done": 1, "mini_target": 2
}}
```

---

## 6. Coach Context — Calisthenics 30-Day Summary

**Gym sections (active program, last gym session) stay unchanged** — only the calisthenics part of `build_coach_context` is modified.

Replace the current "Last Calisthenics Workout" block with a richer 30-day summary:

```
## Calisthenics Activity (last 30 days)
- 12 sessions: 8 main, 4 mini (3 stretch, 1 skill)
- Main by chain: push 6, pull 3, squat 2, core_static 1
- AMRAP trends:
  - full pushup: 12 → 14 → 17 (push, last 3 sessions)
  - forearm plank: 30s → 45s → 60s (core_static)
- Recent levels held: full pushup, australian pullup, full bodyweight squat
```

Computed from:
- Session count grouped by `kind` and (for mini) by `mini_kind`
- Workout count grouped by exercise's `progression_chain`
- For each WorkoutExercise in active program, last 3 AMRAP values
- All queried with `module='calisthenics'` filter

**Empty-state handling:** if the user has 0 calisthenics sessions in the last 30 days, output a single line: `## Calisthenics Activity\nNo recent calisthenics sessions.` — no aggregate or trends sections.

---

## 7. Frontend Changes

### Calisthenics home — new sections

**"Цього тижня" card** (always visible when active program exists):
```
ЦЬОГО ТИЖНЯ
4/5 основних    1/2 міні        ← stat blocks (gym hero-stats style)
```

If `optional_target_per_week == 0`, hide mini stat. Clicking the card opens history page.

**"+ Міні-сесія" button** (always visible regardless of main day / rest day):
```
[ + МІНІ-СЕСІЯ ]
```

Tap → modal overlay (re-uses existing `position:fixed` overlay pattern from level-up dialog) with three large buttons (icons + labels):
- 🧘 Стретч 10хв
- 💪 Скорочена силова 15хв
- 🎯 Скіл-фокус 10хв

Tap a type → loading screen "Створюю сесію…" → POST mini-session/generate → workout view (existing `renderCalisthenicsWorkout`) → user does it / logs it / completes via existing flow.

**"Історія" button** (small link near the "Остання оцінка" card):
- Opens history page (full-screen overlay or new view)

### History page

- Header: "Історія тренувань"
- List of sessions (last 30) using `prog-ex-row`-like styling
- Each row: date · kind badge · workout name · exercise count
- Tap row → session detail view (also overlay)

### Session detail view

- Header: workout name + date + kind
- Read-only list of exercises with logged sets per exercise
- Format: `Full pushup — 10 / 10 / 13` (rep counts) or `Plank — 30s / 45s / 60s`

### Schedule editor in regenerate flow

When user taps "Перегенерувати програму" (existing button on rest day banner OR after assessment):
- Show small inline form BEFORE the loading screen:
  ```
  Скільки днів на тиждень?     [3] [4] [5] [6]   ← chips, default = current
  Опціональних міні-сесій?      [0] [1] [2] [3]
  [ СТВОРИТИ НОВУ ПРОГРАМУ ]
  ```
- Tap CTA → POST `/program/<id>/regenerate` with body `{days_per_week, optional_target_per_week}`
- Loading screen as before, then home reloads with new program

### Update calisthenics profile wizard

Add `optional_target_per_week` to the existing days/duration step:
- Existing chip row: "Скільки разів на тиждень?" 2/3/4/5/6
- New chip row below: "Міні-сесій на тиждень?" 0/1/2/3 (default 0)

---

## 8. Error Handling

| Scenario | Behavior |
|---|---|
| Generate mini-session for user without profile | 400 `PROFILE_REQUIRED` |
| AI returns malformed JSON | retry once with addendum; second failure → 500 `AI_GENERATION_FAILED` |
| AI returns unknown exercise name | 500 `INVALID_EXERCISE_NAME` (closed-list constraint) |
| `type` not in `{stretch, short, skill}` | 400 `INVALID_TYPE` |
| Regenerate with `days_per_week` out of range | 400 `INVALID_FIELD` |
| Session detail for other user's session | 404 |
| Stats endpoint with no profile | 200 with zero counters |

---

## 9. Testing Strategy

### Backend
- Migration tests: existing data unchanged after migration
- Models: column defaults, nullability of `program_week_id`
- Mini-session generation tests: mock Anthropic, verify Workout row created with correct `mini_kind`, exercise resolution, `program_week_id` is null
- Endpoint tests: all 5 endpoints, auth required, module isolation, ownership checks
- Stats query tests: weekly counters, 30-day aggregates with mixed main/mini sessions
- Regenerate-with-params tests: profile updates AND program changes match new days_per_week

### Frontend
- Manual browser test plan in PR description (no automated frontend tests yet)

### Non-regression
- Full pytest suite continues passing
- Existing main-program flow (today, start, log, complete, level-up) unchanged
- Coach chat unchanged (same endpoint, just richer context)

---

## 10. File Map (estimated)

### Backend
- **Modify:** `app/modules/training/models.py` — add `kind` to `WorkoutSession`, `mini_kind` + nullable `program_week_id` to `Workout`
- **Modify:** `app/modules/calisthenics/models.py` — add `optional_target_per_week` to `CalisthenicsProfile`
- **Create:** `migrations/versions/<rev>_add_mini_sessions_and_stats.py`
- **Modify:** `app/modules/calisthenics/coach.py` — add `generate_mini_session` + `save_mini_session_from_dict`
- **Modify:** `app/modules/calisthenics/routes.py` — add 5 new endpoints, extend `/regenerate` body parsing
- **Modify:** `app/modules/calisthenics/routes.py` — extend `_serialize_program`/serializer to include kind/mini_kind
- **Modify:** `app/modules/calisthenics/routes.py` — POST `/profile` validates `optional_target_per_week` in [0, 7]
- **Modify:** `app/modules/coach/context.py` — replace last-session block with 30-day calisthenics summary

### Frontend
- **Modify:** `app/templates/index.html`:
  - Add "Цього тижня" card to calisthenics home
  - Add "+ Міні-сесія" button + bottom sheet picker
  - Add "Історія" button on home + history page modal + session detail modal
  - Add inline schedule editor before regenerate
  - Add new chip row in profile wizard for `optional_target_per_week`

### Tests
- **Create:** `tests/calisthenics/test_mini_sessions.py`
- **Create:** `tests/calisthenics/test_stats.py`
- **Modify:** `tests/calisthenics/test_program_endpoints.py` — extend regenerate test for new params

---

## 11. Open Questions Deferred to Implementation

1. Mini-session naming — let AI choose (e.g., "Recovery flow") vs deterministic ("10хв стретч"). Implementer can pick; deterministic is simpler.
2. Whether mini-session AMRAP results contribute to level-up criterion (decision: NO in v1 — only main sessions count, keeping level-up logic stable)
3. Exact bottom-sheet positioning for the mini-session picker on iOS Telegram (use existing overlay pattern)
