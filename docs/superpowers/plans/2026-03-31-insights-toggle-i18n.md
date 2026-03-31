# Insights Toggle & i18n (EN/UK) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a show/hide insights toggle to the Program tab, and full EN/UK language switching stored in the user's profile in the DB.

**Architecture:** One DB migration adds `app_language` to `users`. The backend just adds the field to `_PROFILE_FIELDS`. All i18n is client-side: a `TRANSLATIONS` dict, a `t(key)` lookup function, and `applyTranslations()` that updates DOM. Language is loaded on `loadMain()` and saved via `PATCH /api/users/me`. Insights toggle is a CSS class toggle — no re-render needed.

**Tech Stack:** Flask, SQLAlchemy, SQLite, Telegram Mini App SPA (single `app/templates/index.html`), pytest

---

## File Map

| File | Change |
|------|--------|
| `app/core/models.py` | Add `app_language` column to User |
| `migrations/versions/d4e5f6a7b8c9_add_app_language.py` | New migration |
| `app/core/routes.py` | Add `'app_language'` to `_PROFILE_FIELDS` |
| `app/templates/index.html` | Insights toggle CSS/JS + full i18n |
| `tests/core/test_core_routes.py` | Add test for app_language in GET/PATCH |

---

## Task 1: Backend — app_language field

**Files:**
- Modify: `app/core/models.py:33`
- Create: `migrations/versions/d4e5f6a7b8c9_add_app_language.py`
- Modify: `app/core/routes.py` (`_PROFILE_FIELDS`)
- Modify: `tests/core/test_core_routes.py`

- [ ] **Step 1: Write failing test**

Add to `tests/core/test_core_routes.py`:

```python
def test_app_language_in_profile(client, app, db):
    from app.core.models import User
    user = User(telegram_id=50001, name='LangTest')
    db.session.add(user)
    db.session.commit()
    # GET returns app_language
    resp = client.get('/api/users/me', headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'app_language' in data['data']

    # PATCH updates app_language
    resp2 = client.patch('/api/users/me',
                         json={'app_language': 'uk'},
                         headers=_auth_header(app, user.id))
    assert resp2.status_code == 200
    assert resp2.get_json()['data']['app_language'] == 'uk'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/natalie/body-coach-ai && pytest tests/core/test_core_routes.py::test_app_language_in_profile -v
```
Expected: FAIL (`'app_language' not in data['data']`)

- [ ] **Step 3: Add column to User model**

In `app/core/models.py`, after line 33 (`motivation_type = ...`), add:

```python
    app_language = db.Column(db.String(10), default='en')
```

- [ ] **Step 4: Create migration file**

Create `migrations/versions/d4e5f6a7b8c9_add_app_language.py`:

```python
"""add app_language to users

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Branch Labels: None
Depends On: None

"""
from alembic import op
import sqlalchemy as sa

revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('app_language', sa.String(10), nullable=True, server_default='en'))


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('app_language')
```

- [ ] **Step 5: Add app_language to _PROFILE_FIELDS**

In `app/core/routes.py`, find `_PROFILE_FIELDS = {` and add `'app_language'` to the set. The current last line of the set is `'had_coach_before', 'motivation_type',`. Change to:

```python
_PROFILE_FIELDS = {
    'name', 'gender', 'age', 'weight_kg', 'height_cm', 'body_fat_pct',
    'goal_primary', 'goal_secondary', 'level', 'training_days_per_week',
    'session_duration_min', 'equipment', 'injuries_current', 'injuries_history',
    'postural_issues', 'mobility_issues', 'muscle_imbalances',
    'menstrual_tracking', 'cycle_length_days', 'last_period_date',
    'training_likes', 'training_dislikes', 'previous_methods',
    'had_coach_before', 'motivation_type', 'app_language',
}
```

- [ ] **Step 6: Run migration**

```bash
cd /Users/natalie/body-coach-ai && flask db upgrade
```
Expected: `Running upgrade c3d4e5f6a7b8 -> d4e5f6a7b8c9`

- [ ] **Step 7: Run tests**

```bash
cd /Users/natalie/body-coach-ai && pytest -v
```
Expected: all pass

- [ ] **Step 8: Commit**

```bash
cd /Users/natalie/body-coach-ai && git add app/core/models.py migrations/versions/d4e5f6a7b8c9_add_app_language.py app/core/routes.py tests/core/test_core_routes.py && git commit -m "feat: add app_language field to user profile"
```

---

## Task 2: Frontend — Insights Toggle

**Files:**
- Modify: `app/templates/index.html`

