# Body Coach AI — Foundation + Training Module Design

**Date:** 2026-03-30
**Scope:** Flask foundation + Training module (MVP). Nutrition, Sleep, Psychology modules follow the same patterns established here.

---

## Overview

Telegram Mini App з AI-тренером. Стек: Python Flask + SQLite (SQLAlchemy) + Anthropic API. Авторизація через Telegram `initData`. Модульна архітектура: нові модулі підключаються через Blueprint без змін у core.

**Core principle:** Universal foundation з першого дня — conversational memory, shared user profile, daily checkins і pain journal доступні всім майбутнім модулям через той самий механізм.

---

## 1. Project Structure

```
body-coach-ai/
├── app/
│   ├── __init__.py              # Flask app factory, реєстрація blueprints, error handlers
│   ├── config.py                # Env-based config (dev/prod)
│   ├── extensions.py            # db, migrate — ініціалізуються тут, імпортуються звідси
│   ├── core/
│   │   ├── auth.py              # Telegram initData validation middleware → JWT
│   │   ├── ai.py                # Anthropic client + universal chat() helper
│   │   ├── conversation.py      # load/save conversation window (per user per module)
│   │   └── models.py            # User, body_measurements, injury_details,
│   │                            # daily_checkins, pain_journal, ai_conversations
│   └── modules/
│       └── training/
│           ├── __init__.py      # Blueprint registration
│           ├── models.py        # Program, Mesocycle, ProgramWeek, Workout,
│           │                   # Exercise, PlannedSet, WorkoutSession,
│           │                   # LoggedExercise, LoggedSet
│           ├── routes.py        # REST endpoints
│           ├── onboarding.py    # Onboarding flow handlers
│           ├── coach.py         # Training AI: builds system prompt + extra_context
│           └── progress.py      # Post-workout feedback, weekly report generation
├── tests/
│   ├── core/
│   │   ├── test_auth.py
│   │   └── test_conversation.py
│   └── training/
│       ├── test_onboarding.py
│       ├── test_program.py
│       ├── test_session.py
│       └── test_coach.py
├── run.py
├── requirements.txt
└── CLAUDE.md
```

**Key decisions:**
- `extensions.py` розриває circular imports: `db = SQLAlchemy()` живе тут, `app/__init__.py` викликає `db.init_app(app)`, моделі імпортують `db` з `extensions`.
- `core/conversation.py` — єдиний механізм для всіх модулів. Training не знає про деталі збереження.
- Новий модуль = нова папка в `modules/` + реєстрація Blueprint. Core не чіпається.

---

## 2. Database Schema

### Core (shared across all modules — `core/models.py`)

```sql
users
  id, telegram_id, name, gender, age
  weight_kg, height_cm, body_fat_pct
  goal_primary          -- hypertrophy / strength / health / weight_loss
  goal_secondary        -- JSON array
  level                 -- beginner / intermediate / advanced
  training_days_per_week, session_duration_min
  equipment             -- JSON array: full_gym / home_gym / dumbbells / barbell / none
  injuries_current      -- JSON
  injuries_history      -- JSON
  postural_issues       -- JSON
  mobility_issues       -- JSON
  muscle_imbalances     -- JSON
  menstrual_tracking    -- bool
  cycle_length_days, last_period_date
  training_likes, training_dislikes
  previous_methods      -- JSON array
  had_coach_before, motivation_type  -- result / process / health
  onboarding_completed_at, created_at

body_measurements
  id, user_id, date
  weight_kg, body_fat_pct
  waist_cm, hips_cm, chest_cm
  left_arm_cm, right_arm_cm, left_leg_cm, right_leg_cm

injury_details
  id, user_id, body_part, side       -- left / right / bilateral
  description, aggravating_factors
  diagnosis, saw_doctor              -- bool
  is_current, created_at

daily_checkins
  id, user_id, date
  energy_level (1-10), sleep_quality (1-10)
  stress_level (1-10), motivation (1-10)
  soreness_level (1-10), body_weight_kg
  cycle_day             -- nullable
  notes

pain_journal
  id, user_id, date
  body_part
  pain_type             -- sharp / dull / aching / burning
  intensity (1-10)
  when_occurs           -- during / after / morning / always
  related_exercise_id   -- nullable FK → exercises
  notes

ai_conversations
  id, user_id
  module                -- training / nutrition / sleep / psychology
  role                  -- system / user / assistant
  content, created_at
```

### Training module (`modules/training/models.py`)

