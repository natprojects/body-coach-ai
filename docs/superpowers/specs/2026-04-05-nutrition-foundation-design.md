# Nutrition Foundation — Design Spec (v1.0)

**Goal:** Build the Nutrition module foundation: profile setup, BMR/TDEE/macro calculation, water recommendation, and an AI chat for ingredient-based meal advice with meal logging for variety tracking.

---

## Overview

When a user opens the Nutrition tab for the first time, a 5-step setup wizard collects their diet profile. After setup, the tab shows a compact targets card (calories, macros, water) plus a full-screen chat where the user describes available ingredients and the AI recommends what to cook — informed by their goals, meal history, training data, cycle phase, and recovery state.

This is the foundation for the Nutrition module. Meal Plan (AI weekly plan) and Supplements are separate specs built on top of this.

---

## Architecture

```
app/modules/nutrition/
├── __init__.py       # Blueprint registration (prefix /api)
├── models.py         # NutritionProfile, MealLog
├── calculator.py     # Pure functions: BMR, TDEE, macros, water
├── context.py        # build_nutrition_context() — aggregates user data for AI
└── routes.py         # All endpoints
```

Registered in `app/__init__.py` following the same pattern as training and coach modules.

One new Alembic migration: tables `nutrition_profiles` and `meal_logs`.

---

## Data Model

### `NutritionProfile` (one-to-one with User)

```python
class NutritionProfile(db.Model):
    __tablename__ = 'nutrition_profiles'
    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)

    # Profile
    diet_type       = db.Column(db.String(20))   # omnivore / vegetarian / vegan / pescatarian
    allergies       = db.Column(db.JSON)          # ['gluten', 'lactose', 'nuts', 'eggs', 'shellfish', 'soy']
    cooking_skill   = db.Column(db.String(20))   # beginner / intermediate / advanced
    budget          = db.Column(db.String(20))   # low / medium / high
    activity_outside = db.Column(db.String(20))  # sedentary / lightly / moderately / very

    # Calculated & cached (recomputed on profile update or weight change)
    bmr             = db.Column(db.Float)
    tdee            = db.Column(db.Float)
    calorie_target  = db.Column(db.Float)
    protein_g       = db.Column(db.Float)
    fat_g           = db.Column(db.Float)
    carbs_g         = db.Column(db.Float)

    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

### `MealLog`

```python
class MealLog(db.Model):
    __tablename__ = 'meal_logs'
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date        = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=False)   # "Гречка з куркою і овочами"
    logged_at   = db.Column(db.DateTime, default=datetime.utcnow)
```

Plain text description — no nutritional breakdown. AI uses recent entries to ensure meal variety.

---

## Calculations (`calculator.py`)

All pure functions — no DB access, fully testable.

### BMR — Mifflin-St Jeor

```python
def calc_bmr(weight_kg, height_cm, age, gender) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base - 161 if gender == 'female' else base + 5
```

### TDEE

Activity factor combines `activity_outside` (base) and `training_days_per_week` (bonus):

| `activity_outside` | Base factor |
|--------------------|-------------|
| sedentary          | 1.20        |
| lightly            | 1.375       |
| moderately         | 1.55        |
| very               | 1.725       |

Training bonus (added to base):
- 0–1 days/week → +0.00
- 2–3 days/week → +0.10
- 4–5 days/week → +0.175
- 6–7 days/week → +0.25

```python
def calc_tdee(bmr, activity_outside, training_days_per_week) -> float:
    base = BASE_FACTORS[activity_outside]
    bonus = training_bonus(training_days_per_week)
    return bmr * (base + bonus)
```

### Calorie Target

Based on `user.goal_primary`:
- `fat_loss` → TDEE − 400 kcal
- `hypertrophy` / `strength` → TDEE + 250 kcal
- all others → TDEE

### Macros

```python
def calc_macros(weight_kg, calorie_target) -> dict:
    protein_g = round(2.0 * weight_kg, 1)
    fat_g     = round(calorie_target * 0.28 / 9, 1)
    carbs_g   = round((calorie_target - protein_g * 4 - fat_g * 9) / 4, 1)
    return {'protein_g': protein_g, 'fat_g': fat_g, 'carbs_g': carbs_g}
```

### Water Recommendation

```python
def calc_water_ml(weight_kg) -> float:
    return round(weight_kg * 32.5)   # midpoint of 30–35 ml/kg