This task adds a CSS rule and replaces the `insightsBtn` logic to include a SHOW/HIDE toggle button. Default state is hidden.

- [ ] **Step 1: Add CSS for insights-hidden**

In `app/templates/index.html`, find the `.prog-mod-badge` CSS rule (last rule in the program CSS section):

```css
    .prog-mod-badge { color: #ffaa44; font-size: 11px; }
```

Replace with:

```css
    .prog-mod-badge { color: #ffaa44; font-size: 11px; }
    #program-content.insights-hidden .prog-insight { display: none; }
```

- [ ] **Step 2: Add `_showInsights` global and `toggleInsightsVisibility` function**

In `app/templates/index.html`, find:

```js
// ── PROGRAM TAB ──
let _programData = null;
```

Replace with:

```js
// ── PROGRAM TAB ──
let _programData = null;
let _showInsights = false;

function toggleInsightsVisibility() {
  _showInsights = !_showInsights;
  const content = document.getElementById('program-content');
  if (content) content.classList.toggle('insights-hidden', !_showInsights);
  const btn = document.getElementById('insights-toggle-btn');
  if (btn) btn.textContent = _showInsights ? 'HIDE INSIGHTS' : 'SHOW INSIGHTS';
}
```

- [ ] **Step 3: Update insightsBtn to include toggle button**

In `app/templates/index.html`, find the exact text:

```js
  const insightsBtn = p.insights_generated
    ? `<div class="insights-ready">✓ Exercise Insights Ready</div>`
    : `<div class="prog-insights-btn">
        <button class="btn btn-ghost" id="insights-btn" onclick="generateInsights()">
          GENERATE EXERCISE INSIGHTS
        </button>
      </div>`;
```

Replace with:

```js
  const insightsBtn = p.insights_generated
    ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <div class="insights-ready">✓ Exercise Insights Ready</div>
        <button class="btn btn-ghost" id="insights-toggle-btn"
          style="width:auto;padding:6px 14px;font-size:12px;flex-shrink:0"
          onclick="toggleInsightsVisibility()">${_showInsights ? 'HIDE INSIGHTS' : 'SHOW INSIGHTS'}</button>
      </div>`
    : `<div class="prog-insights-btn">
        <button class="btn btn-ghost" id="insights-btn" onclick="generateInsights()">
          GENERATE EXERCISE INSIGHTS
        </button>
      </div>`;
```

- [ ] **Step 4: Apply insights-hidden class on render**

After `renderProgramTab()` sets `el.innerHTML`, the `#program-content` element is replaced — so we need to re-apply the CSS class after render. Find the end of `renderProgramTab()`:

```js
  el.innerHTML = `
    <div class="prog-header">
      <div class="prog-title">${_esc(p.name)}</div>
      <div class="prog-meta">${_esc(p.total_weeks)} weeks · ${_esc(p.periodization_type)}</div>
      ${insightsBtn}
    </div>
    ${mesosHtml}`;
}
```

Replace with:

```js
  el.innerHTML = `
    <div class="prog-header">
      <div class="prog-title">${_esc(p.name)}</div>
      <div class="prog-meta">${_esc(p.total_weeks)} weeks · ${_esc(p.periodization_type)}</div>
      ${insightsBtn}
    </div>
    ${mesosHtml}`;
  if (!_showInsights && p.insights_generated) {
    el.classList.add('insights-hidden');
  } else {
    el.classList.remove('insights-hidden');
  }
}
```

- [ ] **Step 5: Run full test suite**

```bash
cd /Users/natalie/body-coach-ai && pytest -v
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd /Users/natalie/body-coach-ai && git add app/templates/index.html && git commit -m "feat: add show/hide insights toggle to program tab (default hidden)"
```

---

## Task 3: Frontend — i18n Foundation

**Files:**
- Modify: `app/templates/index.html`

This task adds the `TRANSLATIONS` dict, `t()` function, `_lang` global, `applyTranslations()`, and wires language loading into `loadMain()`.

- [ ] **Step 1: Add i18n globals and TRANSLATIONS dict**

In `app/templates/index.html`, find:

```js
// ── PROGRAM TAB ──
let _programData = null;
let _showInsights = false;
```

Replace with:

```js
// ── I18N ──
let _lang = 'en';

const TRANSLATIONS = {
  en: {
    tab_train: 'Train', tab_program: 'Program', tab_nutrition: 'Nutrition',
    tab_sleep: 'Sleep', tab_coach: 'Coach',
    week: 'Week', current: 'CURRENT',
    why_exercise: 'Why this exercise', expected_outcome: 'Expected outcome',
    modification: 'Modification',
    show_insights: 'SHOW INSIGHTS', hide_insights: 'HIDE INSIGHTS',
    insights_ready: '✓ Exercise Insights Ready',
    generate_insights: 'GENERATE EXERCISE INSIGHTS',
    generating_insights: 'GENERATING INSIGHTS...',
    no_program: 'No Program Yet',
    no_program_body: 'Generate your personalized training program first.',
    generate_program: 'GENERATE PROGRAM',
    profile_title: 'Profile',
    edit: 'EDIT', save: 'SAVE', cancel: 'CANCEL',
    section_physical: 'Physical', section_goals: 'Goals',
    section_training: 'Training', section_health: 'Health & Notes',
    section_cycle: 'Cycle',
    field_name: 'Name', field_gender: 'Gender', field_age: 'Age',
    field_weight: 'Weight (kg)', field_height: 'Height (cm)',
    field_body_fat: 'Body Fat (%)', field_weight_view: 'Weight',
    field_height_view: 'Height', field_body_fat_view: 'Body Fat',
    field_primary_goal: 'Primary Goal', field_secondary: 'Secondary',
    field_level: 'Level', field_days_week: 'Days / Week',
    field_session_duration: 'Session Duration (min)',
    field_session_duration_view: 'Session Duration',
    field_equipment: 'Equipment',
    field_likes: 'Likes', field_dislikes: 'Dislikes',
    field_likes_edit: 'Training Likes', field_dislikes_edit: 'Training Dislikes',
    field_injuries_current: 'Current Injuries',
    field_injuries_history: 'Injury History',
    field_postural: 'Postural Issues', field_mobility: 'Mobility Issues',
    field_imbalances: 'Muscle Imbalances',
    field_cycle_length: 'Cycle Length', field_last_period: 'Last Period',
    field_language: 'Language',
    lang_en: 'English', lang_uk: 'Українська',
    today_training: "Today's Training",
    exercises: 'Exercises', sets: 'Sets', est_min: 'Est. min',
    start_workout: 'START WORKOUT', finish_workout: 'COMPLETE WORKOUT',
    no_program_train: 'No Program Yet',
    no_program_train_body: 'Generate your personalized training program to get started.',
    rest_day: 'Rest Day', rest_day_sub: 'Recover. You\'ve earned it.',
    loading: 'Loading...', saving: 'Saving...', save_failed: 'Save failed',
    failed_load_profile: 'Failed to load profile',
    failed_load_program: 'Failed to load program',
    done: 'DONE', try_again: 'TRY AGAIN',
    weeks_meta: 'weeks',
  },
  uk: {
    tab_train: 'Тренування', tab_program: 'Програма',
    tab_nutrition: 'Харчування', tab_sleep: 'Сон', tab_coach: 'Тренер',
    week: 'Тиждень', current: 'ПОТОЧНИЙ',
    why_exercise: 'Чому ця вправа', expected_outcome: 'Очікуваний результат',
    modification: 'Модифікація',
    show_insights: 'ПОКАЗАТИ ІНСАЙТИ', hide_insights: 'СХОВАТИ ІНСАЙТИ',
    insights_ready: '✓ Інсайти готові',
    generate_insights: 'ЗГЕНЕРУВАТИ ІНСАЙТИ',
    generating_insights: 'ГЕНЕРУЄМО ІНСАЙТИ...',
    no_program: 'Програми ще немає',
    no_program_body: 'Спочатку згенеруй персоналізовану програму тренувань.',
    generate_program: 'ЗГЕНЕРУВАТИ ПРОГРАМУ',
    profile_title: 'Профіль',
    edit: 'РЕДАГУВАТИ', save: 'ЗБЕРЕГТИ', cancel: 'СКАСУВАТИ',
    section_physical: 'Фізичні дані', section_goals: 'Цілі',
    section_training: 'Тренування', section_health: 'Здоров\'я та нотатки',
    section_cycle: 'Цикл',
    field_name: 'Ім\'я', field_gender: 'Стать', field_age: 'Вік',
    field_weight: 'Вага (кг)', field_height: 'Зріст (см)',
    field_body_fat: 'Відсоток жиру (%)', field_weight_view: 'Вага',
    field_height_view: 'Зріст', field_body_fat_view: 'Відсоток жиру',
    field_primary_goal: 'Основна ціль', field_secondary: 'Додаткова',
    field_level: 'Рівень', field_days_week: 'Днів на тиждень',
    field_session_duration: 'Тривалість (хв)',
    field_session_duration_view: 'Тривалість тренування',
    field_equipment: 'Обладнання',
    field_likes: 'Подобається', field_dislikes: 'Не подобається',
    field_likes_edit: 'Що подобається', field_dislikes_edit: 'Що не подобається',
    field_injuries_current: 'Поточні травми',
    field_injuries_history: 'Історія травм',
    field_postural: 'Постуральні проблеми', field_mobility: 'Проблеми з мобільністю',
    field_imbalances: 'М\'язові дисбаланси',
    field_cycle_length: 'Довжина циклу', field_last_period: 'Остання менструація',
    field_language: 'Мова',
    lang_en: 'English', lang_uk: 'Українська',
    today_training: 'Тренування сьогодні',
    exercises: 'Вправи', sets: 'Підходи', est_min: 'Хв приблизно',
    start_workout: 'ПОЧАТИ ТРЕНУВАННЯ', finish_workout: 'ЗАВЕРШИТИ ТРЕНУВАННЯ',
    no_program_train: 'Програми ще немає',
    no_program_train_body: 'Згенеруй персоналізовану програму, щоб почати.',
    rest_day: 'День відпочинку', rest_day_sub: 'Відновлюйся. Ти це заслужила.',
    loading: 'Завантаження...', saving: 'Зберігаємо...', save_failed: 'Помилка збереження',
    failed_load_profile: 'Не вдалося завантажити профіль',
    failed_load_program: 'Не вдалося завантажити програму',
    done: 'ГОТОВО', try_again: 'СПРОБУВАТИ ЗНОВУ',
    weeks_meta: 'тижнів',
  },
};

function t(key) { return TRANSLATIONS[_lang]?.[key] ?? TRANSLATIONS.en[key] ?? key; }

function applyTranslations() {
  // Nav tab labels
  const navMap = {train:'tab_train', program:'tab_program', nutrition:'tab_nutrition', sleep:'tab_sleep', coach:'tab_coach'};
  document.querySelectorAll('.nav-tab').forEach(tab => {
    const key = navMap[tab.dataset.tab];
    const lbl = tab.querySelector('.nav-tab-label');
    if (key && lbl) lbl.textContent = t(key);
  });
  // Profile overlay title
  const profileTitle = document.querySelector('#overlay-profile .overlay-title');
  if (profileTitle) profileTitle.textContent = t('profile_title');
  // Profile edit toggle button (only if in view mode)
  const editToggle = document.getElementById('profile-edit-toggle');
  if (editToggle && editToggle.style.display !== 'none') editToggle.textContent = t('edit');
  // Profile save/cancel buttons
  const editBar = document.getElementById('profile-edit-bar');
  if (editBar) {
    const btns = editBar.querySelectorAll('button');
    if (btns[0]) btns[0].textContent = t('cancel');
    if (btns[1]) btns[1].textContent = t('save');
  }
  // Feedback overlay done button
  const feedbackDone = document.querySelector('#overlay-feedback .btn-primary');
  if (feedbackDone) feedbackDone.textContent = t('done');
}

// ── PROGRAM TAB ──
let _programData = null;
let _showInsights = false;

function toggleInsightsVisibility() {
```

