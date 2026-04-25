# Calisthenics Plan Module — Design Spec

**Date:** 2026-04-25
**Module:** Calisthenics (Plan subsystem)
**Depends on:** Calisthenics Foundation (already shipped)
**Goal:** Generate, run, and progressively evolve calisthenics training programs.

---

## 1. Scope

### In v1
1. "Створити програму" button on Calisthenics home (after assessment exists)
2. AI-generated 4-6 week mesocycle (1 mesocycle, 1 week template, repeated)
3. Daily workout view with bodyweight-aware targets (reps OR seconds)
4. Logging UX: 1-tap "done as planned" + manual override + AMRAP last set
5. Level-up suggestions after sessions (deterministic rule, no AI)
6. End-of-block re-assessment + program regeneration
7. Strict isolation between gym and calisthenics programs (`module` filter on every query)
8. Universal manual workout picker (any workout of current week, both modules)

### Out of v1 (deferred)
- Cycle adaptation in calisthenics
- Coach chat for calisthenics
- Photos / analytics
- Custom user-added exercises (only prebuilt progression chains)
- Pause/resume / archive program manually

---

## 2. Architecture Principle

Reuse the existing gym training data hierarchy (`Program → Mesocycle → ProgramWeek → Workout → WorkoutExercise → PlannedSet`, plus `WorkoutSession → LoggedExercise → LoggedSet`). Add a `module` discriminator column where needed and filter every query by `module = user.active_module`.

This keeps logging/sessions/recommendations infrastructure shared while making the two modules' data domains disjoint at the query level.

---

## 3. Data Model Changes

### New columns

**`programs`:**
- `module` `String(20)` NOT NULL, default `'gym'`, server_default `'gym'`
- `is_active` `Boolean` NOT NULL, default `True`, server_default `'1'` — replaces "latest by created_at" assumption; old programs flipped to `false` on regenerate. Applies to both modules (gym + calisthenics).

**`workout_sessions`:**
- `module` `String(20)` NOT NULL, default `'gym'`, server_default `'gym'` — denormalized from `program.module` for query speed; populated on session start

**`exercises`:**
- `module` `String(20)` NOT NULL, default `'gym'`, server_default `'gym'`
- `progression_chain` `String(30)` NULLABLE — one of: `'push'`, `'pull'`, `'squat'`, `'core_dynamic'`, `'core_static'`, `'lunge'`. NULL for gym exercises
- `progression_level` `Integer` NULLABLE — 0..N within chain. NULL for gym exercises
- `unit` `String(10)` NULLABLE — `'reps'` or `'seconds'`. NULL for gym exercises (which always use reps + weight)

**`planned_sets`:**
- `is_amrap` `Boolean` NOT NULL, default `False`, server_default `'0'` — true for last set typically
- `target_seconds` `Integer` NULLABLE — for static holds. If NULL, use `target_reps` field

### Migration

Single migration adds all five columns + creates a unique constraint `(progression_chain, progression_level)` partial index where `module='calisthenics'` (so each level in a chain has exactly one canonical exercise).

### Seed data — progression chains

40+ calisthenics exercises seeded into `exercises` table during the same migration. Levels are 0-indexed within each chain.

```
push (10 levels):
  0  wall pushup
  1  incline pushup
  2  knee pushup
  3  full pushup
  4  diamond pushup
  5  decline pushup
  6  archer pushup
  7  pseudo planche pushup
  8  one-arm pushup negative
  9  one-arm pushup

pull (8 levels):
  0  dead hang (seconds)
  1  scapular pull
  2  australian pullup
  3  negative pullup
  4  band-assisted pullup
  5  full pullup
  6  archer pullup
  7  one-arm pullup negative

squat (6 levels):
  0  assisted squat (holding support)
  1  full bodyweight squat
  2  reverse lunge
  3  bulgarian split squat
  4  pistol squat negative
  5  pistol squat

core_dynamic (5 levels):
  0  dead bug
  1  hanging knee raise
  2  hanging leg raise
  3  toes-to-bar
  4  dragon flag negative

core_static (5 levels, all in seconds):
  0  forearm plank
  1  hollow body hold
  2  l-sit tuck (parallettes / floor)
  3  l-sit
  4  v-sit progression

lunge (4 levels):
  0  reverse lunge
  1  walking lunge
  2  jumping lunge
  3  shrimp squat regression
```

Document is also written to `docs/calisthenics_progressions.md` for future tweaks.

---

## 4. AI Generation

