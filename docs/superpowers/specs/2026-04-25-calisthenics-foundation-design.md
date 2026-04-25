# Calisthenics Foundation — Design Spec (v1.0)

**Goal:** Build the Calisthenics module foundation: mode switcher (gym/calisthenics), profile wizard, and assessment session with history tracking.

---

## Overview

The Train tab gets a segment control at the top: "Зал / Калістеніка". Switching mode changes what's shown in Train and Program tabs. On first switch to Calisthenics, a 5-step wizard collects the profile, then immediately launches an assessment session to establish the baseline. Assessments can be repeated to track progress over time.

This is Phase 1 (Foundation). Plan generation, workout logging, progress photos, and analytics are separate specs built on top of this.

---

## Mode Switcher

A new field `active_module` (String, default `'gym'`) is added to the `User` model.

- Values: `'gym'` | `'calisthenics'`
- Persists between sessions
- **Train tab:** segment control "Зал / Калістеніка" at the top. Tapping switches mode and immediately re-renders the tab content.
- **Program tab:** automatically shows gym program or calisthenics program depending on `active_module`. If no program exists for the active module, shows an empty/setup state.
- Endpoint: `PATCH /api/user/active-module` — body: `{ "module": "gym" | "calisthenics" }`

---

## Architecture

```
app/modules/calisthenics/
├── __init__.py      # Blueprint, prefix /api
├── models.py        # CalisthenicsProfile, CalisthenicsAssessment
└── routes.py        # All endpoints

app/core/models.py   # Add active_module field to User
migrations/          # One new migration: active_module + two new tables
```

Registered in `app/__init__.py` following the same pattern as training and nutrition modules.

---

## Data Model

### User (modified)

```python
active_module = db.Column(db.String(20), default='gym', nullable=False)
# 'gym' | 'calisthenics'
```

### `CalisthenicsProfile` (one-to-one with User)

```python
class CalisthenicsProfile(db.Model):
    __tablename__ = 'calisthenics_profiles'
    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)

    # Step 1: Goals (multi-select)
    goals        = db.Column(db.JSON)
    # ['muscle', 'strength', 'skill', 'weight_loss', 'endurance']

    # Step 2: Equipment (multi-select)
    equipment    = db.Column(db.JSON)
    # ['none', 'floor', 'bands', 'dumbbells', 'pullup_bar', 'dip_bars', 'rings', 'parallettes']

    # Step 3: Schedule
    days_per_week       = db.Column(db.Integer)
    session_duration_min = db.Column(db.Integer)

    # Step 4: Limitations (pre-filled from User, user confirms/updates)
    injuries     = db.Column(db.JSON)   # mirrors User.injuries_current

    # Step 5: Motivation
    motivation   = db.Column(db.String(50))
    # 'look' | 'feel' | 'achieve' | 'health'

    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### `CalisthenicsAssessment` (many per User — history)

```python
class CalisthenicsAssessment(db.Model):
    __tablename__ = 'calisthenics_assessments'
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assessed_at     = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Results — None means exercise was skipped (no equipment)
    pullups         = db.Column(db.Integer, nullable=True)   # reps; requires pullup_bar/dip_bars/rings
    australian_pullups = db.Column(db.Integer, nullable=True)  # reps; always shown
    pushups         = db.Column(db.Integer, nullable=True)   # reps; always shown
    pike_pushups    = db.Column(db.Integer, nullable=True)   # reps; always shown
    squats          = db.Column(db.Integer, nullable=True)   # reps; always shown
    superman_hold   = db.Column(db.Integer, nullable=True)   # seconds; always shown
    plank           = db.Column(db.Integer, nullable=True)   # seconds; always shown
    hollow_body     = db.Column(db.Integer, nullable=True)   # seconds; always shown
    lunges          = db.Column(db.Integer, nullable=True)   # reps per leg; always shown

    notes           = db.Column(db.Text, nullable=True)      # optional user note