- [ ] **Step 2: Load language in loadMain()**

Find the current `loadMain` function:

```js
async function loadMain() {
  setLoading('Loading workout...');
  const r = await api('GET', '/api/training/today');
  S.todayWorkout = r.success ? r.data : null;
  renderTrainTab();
  showScreen('main');
}
```

Replace with:

```js
async function loadMain() {
  setLoading('Loading workout...');
  const [r, userR] = await Promise.all([
    api('GET', '/api/training/today'),
    api('GET', '/api/users/me'),
  ]);
  S.todayWorkout = r.success ? r.data : null;
  if (userR.success && userR.data.app_language) {
    _lang = userR.data.app_language;
  }
  applyTranslations();
  renderTrainTab();
  showScreen('main');
}
```

- [ ] **Step 3: Update saveProfile() to re-apply language on change**

Find in `saveProfile()` the block after successful PATCH:

```js
  _profileData = r.data;
  msg.innerHTML = '';
  _profileEditMode = false;

  if (r.data.name) {
    const el = document.getElementById('user-name');
    if (el) el.textContent = r.data.name.toUpperCase();
  }
  renderProfileView();
```

Replace with:

```js
  const prevLang = _lang;
  _profileData = r.data;
  msg.innerHTML = '';
  _profileEditMode = false;

  if (r.data.name) {
    const el = document.getElementById('user-name');
    if (el) el.textContent = r.data.name.toUpperCase();
  }
  if (r.data.app_language && r.data.app_language !== prevLang) {
    _lang = r.data.app_language;
    applyTranslations();
    if (_programData) renderProgramTab();
    renderTrainTab();
  }
  renderProfileView();
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/natalie/body-coach-ai && pytest -v
```
Expected: all pass