### File: `app/modules/calisthenics/coach.py`

```python
def generate_calisthenics_program(user: User, profile: CalisthenicsProfile,
                                   last_assessment: CalisthenicsAssessment) -> dict:
```

Returns the same JSON structure as gym (`name`, `periodization_type`, `total_weeks`, `mesocycles[].weeks[].workouts[].exercises[].sets[]`). The output is fed into a thin variant of `save_program_from_dict` that preserves the `module='calisthenics'` discriminator and resolves exercise names to existing seeded `Exercise` rows (no new `Exercise` rows created).

### System prompt highlights

1. **Hard constraints (mandatory):** 1 mesocycle, 1 week template, exactly N workouts (N from profile.days_per_week), 4-6 exercises per workout, exactly 3 sets per exercise (last set `is_amrap: true`)
2. **Closed exercise list:** entire seeded progression catalog passed inline as JSON `[{name, chain, level, unit}, ...]`. AI must pick by `name`. Hallucinated exercise names are caught at save time.
3. **Equipment guard:** if `profile.equipment` lacks any of `pullup_bar / dip_bars / rings`, exclude `pull` chain entirely (and pseudo planche / one-arm progressions that need a sturdy bar)
4. **Injury contraindications:** standard rehab-aware logic (knees → no jumping lunges, wrists → use parallettes for pushups or skip diamond, shoulders → no decline / archer push, back → no dragon flag)
5. **Level selection rule:** for each chain we pick into the workout, AI picks `progression_level` such that `target_reps` (or `target_seconds`) is achievable based on assessment values. Heuristics in prompt: e.g., `if pushups<5 → level 1-2; 5-12 → level 3 full; 13-25 → level 4 diamond; 25+ → level 5+`
6. **Progressive overload across the week:** if 2 workouts hit the same chain (e.g., Push A and Push B), use slightly different progression levels or different rep schemes
7. **Beginner constraints:** if `level='beginner'` → only chains 0-3, total_weeks 4. Intermediate → chains up to 5, total_weeks 5. Advanced → no cap, total_weeks 6.

### User prompt content

Profile (goals, equipment, days, duration, injuries, motivation), last assessment results (all 9 metrics with units), prior session history if regenerating (counts of completed workouts, ratio of AMRAP-target vs target — used for new block calibration).

### Save flow

`save_calisthenics_program_from_dict(user_id, dict)`:
1. Validate every `exercise_name` resolves to an `Exercise` with `module='calisthenics'`. Unresolved → `INVALID_EXERCISE_NAME` 400.
2. Mark prior active calisthenics program as archived (set a flag — see §6 below).
3. Persist Program/Mesocycle/Week/Workout/WorkoutExercise/PlannedSet, all with `module='calisthenics'` where applicable.
4. Return saved program serialized.

---

## 5. API Endpoints

