# Insights Toggle & i18n (EN/UK) Design

## Goal

Two features:
1. **Insights Toggle** — show/hide exercise insights in Program tab (default hidden)
2. **i18n** — English/Ukrainian language switch, configurable in profile, stored in DB

## Architecture

No new API endpoints. One DB migration (add `app_language` to users). One backend change (`_PROFILE_FIELDS`). All UI logic in `app/templates/index.html`.

**Tech Stack:** Flask, SQLAlchemy, SQLite, Telegram Mini App SPA

---

## 1. Database

### Migration: add `app_language` to `users`

```sql
ALTER TABLE users ADD COLUMN app_language VARCHAR(10) DEFAULT 'en';
```

Nullable, default `'en'`. Valid values: `'en'`, `'uk'`.

---

## 2. Backend

### app/core/routes.py

Add `'app_language'` to `_PROFILE_FIELDS` set. No other backend changes — `GET /api/users/me` and `PATCH /api/users/me` automatically handle the new field.

### app/core/models.py

Add column to User model:
```python
app_language = db.Column(db.String(10), default='en')
```

---

## 3. Frontend

### 3.1 Insights Toggle

**Default state:** insights hidden (`_showInsights = false`).

**When `insights_generated = true`**, the header area shows:
```
✓ Exercise Insights Ready     [SHOW INSIGHTS]
```
(flex row, space-between)

**Toggle behavior:**
- `_showInsights` toggles between `true`/`false`
- CSS class `insights-hidden` added/removed on `#program-content`
- Button text: `t('show_insights')` / `t('hide_insights')`

**CSS:**
```css
#program-content.insights-hidden .prog-insight { display: none; }
```

No re-render needed.

---

### 3.2 i18n

**Translation dictionary** (`TRANSLATIONS`) in JS:

```js
const TRANSLATIONS = {
  en: {
    // Nav
    tab_train: 'Train', tab_program: 'Program', tab_nutrition: 'Nutrition',
    tab_sleep: 'Sleep', tab_coach: 'Coach',
    // Program tab
    week: 'Week', current: 'CURRENT',
    why_exercise: 'Why this exercise', expected_outcome: 'Expected outcome',
    modification: 'Modification',
    show_insights: 'SHOW INSIGHTS', hide_insights: 'HIDE INSIGHTS',
    insights_ready: '✓ Exercise Insights Ready',
    generate_insights: 'GENERATE EXERCISE INSIGHTS',
    generating_insights: 'GENERATING INSIGHTS...',
    no_program: 'No Program Yet', no_program_body: 'Generate your personalized training program first.',
    generate_program: 'GENERATE PROGRAM',
    // Profile overlay
    profile_title: 'Profile',
    edit: 'EDIT', save: 'SAVE', cancel: 'CANCEL',
    section_physical: 'Physical', section_goals: 'Goals',
    section_training: 'Training', section_health: 'Health & Notes',
    section_cycle: 'Cycle', section_language: 'Language',
    field_name: 'Name', field_gender: 'Gender', field_age: 'Age',
    field_weight: 'Weight', field_height: 'Height', field_body_fat: 'Body Fat',
    field_primary_goal: 'Primary Goal', field_secondary: 'Secondary',
    field_level: 'Level', field_days_week: 'Days / Week',
    field_session_duration: 'Session Duration', field_equipment: 'Equipment',
    field_likes: 'Likes', field_dislikes: 'Dislikes',
    field_injuries_current: 'Current Injuries', field_injuries_history: 'Injury History',
    field_postural: 'Postural Issues', field_mobility: 'Mobility Issues',
    field_imbalances: 'Muscle Imbalances',
    field_cycle_length: 'Cycle Length', field_last_period: 'Last Period',
    field_language: 'Language',
    lang_en: 'English', lang_uk: 'Українська',
    // Session
    start_workout: 'START WORKOUT', finish_workout: 'FINISH',
    log_set: 'LOG SET', rest: 'Rest',
    // General
    loading: 'Loading...', saving: 'Saving...', save_failed: 'Save failed',
    failed_load_profile: 'Failed to load profile',
    failed_load_program: 'Failed to load program',
    done: 'DONE', try_again: 'TRY AGAIN',
  },
  uk: {
    // Nav
    tab_train: 'Тренування', tab_program: 'Програма',
    tab_nutrition: 'Харчування', tab_sleep: 'Сон', tab_coach: 'Тренер',
    // Program tab
    week: 'Тиждень', current: 'ПОТОЧНИЙ',
    why_exercise: 'Чому ця вправа', expected_outcome: 'Очікуваний результат',
    modification: 'Модифікація',
    show_insights: 'ПОКАЗАТИ ІНСАЙТИ', hide_insights: 'СХОВАТИ ІНСАЙТИ',
    insights_ready: '✓ Інсайти готові',
    generate_insights: 'ЗГЕНЕРУВАТИ ІНСАЙТИ',
    generating_insights: 'ГЕНЕРУЄМО ІНСАЙТИ...',
    no_program: 'Програми ще немає', no_program_body: 'Спочатку згенеруй персоналізовану програму тренувань.',
    generate_program: 'ЗГЕНЕРУВАТИ ПРОГРАМУ',
    // Profile overlay
    profile_title: 'Профіль',
    edit: 'РЕДАГУВАТИ', save: 'ЗБЕРЕГТИ', cancel: 'СКАСУВАТИ',
    section_physical: 'Фізичні дані', section_goals: 'Цілі',
    section_training: 'Тренування', section_health: 'Здоров\'я та нотатки',
    section_cycle: 'Цикл', section_language: 'Мова',
    field_name: 'Ім\'я', field_gender: 'Стать', field_age: 'Вік',
    field_weight: 'Вага', field_height: 'Зріст', field_body_fat: 'Відсоток жиру',
    field_primary_goal: 'Основна ціль', field_secondary: 'Додаткова',
    field_level: 'Рівень', field_days_week: 'Днів на тиждень',
    field_session_duration: 'Тривалість тренування', field_equipment: 'Обладнання',
    field_likes: 'Подобається', field_dislikes: 'Не подобається',
    field_injuries_current: 'Поточні травми', field_injuries_history: 'Історія травм',
    field_postural: 'Постуральні проблеми', field_mobility: 'Проблеми з мобільністю',
    field_imbalances: 'М\'язові дисбаланси',
    field_cycle_length: 'Довжина циклу', field_last_period: 'Остання менструація',
    field_language: 'Мова',
    lang_en: 'English', lang_uk: 'Українська',
    // Session
    start_workout: 'ПОЧАТИ ТРЕНУВАННЯ', finish_workout: 'ЗАВЕРШИТИ',
    log_set: 'ЗАПИСАТИ ПІДХІД', rest: 'Відпочинок',
    // General
    loading: 'Завантаження...', saving: 'Зберігаємо...', save_failed: 'Помилка збереження',
    failed_load_profile: 'Не вдалося завантажити профіль',
    failed_load_program: 'Не вдалося завантажити програму',
    done: 'ГОТОВО', try_again: 'СПРОБУВАТИ ЗНОВУ',
  },
};
```

**`t(key)` function:**
```js
function t(key) { return TRANSLATIONS[_lang]?.[key] ?? TRANSLATIONS.en[key] ?? key; }
```

**`applyTranslations()` function** — updates static DOM elements:
- Nav tab labels (`.nav-tab-label` text by data-tab attribute)
- Overlay titles (`overlay-profile` title)
- Static buttons (e.g. "DONE" button in feedback overlay)

**Language init:** called in `initApp()` after user data loaded:
```js
_lang = userData.app_language || 'en';
applyTranslations();
```

**Language change:** in `saveProfile()` — after successful PATCH, if `app_language` changed, update `_lang`, call `applyTranslations()`, re-render current tab.

**Profile edit mode** — language selector added to edit form:
```html
<select data-field="app_language">
  <option value="en">English</option>
  <option value="uk">Українська</option>
</select>
```
(not a numeric field — handled as plain string in saveProfile)

---

## 4. File Changes

| File | Change |
|------|--------|
| `app/core/models.py` | Add `app_language` column to User |
| `migrations/versions/xxxx_add_app_language.py` | New migration |
| `app/core/routes.py` | Add `'app_language'` to `_PROFILE_FIELDS` |
| `app/templates/index.html` | Insights toggle CSS/JS, TRANSLATIONS dict, t(), applyTranslations(), update all rendered strings |

---

## 5. Error Handling

- If `app_language` is an unknown value, `t()` falls back to `en` via `?? TRANSLATIONS.en[key]`.
- Language field in PATCH: unknown values silently ignored by existing allowlist logic (only `app_language` accepted, value not validated server-side — frontend only sends `'en'` or `'uk'`).