- [ ] **Step 5: Commit**

```bash
cd /Users/natalie/body-coach-ai && git add app/templates/index.html && git commit -m "feat: add i18n foundation — TRANSLATIONS dict, t(), applyTranslations, language loading"
```

---

## Task 4: Frontend — Apply t() throughout UI + Language selector in profile

**Files:**
- Modify: `app/templates/index.html`

This task replaces all hardcoded English strings in JS-rendered content with `t()` calls, and adds a language `<select>` to the profile edit form.

- [ ] **Step 1: Update renderProgramTab() strings**

Find all hardcoded English strings in `renderProgramTab()` and replace with `t()` calls.

Find this block:

```js
  if (!p) {
    el.innerHTML = `
      <div class="no-program-card">
        <div class="np-title">No Program Yet</div>
        <div class="np-body">Generate your personalized training program first.</div>
        <button class="btn btn-primary" onclick="generateProgram()">GENERATE PROGRAM</button>
      </div>`;
    return;
  }
```

Replace with:

```js
  if (!p) {
    el.innerHTML = `
      <div class="no-program-card">
        <div class="np-title">${t('no_program')}</div>
        <div class="np-body">${t('no_program_body')}</div>
        <button class="btn btn-primary" onclick="generateProgram()">${t('generate_program')}</button>
      </div>`;
    return;
  }
```

Find:

```js
  const insightsBtn = p.insights_generated
    ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <div class="insights-ready">✓ Exercise Insights Ready</div>
        <button class="btn btn-ghost" id="insights-toggle-btn"
          style="width:auto;padding:6px 14px;font-size:12px;flex-shrink:0"
          onclick="toggleInsightsVisibility()">${_showInsights ? 'HIDE INSIGHTS' : 'SHOW INSIGHTS'}</button>
      </div>`
    : `<div class="prog-insights-btn">
        <button class="btn btn-ghost" id="insights-btn" onclick="generateInsights()">
          GENERATE EXERCISE INSIGHTS
        </button>
      </div>`;
```

Replace with:

```js
  const insightsBtn = p.insights_generated
    ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <div class="insights-ready">${t('insights_ready')}</div>
        <button class="btn btn-ghost" id="insights-toggle-btn"
          style="width:auto;padding:6px 14px;font-size:12px;flex-shrink:0"
          onclick="toggleInsightsVisibility()">${t(_showInsights ? 'hide_insights' : 'show_insights')}</button>
      </div>`
    : `<div class="prog-insights-btn">
        <button class="btn btn-ghost" id="insights-btn" onclick="generateInsights()">
          ${t('generate_insights')}
        </button>
      </div>`;
```

Find these two lines inside the week/exercise rendering:

```js
              <span class="week-label">Week ${w.week_number}</span>
              ${isCurrent ? '<span class="week-current-badge">● CURRENT</span>' : '<span></span>'}
```

Replace with:

```js
              <span class="week-label">${t('week')} ${w.week_number}</span>
              ${isCurrent ? `<span class="week-current-badge">● ${t('current')}</span>` : '<span></span>'}
```

Find these three insight toggle labels:

```js
                          onclick="toggleInsight(this)"><span class="insight-arrow">▶</span> Why this exercise</button>
```
Replace with:
```js
                          onclick="toggleInsight(this)"><span class="insight-arrow">▶</span> ${t('why_exercise')}</button>
```

Find:
```js
                          onclick="toggleInsight(this)"><span class="insight-arrow">▶</span> Expected outcome</button>
```
Replace with:
```js
                          onclick="toggleInsight(this)"><span class="insight-arrow">▶</span> ${t('expected_outcome')}</button>
```

Find:
```js
                          onclick="toggleInsight(this)"><span class="insight-arrow">▶</span> <span class="prog-mod-badge">⚠ Modification</span></button>
```
Replace with:
```js
                          onclick="toggleInsight(this)"><span class="insight-arrow">▶</span> <span class="prog-mod-badge">⚠ ${t('modification')}</span></button>
```

Find (program meta line):
```js
      <div class="prog-meta">${_esc(p.total_weeks)} weeks · ${_esc(p.periodization_type)}</div>
```
Replace with:
```js
      <div class="prog-meta">${_esc(p.total_weeks)} ${t('weeks_meta')} · ${_esc(p.periodization_type)}</div>
```

Find (loadProgramTab error):
```js
    el.innerHTML = '<div class="error-msg">Failed to load program</div>';
```
Replace with:
```js
    el.innerHTML = `<div class="error-msg">${t('failed_load_program')}</div>`;
```