```

**Pull-up skip logic:** `pullups` is `null` when user's equipment does not include `'pullup_bar'`, `'dip_bars'`, or `'rings'`. All other exercises are always present (0 is a valid result, null means skipped).

---

## Endpoints

### `PATCH /api/user/active-module`

Lives in `app/core/routes.py` (modifies the User model, not calisthenics-specific).

Auth: Bearer JWT.

Body: `{ "module": "gym" | "calisthenics" }`

Updates `user.active_module`. Returns `{ "success": true, "data": { "active_module": "calisthenics" } }`.

Validation: reject values other than `'gym'` and `'calisthenics'`.

### `GET /api/calisthenics/profile`

Returns `CalisthenicsProfile` or `{ "data": null }` if not set up yet.

Response:
```json
{
  "success": true,
  "data": {
    "goals": ["muscle", "strength"],
    "equipment": ["floor", "bands", "dumbbells"],
    "days_per_week": 4,
    "session_duration_min": 45,
    "injuries": [],
    "motivation": "look"
  }
}
```

### `POST /api/calisthenics/profile`

Creates or updates (upsert) the profile. Returns same shape as GET.

Body: `{ goals, equipment, days_per_week, session_duration_min, injuries, motivation }`

Validation:
- `goals`: non-empty list, each item in allowed set
- `equipment`: list, each item in allowed set (can be empty)
- `days_per_week`: 1–7
- `session_duration_min`: 15–180
- `motivation`: one of allowed values

### `POST /api/calisthenics/assessment`

Saves a new assessment row. Returns the saved assessment with `id` and `assessed_at`.

Body:
```json
{
  "pullups": 0,
  "australian_pullups": 8,
  "pushups": 15,
  "pike_pushups": 10,
  "squats": 25,
  "superman_hold": 30,
  "plank": 45,
  "hollow_body": 20,
  "lunges": 12,
  "notes": ""
}
```

`pullups` may be omitted or `null` if user has no pullup equipment — stored as `null`.
All other fields: integer ≥ 0, required (0 is valid).

### `GET /api/calisthenics/assessment/history`

Returns all assessments for the user, newest first.

```json
{
  "success": true,
  "data": [
    {
      "id": 3,
      "assessed_at": "2026-04-25T14:00:00",
      "pullups": null,
      "australian_pullups": 8,
      "pushups": 15,
      ...
    }
  ]
}
```

---

## Assessment Exercise List

| Exercise | Metric | Shown when |
|----------|--------|------------|
| Підтягування | макс повторів (0 — ок) | equipment includes pullup_bar / dip_bars / rings |
| Австралійські підтягування | макс повторів | always |
| Віджимання | макс повторів | always |
| Pike push-ups | макс повторів | always |
| Присідання | макс повторів | always |
| Superman hold | секунди | always |
| Планка | секунди | always |
| Hollow body hold | секунди | always |
| Випади | макс (кожна нога) | always |

---

## Frontend (`app/templates/index.html`)

### Mode switcher

In the Train tab, above all other content:

```html
<div class="module-switcher">
  <button onclick="switchModule('gym')">Зал</button>
  <button onclick="switchModule('calisthenics')">Калістеніка</button>
</div>
```

`switchModule(mode)` calls `PATCH /api/user/active-module`, updates `S.activeModule`, re-renders Train and Program tabs.

### State additions

```javascript
S.activeModule = 'gym'          // loaded from user profile on app start
S.calisthenicsProfile = null    // loaded when switching to calisthenics
```

### Calisthenics first-open flow

```javascript
async function loadCalisthenicsMode() {
  const r = await api('GET', '/api/calisthenics/profile');
  if (!r.data) { renderCalisthenicsWizard(); return; }
  S.calisthenicsProfile = r.data;
  renderCalisthenicsHome();
}
```

### Setup Wizard (5 screens)

Full-panel overlay, one question per screen:

1. **Ціль** — multi-select chips: М'язи / Сила / Скіл / Схуднення / Витривалість
2. **Обладнання** — multi-select chips: Підлога / Резинки / Гантелі / Турнік / Бруси / Кільця / Паралетки / Нічого додаткового
3. **Розклад** — days per week (1–7 selector) + session duration (slider or select)
4. **Обмеження** — pre-filled from existing user profile injuries, confirm or edit
5. **Мотивація** — 4 option buttons: Виглядати / Відчувати / Досягати / Здоров'я

On final step: `POST /api/calisthenics/profile` → `renderCalisthenicsAssessment()`.

### Assessment screen

After wizard (or tappable from calisthenics home: "Пройти тест знову"):

- Title: "Стартова точка" (or "Переоцінка" if not first time)
- For each exercise: name + input field (number)
- Pullups row hidden if equipment has no bar/rings
- Optional notes field at bottom
- "Зберегти результати" button → `POST /api/calisthenics/assessment`
- On success: show summary card with results, button "До тренувань"

### Calisthenics home (after setup)

```
┌─────────────────────────────────────────┐
│  [Зал]  [Калістеніка ●]                 │  ← segment control
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  Остання оцінка: 25 квітня              │
│  Віджимання: 15  Планка: 45с  ...       │
│  [Пройти тест знову]                    │
└─────────────────────────────────────────┘

[ Програма генерується в наступному модулі ]
```

### Program tab

```javascript
function loadProgramTab() {
  if (S.activeModule === 'calisthenics') {
    loadCalisthenicsProgram(); // stub for now — "Програма скоро"
  } else {
    loadGymProgram(); // existing logic
  }
}
```

---

## Error Handling

- `active_module` invalid value → 400 `INVALID_MODULE`
- Profile POST with missing required fields → 400 `INVALID_FIELD`
- Assessment POST with non-integer values → 400 `INVALID_FIELD`
- Assessment POST before profile exists → 400 `PROFILE_REQUIRED`

---

## What Is NOT in Scope

- Plan generation (Phase 2)
- Workout logging (Phase 3)
- Progress photos (Phase 4)
- Analytics & streaks (Phase 4)
- Lever progressions / auto-advance
- AI feedback on assessment results (beyond level detection — Phase 2)