```

---

## Context Builder (`context.py`)

```python
def build_nutrition_context(user_id: int) -> str:
```

Aggregates for the AI system prompt:
- **Nutrition profile:** diet type, allergies, calorie/macro targets, goal
- **Meal log:** last 7 days entries (date + description)
- **Training:** last 3 sessions (muscle groups, volume)
- **Daily checkin:** today's energy and sleep quality
- **Cycle phase:** current phase + modifier if `menstrual_tracking=True`

Returns a single string injected into the AI system prompt. This gives the AI full context across all modules — training, recovery, cycle, and nutrition history.

---

## Endpoints

### `GET /api/nutrition/profile`

Auth: Bearer JWT.

Returns the user's `NutritionProfile` with all targets, or `{"data": null}` if not set up yet.

Response:
```json
{
  "success": true,
  "data": {
    "diet_type": "omnivore",
    "allergies": ["lactose"],
    "cooking_skill": "intermediate",
    "budget": "medium",
    "activity_outside": "moderately",
    "calorie_target": 2150,
    "protein_g": 132,
    "fat_g": 67,
    "carbs_g": 248,
    "water_ml": 1950
  }
}
```

Note: `water_ml` is calculated on the fly from current `user.weight_kg` — not stored.

### `POST /api/nutrition/profile`

Auth: Bearer JWT.

Body: `{ diet_type, allergies, cooking_skill, budget, activity_outside }`

Creates or updates (upsert) the profile. Recalculates BMR/TDEE/macros and saves. Returns same shape as GET.

### `GET /api/nutrition/chat/thread`

Returns the user's active nutrition chat thread (creates one if none exists), including the last 20 messages.

### `POST /api/nutrition/chat/message`

Body: `{ thread_id, content }`

Streams AI response using `stream_chat()` from `app/core/ai.py`. System prompt is built by `build_nutrition_context()`. Uses existing `ChatThread`/`ChatMessage` models with `module='nutrition'`.

### `POST /api/nutrition/meals/log`

Body: `{ description }` — logs today's meal.

### `GET /api/nutrition/meals/log`

Returns last 14 days of meal log entries.

---

## Frontend (`app/templates/index.html`)

### Tab load

```javascript
async function loadNutritionTab() {
  const r = await api('GET', '/api/nutrition/profile');
  if (!r.data) { renderNutritionSetup(); return; }
  S.nutritionProfile = r.data;
  renderNutritionTab();
}
```

Add `if (name === 'nutrition') loadNutritionTab();` to `switchTab()`.

### Setup Wizard (5 screens)

Shown on first open. Each screen is a full-panel overlay with one question:

1. **Тип дієти** — 4 option buttons: Omnivore / Vegetarian / Vegan / Pescatarian
2. **Алергії** — multi-select chips (skip button available)
3. **Активність поза тренуваннями** — 4 options: Сидяча / Легка / Помірна / Висока
4. **Кулінарні навички** — 3 options: Початківець / Середній / Досвідчений
5. **Бюджет** — 3 options: Низький / Середній / Високий

On final step: POST `/api/nutrition/profile` → `renderNutritionTab()`.

### Nutrition Tab (after setup)

```
┌─────────────────────────────────────────┐
│  🔥 2 150 ккал  ·  🥩 132г  ·  💧 1.95л  │  ← compact card
└─────────────────────────────────────────┘

[Chat messages area — scrollable]

┌─────────────────────────────────────────┐
│  Що є в холодильнику?                   │
│                                [→] [✓]  │  ← [→] = send, [✓] = log as meal
└─────────────────────────────────────────┘
```

- **[→]** sends message to AI chat
- **[✓]** logs the last AI recommendation as a meal entry (one tap)

### State additions

```javascript
S.nutritionProfile = null   // profile + targets
S.nutritionThread  = null   // active chat thread
```

---

## Error Handling

- If `user.weight_kg` or `user.height_cm` is null → `GET /api/nutrition/profile` returns error asking to complete onboarding first
- If AI call fails → return error message in chat, meal log is unaffected
- If macros result in negative carbs (very high protein + fat targets) → clamp carbs to 0 and note in response

---

## What Is NOT in Scope

- Meal Plan (AI weekly plan) — separate spec
- Supplements — separate spec
- Calorie counting / nutritional breakdown of meals
- Food database / barcode scanning
- Macro tracking (logging actual intake vs targets)
- Notifications ("time to eat")