Find (loadProgramTab loading):
```js
  el.innerHTML = '<div style="color:var(--muted);font-size:13px;text-align:center;padding:40px">Loading...</div>';
```
Replace with:
```js
  el.innerHTML = `<div style="color:var(--muted);font-size:13px;text-align:center;padding:40px">${t('loading')}</div>`;
```

Find (generateInsights button states):
```js
  btn.textContent = 'GENERATING INSIGHTS...';
```
Replace with:
```js
  btn.textContent = t('generating_insights');
```

Find:
```js
    btn.textContent = 'TRY AGAIN';
```
(inside `generateInsights`) Replace with:
```js
    btn.textContent = t('try_again');
```

- [ ] **Step 2: Update renderTrainTab() strings**

Find the no-program card in `renderTrainTab()`:

```js
    el.innerHTML = `
      <div class="no-program-card">
        <div class="np-title">No Program Yet</div>
        <div class="np-body">Generate your personalized training program to get started.</div>
        <button class="btn btn-primary" onclick="generateProgram()">GENERATE PROGRAM</button>
      </div>`;
```

Replace with:

```js
    el.innerHTML = `
      <div class="no-program-card">
        <div class="np-title">${t('no_program_train')}</div>
        <div class="np-body">${t('no_program_train_body')}</div>
        <button class="btn btn-primary" onclick="generateProgram()">${t('generate_program')}</button>
      </div>`;
```

Find the rest-day card:

```js
      <div class="rest-title">Rest Day</div>
      <div style="font-size:13px;color:var(--muted);margin-top:8px">Recover. You've earned it.</div>
```
Replace with:
```js
      <div class="rest-title">${t('rest_day')}</div>
      <div style="font-size:13px;color:var(--muted);margin-top:8px">${t('rest_day_sub')}</div>
```

Find in the hero card:
```js
      <div class="hero-label">Today's Training</div>
```
Replace with:
```js
      <div class="hero-label">${t('today_training')}</div>
```

Find:
```js
        <div class="stat"><span class="stat-value">${exCount}</span><span class="stat-label">Exercises</span></div>
        <div class="stat"><span class="stat-value">${setCount}</span><span class="stat-label">Sets</span></div>
        <div class="stat"><span class="stat-value">${estMin}</span><span class="stat-label">Est. min</span></div>
```
Replace with:
```js
        <div class="stat"><span class="stat-value">${exCount}</span><span class="stat-label">${t('exercises')}</span></div>
        <div class="stat"><span class="stat-value">${setCount}</span><span class="stat-label">${t('sets')}</span></div>
        <div class="stat"><span class="stat-value">${estMin}</span><span class="stat-label">${t('est_min')}</span></div>
```

Find:
```js
      <button class="btn btn-primary" onclick="startWorkout()">START WORKOUT</button>
```
Replace with:
```js
      <button class="btn btn-primary" onclick="startWorkout()">${t('start_workout')}</button>
```

- [ ] **Step 3: Update renderProfileView() strings**

Find the sections array in `renderProfileView()`:

```js
  const sections = [
    { title: 'Physical', rows: [
      ['Name', d.name], ['Gender', d.gender], ['Age', d.age],
      ['Weight', d.weight_kg ? d.weight_kg + ' kg' : '—'],
      ['Height', d.height_cm ? d.height_cm + ' cm' : '—'],
      ['Body Fat', d.body_fat_pct ? d.body_fat_pct + '%' : '—'],
    ]},
    { title: 'Goals', rows: [
      ['Primary Goal', d.goal_primary], ['Secondary', _fmt(d.goal_secondary)],
      ['Level', d.level],
    ]},
    { title: 'Training', rows: [
      ['Days / Week', d.training_days_per_week],
      ['Session Duration', d.session_duration_min ? d.session_duration_min + ' min' : '—'],
      ['Equipment', _fmt(d.equipment)],
      ['Likes', d.training_likes || '—'], ['Dislikes', d.training_dislikes || '—'],
    ]},
    { title: 'Health', rows: [
      ['Current Injuries', _fmt(d.injuries_current)],
      ['Injury History', _fmt(d.injuries_history)],
      ['Postural Issues', _fmt(d.postural_issues)],
      ['Mobility Issues', _fmt(d.mobility_issues)],
      ['Muscle Imbalances', _fmt(d.muscle_imbalances)],
    ]},
  ];
```

Replace with:

```js
  const sections = [
    { title: t('section_physical'), rows: [
      [t('field_name'), d.name], [t('field_gender'), d.gender], [t('field_age'), d.age],
      [t('field_weight_view'), d.weight_kg ? d.weight_kg + ' kg' : '—'],
      [t('field_height_view'), d.height_cm ? d.height_cm + ' cm' : '—'],
      [t('field_body_fat_view'), d.body_fat_pct ? d.body_fat_pct + '%' : '—'],
    ]},
    { title: t('section_goals'), rows: [
      [t('field_primary_goal'), d.goal_primary], [t('field_secondary'), _fmt(d.goal_secondary)],
      [t('field_level'), d.level],
    ]},
    { title: t('section_training'), rows: [
      [t('field_days_week'), d.training_days_per_week],
      [t('field_session_duration_view'), d.session_duration_min ? d.session_duration_min + ' min' : '—'],
      [t('field_equipment'), _fmt(d.equipment)],
      [t('field_likes'), d.training_likes || '—'], [t('field_dislikes'), d.training_dislikes || '—'],
    ]},
    { title: t('section_health'), rows: [
      [t('field_injuries_current'), _fmt(d.injuries_current)],
      [t('field_injuries_history'), _fmt(d.injuries_history)],
      [t('field_postural'), _fmt(d.postural_issues)],
      [t('field_mobility'), _fmt(d.mobility_issues)],
      [t('field_imbalances'), _fmt(d.muscle_imbalances)],
    ]},
    { title: t('field_language'), rows: [
      [t('field_language'), d.app_language === 'uk' ? t('lang_uk') : t('lang_en')],
    ]},
  ];
```

Find the cycle block:
```js
  if (d.menstrual_tracking) {
    sections.push({ title: 'Cycle', rows: [
      ['Cycle Length', d.cycle_length_days ? d.cycle_length_days + ' days' : '—'],
      ['Last Period', d.last_period_date || '—'],
    ]});
  }
```
Replace with:
```js
  if (d.menstrual_tracking) {
    sections.push({ title: t('section_cycle'), rows: [
      [t('field_cycle_length'), d.cycle_length_days ? d.cycle_length_days + ' days' : '—'],
      [t('field_last_period'), d.last_period_date || '—'],
    ]});
  }
```

Also update the `openProfile()` loading/error strings:

Find:
```js
    '<div style="color:var(--muted);font-size:13px;text-align:center;padding:20px">Loading...</div>';
```
Replace with:
```js
    `<div style="color:var(--muted);font-size:13px;text-align:center;padding:20px">${t('loading')}</div>`;
```

Find (openProfile error):
```js
      '<div class="error-msg">Failed to load profile</div>';
```
Replace with:
```js
      `<div class="error-msg">${t('failed_load_profile')}</div>`;
```

- [ ] **Step 4: Update toggleProfileEdit() with t() + language select**

Find the `fields` array in `toggleProfileEdit()`:

```js
  const fields = [
    { title: 'Physical', rows: [
      ['name','Name','text', d.name||''],
      ['age','Age','number', d.age||''],
      ['weight_kg','Weight (kg)','number', d.weight_kg||''],
      ['height_cm','Height (cm)','number', d.height_cm||''],
      ['body_fat_pct','Body Fat (%)','number', d.body_fat_pct||''],
    ]},
    { title: 'Goals', rows: [
      ['goal_primary','Primary Goal','text', d.goal_primary||''],
      ['training_days_per_week','Days / Week','number', d.training_days_per_week||''],
      ['session_duration_min','Session Duration (min)','number', d.session_duration_min||''],
    ]},
    { title: 'Health & Notes', rows: [
      ['training_likes','Training Likes','textarea', d.training_likes||''],
      ['training_dislikes','Training Dislikes','textarea', d.training_dislikes||''],
    ]},
  ];
```

Replace with:

```js
  const fields = [
    { title: t('section_physical'), rows: [
      ['name', t('field_name'), 'text', d.name||''],
      ['age', t('field_age'), 'number', d.age||''],
      ['weight_kg', t('field_weight'), 'number', d.weight_kg||''],
      ['height_cm', t('field_height'), 'number', d.height_cm||''],
      ['body_fat_pct', t('field_body_fat'), 'number', d.body_fat_pct||''],
    ]},
    { title: t('section_goals'), rows: [
      ['goal_primary', t('field_primary_goal'), 'text', d.goal_primary||''],
      ['training_days_per_week', t('field_days_week'), 'number', d.training_days_per_week||''],
      ['session_duration_min', t('field_session_duration'), 'number', d.session_duration_min||''],
    ]},
    { title: t('section_health'), rows: [
      ['training_likes', t('field_likes_edit'), 'textarea', d.training_likes||''],
      ['training_dislikes', t('field_dislikes_edit'), 'textarea', d.training_dislikes||''],
    ]},
  ];
```

