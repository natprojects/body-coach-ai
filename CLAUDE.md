# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Body Coach AI — Telegram Mini App з AI-тренером на базі Anthropic API.
Платформа з модульною архітектурою: **Training, Nutrition, Sleep, Psychology**.
Зараз реалізовано: фундамент + Training модуль.

## Stack

- **Backend:** Python Flask + SQLite (via SQLAlchemy)
- **AI:** Anthropic API (Claude)
- **Frontend:** Telegram Mini App (Web App API)
- **Auth:** Telegram WebApp `initData` validation

## Architecture Principle

**Universal foundation з першого дня.** Нові модулі (Nutrition, Sleep, Psychology) мають підключатися без рефакторингу існуючого коду. Кожен модуль — ізольований, реєструється через Blueprint і власну схему БД.

```
body-coach-ai/
├── app/
│   ├── __init__.py          # Flask app factory, реєстрація blueprints
│   ├── core/                # Спільна інфраструктура (auth, db, ai client)
│   │   ├── auth.py          # Telegram initData validation
│   │   ├── ai.py            # Anthropic client wrapper
│   │   └── models.py        # Base models (User)
│   └── modules/
│       └── training/        # Training модуль (перший)
│           ├── __init__.py  # Blueprint registration
│           ├── models.py    # Training-specific DB models
│           ├── routes.py    # API endpoints
│           └── ai_coach.py  # Training AI logic
├── migrations/              # DB міграції
├── config.py                # Конфіг (env vars)
├── run.py                   # Entry point
└── requirements.txt
```

### Додавання нового модуля

Щоб додати модуль (наприклад, Nutrition):
1. Створити `app/modules/nutrition/` з тією ж структурою
2. Зареєструвати Blueprint у `app/__init__.py`
3. Нових залежностей у core не потрібно

## Commands

```bash
# Встановлення залежностей
pip install -r requirements.txt

# Запуск dev-сервера
python run.py

# Запуск тестів
pytest

# Запуск одного тесту
pytest tests/test_training.py::test_name -v

# Міграції БД
flask db init
flask db migrate -m "description"
flask db upgrade
```

## Environment Variables

```
ANTHROPIC_API_KEY=
TELEGRAM_BOT_TOKEN=      # для валідації initData
DATABASE_URL=sqlite:///body_coach.db
FLASK_ENV=development
```

## AI Integration

Anthropic API використовується через єдиний wrapper у `app/core/ai.py`. Кожен модуль передає свій системний промпт і контекст користувача — логіка AI ізольована всередині модуля, core лише надає клієнт.

## Key Constraints

- SQLite для простоти (легко мігрувати на Postgres пізніше)
- Telegram Mini App — вся авторизація через `initData`, без окремої системи логіну
- Відповіді AI стрімляться там, де це підтримує Telegram Web App API