```sql
programs
  id, user_id, name
  periodization_type    -- linear / wave / block
  total_weeks
  status                -- active / completed / paused
  created_at

mesocycles
  id, program_id, name  -- Accumulation / Intensification / Deload
  order_index, weeks_count

program_weeks
  id, mesocycle_id, week_number, notes

workouts  (planned)
  id, program_week_id, day_of_week, name, order_index

exercises  (master list)
  id, name, muscle_group, equipment_needed
  contraindications           -- JSON
  contraindication_severity   -- none / caution / avoid
  mobility_requirements       -- JSON
  posture_considerations      -- JSON
  injury_modifications        -- JSON
  muscle_position             -- stretched / shortened / mid
  is_corrective               -- bool
  is_prehab                   -- bool

workout_exercises  (planned)
  id, workout_id, exercise_id, order_index, notes

planned_sets
  id, workout_exercise_id, set_number
  target_reps, target_weight_kg, target_rpe, rest_seconds

workout_sessions  (actual)
  id, user_id, workout_id    -- nullable: підтримує вільне тренування
  date, status               -- in_progress / completed
  notes, ai_feedback

logged_exercises
  id, session_id, exercise_id, order_index

logged_sets
  id, logged_exercise_id, set_number
  actual_reps, actual_weight_kg, actual_rpe
  notes, logged_at
```

**Key decisions:**
- `planned_sets` vs `logged_sets` — AI бачить відхилення від плану для коригування наступного тижня.
- `exercises.contraindications` + `contraindication_severity` — при генерації програми AI виключає вправи несумісні з профілем травм.
- `daily_checkins` і `pain_journal` живуть у core, не в Training — Nutrition і Sleep теж їх читатимуть.

---

## 3. AI Architecture

### Context construction (per request)

```python
# core/ai.py
def chat(user_id, module, user_message, extra_context=""):
    system = build_base_system(user_id) + extra_context
    # build_base_system: user profile + today's checkin + recent pain_journal entries
    history = load_conversation_window(user_id, module, limit=15)
    response = anthropic_client.messages.create(
        model="claude-opus-4-6",
        system=system,
        messages=history + [{"role": "user", "content": user_message}],
        stream=True
    )
    save_message(user_id, module, "user", user_message)
    save_message(user_id, module, "assistant", response)
    return response
```

Each module provides its own `extra_context`:
- **Training `coach.py`:** current program week, today's planned workout, session progress if in_progress
- **Future Nutrition:** current meal plan, today's intake
- **Future Sleep:** sleep protocol, recent sleep scores

### Three AI interaction types in Training

| Момент | Тригер | AI контекст |
|--------|--------|-------------|
| Онбординг | Step-by-step flow | Накопичені відповіді → будує профіль |
| Під час тренування | Кожне повідомлення / logged set | Поточна сесія + план + checkin дня |
| Post-workout feedback | `session.status = completed` | Вся сесія vs план → short summary |
| Тижневий звіт | Manual trigger (MVP) | Всі сесії тижня + pain journal → report + корекція плану |

**Streaming:** Anthropic streaming API → Flask `text/event-stream` → Telegram Mini App SSE.

---

## 4. API Endpoints

All endpoints require `Authorization: Bearer <jwt>` except `/api/auth/validate`.
All responses: `{ success: bool, data: any, error: { code, message } }`.

```
POST /api/auth/validate

GET  /api/onboarding/status
POST /api/onboarding/step          # { step, data }
POST /api/onboarding/complete

POST /api/training/program/generate
GET  /api/training/program/current
GET  /api/training/program/week/<n>

GET  /api/training/today
POST /api/training/session/start
POST /api/training/session/log-set   # { exercise_id, set_number, reps, weight, rpe }
POST /api/training/session/complete
GET  /api/training/session/<id>

GET  /api/training/progress/weekly
GET  /api/training/progress/history

POST /api/training/chat              # SSE stream

POST /api/checkin
GET  /api/checkin/today

POST /api/pain
GET  /api/pain/recent

POST /api/measurements
GET  /api/measurements/history
```

---

## 5. Error Handling

Single `@app.errorhandler` in `app/__init__.py`. Modules raise typed exceptions:
- `OnboardingIncomplete` → 400
- `NoProgramFound` → 404
- `AIRateLimited` → 429 with retry-after

AI errors never crash an active workout session — logged sets are always saved before any AI call. Fallback response returned if AI fails.

---

## 6. Testing Strategy

Anthropic API мокується через `unittest.mock` у всіх тестах — перевіряємо що правильний контекст будується, а не що AI відповідає розумно.

```
tests/core/test_auth.py           — Telegram initData validation (valid / tampered / expired)
tests/core/test_conversation.py  — window load/save, module isolation
tests/training/test_onboarding.py — flow completeness, required fields validation
tests/training/test_program.py   — mesocycle structure, week ordering, periodization types
tests/training/test_session.py   — log sets, session completion, planned vs actual diff
tests/training/test_coach.py     — AI context building correctness
```

---

## Adding a New Module (Checklist)

1. Create `app/modules/<name>/` with `__init__.py`, `models.py`, `routes.py`, `coach.py`
2. Register Blueprint in `app/__init__.py`
3. Module's `coach.py` calls `core/ai.chat()` with its own `extra_context`
4. Read `daily_checkins`, `pain_journal`, `body_measurements` from core models as needed
5. No changes to core required