All under `/api/calisthenics/` and decorated with `@require_auth`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/program/generate` | Generate + save new program. Requires profile + assessment. Returns program dict |
| `GET` | `/program/active` | Active program (if any) or `null` |
| `GET` | `/today` | Active workout for today (scheduled / ad_hoc) or `{rest_day: true}` |
| `GET` | `/week-overview` | All workouts of current week with status (`done`, `today`, `upcoming`) |
| `POST` | `/session/start` | Start session for a workout_id (enforces module match) |
| `POST` | `/session/<id>/log-set` | Log a single set (reps OR seconds, plus is_amrap flag) |
| `POST` | `/session/<id>/complete` | Finish session. Returns `{level_up_suggestions: [...]}` |
| `POST` | `/program/<id>/level-up` | Apply a level-up swap (replace exercise_id in WorkoutExercise + future sets) |
| `POST` | `/program/<id>/regenerate` | Mark current archived, generate new (after re-assessment) |

### Universal week-overview (gym + calisthenics)

`GET /api/training/week-overview` returns the same shape, gym version. Frontend calls the right one based on `S.activeModule`.

```json
{
  "week_start": "2026-04-20",
  "workouts": [
    {"id": 12, "name": "Push A", "day_of_week": 0, "status": "done", "session_id": 87},
    {"id": 13, "name": "Pull A", "day_of_week": 2, "status": "today"},
    {"id": 14, "name": "Legs A", "day_of_week": 4, "status": "upcoming"}
  ]
}
```

---

## 6. Level-Up Logic

### Trigger

On `POST /session/<id>/complete`, after recording `LoggedSet`s, run `_check_level_ups(user_id, program)`.

### Rule (deterministic, no AI)

For each `WorkoutExercise` in current program (filter by `module='calisthenics'` + active program):

1. Find the last 3 completed sessions that included this workout
2. For each session, find the AMRAP-flagged set's logged value
3. **Threshold for promote:**
   - `target_reps` is stored as a range string like `"8-12"`. Parse upper bound (`12` here).
   - If `unit='reps'`: AMRAP value ≥ `upper_bound + 3` in all 3 sessions (e.g., for `"8-12"` need ≥ 15 reps three times)
   - If `unit='seconds'`: AMRAP value ≥ `target_seconds + 10` in all 3 sessions
4. If passed: find next exercise in same `progression_chain` with `progression_level + 1`. If exists → add to suggestions list

Returns `[{exercise_id_current, exercise_name_current, exercise_id_next, exercise_name_next, chain, sessions_count: 3}, ...]`

### Apply (user-confirmed)

`POST /program/<id>/level-up` body: `{from_exercise_id, to_exercise_id}`.

Backend swaps `WorkoutExercise.exercise_id` (all rows referencing `from_exercise_id` in this program). New `PlannedSet` targets are scaled down: `target_reps = "6-10"` (start of next level's recommended range), `target_weight_kg` stays NULL. Future sessions use the new exercise; past sessions remain attached to old exercise (history preserved).

### Why not auto-apply?

User control + psychological buy-in. We surface the suggestion as a celebratory dialog after session complete; user explicitly opts in. Skipping doesn't lose the suggestion — it triggers again next session if criteria still met.

---

## 7. Re-Assessment Trigger

### When

When user has completed all weeks × workouts of the active mesocycle (i.e., session count for this program ≥ `total_weeks × workouts_per_week`), or when `total_weeks` calendar weeks have passed since program creation, whichever comes first.

### UX

Banner on Calisthenics home: "Ти завершила блок! Пройди тест щоб виміряти прогрес → новий блок". Tap → assessment screen (existing). After save → "Створити новий блок" CTA → calls `POST /program/<id>/regenerate`. Old program is archived (`is_active=false` field) but remains in DB for history.

No hard block — user can keep using old program indefinitely if she wants.

### Active query pattern

After the `is_active` column is added (see §3), the active program query becomes:

```python
Program.query.filter_by(
    user_id=u.id,
    module=u.active_module,
    is_active=True,
).first()
```

On regenerate: old program's `is_active` set to `False`, new program created with `is_active=True`. History preserved.

---

## 8. Frontend UI

### Calisthenics home — three states

**State A: profile + assessment, no program**
- Card: latest assessment (already implemented)
- Big primary button: "Створити програму"
- Tap → loading screen ("Створюю твою програму…" 5-15s) → state B

**State B: active program, no session in progress**
- "Сьогодні" hero card: workout name, est. duration, exercise preview (3 names), "Почати тренування" CTA
- If rest day: "Сьогодні відпочинок 💤" + "Якщо є настрій — обери тренування нижче"
- "→ Інше тренування" link (collapsed unless rest day): expands to week-overview list, each tappable to start
- Collapsed "Програма" section: mesocycle name, week X/Y, list of workouts with status badges
- Bottom: shrunk "Остання оцінка" card with "Пройти тест знову" link
- If end-of-block reached: orange banner "Ти завершила блок! Пройди тест → новий блок"

**State C: session in progress (workout view)**
- Same as gym workout view but adapted for bodyweight:
  - No weight input
  - Targets show as `Full pushup — 3 × 10-12` or `Plank — 3 × 30s`
  - Sets render as 3 rows with "✓ Зробила" + "✏ Інакше" buttons (per set), final set always has number input
  - Rest timer between sets (default 60-90s, configurable)
- Complete button → POST /complete → if `level_up_suggestions` non-empty, show dialog before redirect

### Level-up dialog

```
🎉 Готова до наступного рівня!
Ти 3 рази поспіль зробила Full pushup × 12+.
Час спробувати Diamond pushup.