Also update the `profile-edit-toggle` button text and the `profile-edit-bar` save/cancel button text in `toggleProfileEdit()`. Find:

```js
  document.getElementById('profile-edit-toggle').style.display = 'none';
  document.getElementById('profile-edit-bar').style.display = 'flex';
```

And the part that builds the innerHTML for fields — find after the fields array, the `document.getElementById('profile-body').innerHTML` assignment in toggleProfileEdit. After that assignment, add the language select **as a separate section** by appending to the existing rendered HTML:

Find (end of `toggleProfileEdit`, just before the closing `}`):

```js
  document.getElementById('profile-body').innerHTML = fields.map(s => `
    <div class="profile-section">
      <div class="profile-section-title">${s.title}</div>
      ${s.rows.map(([key, label, type, val]) => `
        <div class="profile-row" style="flex-direction:column;align-items:stretch;gap:6px">
          <span class="profile-row-label">${label}</span>
          ${type === 'textarea'
            ? `<textarea data-field="${key}">${_esc(val)}</textarea>`
            : `<input type="${type}" data-field="${key}" value="${_esc(val)}">`
          }
        </div>`).join('')}
    </div>`).join('');
}
```

Replace with:

```js
  const curLang = d.app_language || 'en';
  document.getElementById('profile-body').innerHTML = fields.map(s => `
    <div class="profile-section">
      <div class="profile-section-title">${s.title}</div>
      ${s.rows.map(([key, label, type, val]) => `
        <div class="profile-row" style="flex-direction:column;align-items:stretch;gap:6px">
          <span class="profile-row-label">${label}</span>
          ${type === 'textarea'
            ? `<textarea data-field="${key}">${_esc(val)}</textarea>`
            : `<input type="${type}" data-field="${key}" value="${_esc(val)}">`
          }
        </div>`).join('')}
    </div>`).join('') + `
    <div class="profile-section">
      <div class="profile-section-title">${t('field_language')}</div>
      <div class="profile-row" style="flex-direction:column;align-items:stretch;gap:6px">
        <span class="profile-row-label">${t('field_language')}</span>
        <select data-field="app_language">
          <option value="en" ${curLang === 'en' ? 'selected' : ''}>${t('lang_en')}</option>
          <option value="uk" ${curLang === 'uk' ? 'selected' : ''}>${t('lang_uk')}</option>
        </select>
      </div>
    </div>`;
}
```

Also update `renderProfileView()` profile-edit-toggle button to use `t('edit')` and save/cancel in the static HTML. Find the edit toggle button in `renderProfileView()`:

```js
  document.getElementById('profile-edit-toggle').textContent = 'EDIT';
```
Replace with:
```js
  document.getElementById('profile-edit-toggle').textContent = t('edit');
```

Update the save/cancel button text by calling `applyTranslations()` at the end of `renderProfileView()` — add this line before the closing `}`:

```js
  applyTranslations();
```

Also update the `saveProfile()` saving and save_failed strings. Find:

```js
  msg.innerHTML = '<div style="color:var(--muted);font-size:13px;text-align:center">Saving...</div>';
```
Replace with:
```js
  msg.innerHTML = `<div style="color:var(--muted);font-size:13px;text-align:center">${t('saving')}</div>`;
```

Find (in saveProfile error handler):
```js
    errDiv.textContent = r.error?.message || 'Save failed';
```
Replace with:
```js
    errDiv.textContent = r.error?.message || t('save_failed');
```

- [ ] **Step 5: Run full test suite**

```bash
cd /Users/natalie/body-coach-ai && pytest -v
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
cd /Users/natalie/body-coach-ai && git add app/templates/index.html && git commit -m "feat: apply i18n t() throughout UI and add language selector to profile edit"
```

---

## Task 5: Deploy

**Files:** none (push triggers GitHub Actions)

- [ ] **Step 1: Push to main**

```bash
cd /Users/natalie/body-coach-ai && git push origin main
```

- [ ] **Step 2: Monitor deploy**

```bash
gh run watch $(gh run list --limit 1 --json databaseId -q '.[0].databaseId')
```
Expected: `✓ deploy` in ~45s

- [ ] **Step 3: Smoke test**

In the app:
- Open Program tab → insights should be hidden, "SHOW INSIGHTS" button visible
- Tap "SHOW INSIGHTS" → insights expand, button changes to "HIDE INSIGHTS"
- Open Profile → tap EDIT → Language field shows EN/UK select
- Change to Українська → tap SAVE → nav tabs and UI switch to Ukrainian