[Так, перейти]   [Поки що ні]
```

Apply tap → POST /program/<id>/level-up → reload program → home view.

### Tab Program (when calisthenics active)

Replaces the "незабаром" placeholder shipped in Foundation. Same component as gym Program tab (mesocycles → weeks → workouts) but reads `module='calisthenics'` data.

### Universal "Other Workout" picker

A new shared component used in both modules' Train tabs:

- Renders week-overview list with status icons (`✓`, `⊙`, `•`)
- Clicking a `done` or `upcoming` workout → confirmation dialog "Ти ще не маєш робити це сьогодні / Ти вже зробила це сьогодні. Все одно?" → POST /session/start with explicit workout_id
- Clicking `today` workout = same as the regular start button

Hidden by default behind "→ Інше тренування" link, expanded on rest day.

---

## 9. Error Handling

| Scenario | Behavior |
|---|---|
| Generate program without profile | 400 `PROFILE_REQUIRED` |
| Generate program without any assessment | 400 `ASSESSMENT_REQUIRED` |
| AI returns malformed JSON | retry once with system prompt addendum "previous output failed to parse"; second failure → 500 `AI_GENERATION_FAILED` |
| AI returns exercise name not in seeded list | 500 `INVALID_EXERCISE_NAME` (with offending name in message) — should be rare given closed-list prompt |
| Start session for workout in wrong module | 400 `MODULE_MISMATCH` |
| Level-up requested but criteria not met (server-recheck) | 400 `LEVEL_UP_NOT_READY` |
| Concurrent active sessions in two modules | each module tracks its own active session; user can have two simultaneously (but UX nudges against it via "Resume" banner only showing the currently-active module) |

---

## 10. Testing Strategy

### Backend

- Models tests: column defaults, JSON serialization, level-up criterion calculation pure function
- Generation tests: mock Anthropic, verify save flow, exercise resolution, archived flag toggling
- Endpoint tests: all 9 endpoints, auth required, module isolation (cross-module access returns 404 / 400)
- Level-up tests: 3-session window, threshold logic, no-next-level edge case, no-history edge case
- Regenerate tests: archives old, creates new, history preserved
- Week-overview tests: status correctness, both modules
- Migration test: existing gym programs continue to work after migration applied (default `module='gym'`)

### Frontend

- Manual browser test plan in PR description (no automated frontend tests yet)

### Non-regression

Full pytest suite must continue to pass after this change. Gym ad-hoc, cycle adaptation, recommendations all still work.

---

## 11. Migration / Rollout Strategy

1. Migration adds columns with defaults — zero downtime
2. Existing gym data: all programs/sessions get `module='gym'`, all gym exercises stay as-is (no chain/level fields)
3. Seed migration adds calisthenics exercises (~40 rows)
4. Backend deploys first, frontend after — backend is backwards-compatible (no breaking changes to gym endpoints; the new endpoints are additive)
5. After deploy, existing users with calisthenics profiles see the new "Створити програму" button on home

---

## 12. File Map (estimated)

### Backend
- **Modify:** `app/core/models.py` — add `is_active` to `Program`, `module` to `Program`/`WorkoutSession`/`Exercise`/`planned_sets`, plus chain/level/unit fields
- **Modify:** `app/modules/training/models.py` — same additions split correctly
- **Create:** `migrations/versions/<rev>_add_module_isolation_and_calisthenics_seeds.py`
- **Modify:** `app/modules/calisthenics/__init__.py` (no change beyond what Foundation has)
- **Modify:** `app/modules/calisthenics/routes.py` — add 9 new endpoints
- **Create:** `app/modules/calisthenics/coach.py` — generation function
- **Create:** `app/modules/calisthenics/level_up.py` — pure function for criterion check
- **Modify:** `app/modules/training/routes.py` — add `/api/training/week-overview` (universal)
- **Modify:** every gym query that fetches program/workouts/sessions — add `module=u.active_module` filter (or `Program.is_active=True`)

### Frontend
- **Modify:** `app/templates/index.html` — Calisthenics home states A/B/C, workout view component, level-up dialog, "Other Workout" picker, Program tab when calisthenics, banner for end-of-block

### Tests
- **Create:** `tests/calisthenics/test_program_generation.py`
- **Create:** `tests/calisthenics/test_program_endpoints.py`
- **Create:** `tests/calisthenics/test_level_up.py`
- **Create:** `tests/calisthenics/test_week_overview.py`
- **Modify:** `tests/training/` — add module-isolation regression tests

### Docs
- **Create:** `docs/calisthenics_progressions.md` — list of all chains and levels with form notes

---

## 13. Open Questions Deferred to Implementation

1. Exact rest timer defaults per chain (60s for core, 90s for push/pull, 120s for legs?) — implementer can pick reasonable defaults
2. Translation strings for level-up dialog (Ukrainian — already established pattern)
3. Whether to show progress chart of past assessments on home — nice-to-have, can defer
