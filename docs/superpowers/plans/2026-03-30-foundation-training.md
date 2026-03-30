# Foundation + Training Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Flask foundation and Training module for Body Coach AI — a Telegram Mini App with AI personal coaching.

**Architecture:** Blueprint-per-module with a shared core (auth, AI client, conversation memory). All modules read from the same `users` table. AI context = structured system prompt (user profile + module context) + rolling conversation window (15 messages) stored in `ai_conversations`.

**Tech Stack:** Python 3.11+, Flask 3.x, SQLAlchemy + Flask-Migrate (SQLite), Anthropic Python SDK, PyJWT, pytest + pytest-flask.

---

## File Map

**Created from scratch:**
```
requirements.txt
run.py
app/__init__.py                          # app factory, error handlers
app/config.py                            # Config, TestConfig
app/extensions.py                        # db, migrate singletons

app/core/auth.py                         # Telegram initData validation, JWT, require_auth decorator
app/core/conversation.py                 # save_message(), load_conversation_window()
app/core/ai.py                           # get_client(), build_base_system(), stream_chat(), complete()
app/core/models.py                       # User, BodyMeasurement, InjuryDetail, DailyCheckin, PainJournal, AIConversation
app/core/routes.py                       # /api/auth/validate, /api/checkin, /api/pain, /api/measurements

app/modules/training/__init__.py         # Blueprint
app/modules/training/models.py           # Program, Mesocycle, ProgramWeek, Workout, Exercise,
                                         # WorkoutExercise, PlannedSet, WorkoutSession, LoggedExercise, LoggedSet
app/modules/training/routes.py           # All /api/training/* and /api/onboarding/* endpoints
app/modules/training/onboarding.py       # Step definitions, step handlers, next_step logic
app/modules/training/coach.py            # build_training_context(), generate_program(), save_program_from_dict()
app/modules/training/progress.py         # generate_post_workout_feedback(), generate_weekly_report()

tests/conftest.py                        # app, client, db, mock_anthropic fixtures
tests/core/test_auth.py
tests/core/test_conversation.py
tests/training/test_onboarding.py
tests/training/test_program.py
tests/training/test_session.py
tests/training/test_coach.py
```

---

## Task 1: Bootstrap

**Files:**
- Create: `requirements.txt`
- Create: `run.py`
- Create: `app/config.py`
- Create: `app/extensions.py`
- Create: `app/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create requirements.txt**

```
flask>=3.0.0
flask-sqlalchemy>=3.1.0
flask-migrate>=4.0.0
anthropic>=0.40.0
PyJWT>=2.8.0
pytest>=8.0.0
pytest-flask>=1.3.0
```

- [ ] **Step 2: Create app/config.py**

```python
import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///body_coach.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    AI_MODEL = 'claude-opus-4-6'
    CONVERSATION_WINDOW_SIZE = 15

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    TELEGRAM_BOT_TOKEN = 'test-bot-token-1234567890'
    SECRET_KEY = 'test-secret'
```

- [ ] **Step 3: Create app/extensions.py**

```python
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()
```

- [ ] **Step 4: Create app/__init__.py**

```python
from flask import Flask, jsonify
from .config import Config
from .extensions import db, migrate


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)

    from .core.routes import bp as core_bp
    app.register_blueprint(core_bp, url_prefix='/api')

    from .modules.training import bp as training_bp
    app.register_blueprint(training_bp, url_prefix='/api')

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({'success': False, 'error': {'code': 'BAD_REQUEST', 'message': str(e)}}), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({'success': False, 'error': {'code': 'UNAUTHORIZED', 'message': str(e)}}), 401

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': str(e)}}), 404

    @app.errorhandler(Exception)
    def handle_exception(e):
        app.logger.error(f"Unhandled exception: {e}", exc_info=True)
        return jsonify({'success': False, 'error': {'code': 'INTERNAL_ERROR', 'message': 'Internal server error'}}), 500

    return app
```

- [ ] **Step 5: Create run.py**

```python
from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, port=5000)
```

- [ ] **Step 6: Create tests/conftest.py**

```python
import pytest
from unittest.mock import MagicMock, patch
from app import create_app
from app.config import TestConfig
from app.extensions import db as _db


@pytest.fixture(scope='function')
def app():
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def mock_anthropic():
    mock_client = MagicMock()
    with patch('app.core.ai.get_client', return_value=mock_client):
        yield mock_client
```

- [ ] **Step 7: Install dependencies**

```bash
pip install -r requirements.txt
```

- [ ] **Step 8: Verify app starts**

```bash
python run.py
```
Expected: Flask dev server starts on port 5000 with no import errors.

- [ ] **Step 9: Commit**

```bash
git add requirements.txt run.py app/__init__.py app/config.py app/extensions.py tests/conftest.py
git commit -m "feat: bootstrap Flask app factory with config and extensions"
```

---

## Task 2: Core Models

**Files:**
- Create: `app/core/__init__.py`
- Create: `app/core/models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_models.py
def test_user_creation(db, app):
    from app.core.models import User
    user = User(telegram_id=123456789)
    db.session.add(user)
    db.session.commit()
    assert user.id is not None
    assert user.telegram_id == 123456789
    assert user.onboarding_completed_at is None

def test_daily_checkin(db, app):
    from app.core.models import User, DailyCheckin
    from datetime import date
    user = User(telegram_id=111111)
    db.session.add(user)
    db.session.commit()
    checkin = DailyCheckin(
        user_id=user.id, date=date.today(),
        energy_level=7, sleep_quality=6, stress_level=4,
        motivation=8, soreness_level=3
    )
    db.session.add(checkin)
    db.session.commit()
    assert checkin.id is not None

def test_ai_conversation_module_isolation(db, app):
    from app.core.models import User, AIConversation
    user = User(telegram_id=222222)
    db.session.add(user)
    db.session.commit()
    msg = AIConversation(user_id=user.id, module='training', role='user', content='test')
    db.session.add(msg)
    db.session.commit()
    results = AIConversation.query.filter_by(user_id=user.id, module='nutrition').all()
    assert results == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/core/test_models.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.models'`

- [ ] **Step 3: Create app/core/__init__.py**

```python
```
(empty file)

- [ ] **Step 4: Create app/core/models.py**

```python
from datetime import datetime, date
from app.extensions import db


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    telegram_id = db.Column(db.BigInteger, unique=True, nullable=False)
    name = db.Column(db.String(200))
    gender = db.Column(db.String(20))
    age = db.Column(db.Integer)
    weight_kg = db.Column(db.Float)
    height_cm = db.Column(db.Float)
    body_fat_pct = db.Column(db.Float)
    goal_primary = db.Column(db.String(50))
    goal_secondary = db.Column(db.JSON)
    level = db.Column(db.String(20))
    training_days_per_week = db.Column(db.Integer)
    session_duration_min = db.Column(db.Integer)
    equipment = db.Column(db.JSON)
    injuries_current = db.Column(db.JSON)
    injuries_history = db.Column(db.JSON)
    postural_issues = db.Column(db.JSON)
    mobility_issues = db.Column(db.JSON)
    muscle_imbalances = db.Column(db.JSON)
    menstrual_tracking = db.Column(db.Boolean, default=False)
    cycle_length_days = db.Column(db.Integer)
    last_period_date = db.Column(db.Date)
    training_likes = db.Column(db.Text)
    training_dislikes = db.Column(db.Text)
    previous_methods = db.Column(db.JSON)
    had_coach_before = db.Column(db.Boolean)
    motivation_type = db.Column(db.String(20))
    onboarding_completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BodyMeasurement(db.Model):
    __tablename__ = 'body_measurements'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    weight_kg = db.Column(db.Float)
    body_fat_pct = db.Column(db.Float)
    waist_cm = db.Column(db.Float)
    hips_cm = db.Column(db.Float)
    chest_cm = db.Column(db.Float)
    left_arm_cm = db.Column(db.Float)
    right_arm_cm = db.Column(db.Float)
    left_leg_cm = db.Column(db.Float)
    right_leg_cm = db.Column(db.Float)


class InjuryDetail(db.Model):
    __tablename__ = 'injury_details'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    body_part = db.Column(db.String(100), nullable=False)
    side = db.Column(db.String(20))  # left / right / bilateral
    description = db.Column(db.Text)
    aggravating_factors = db.Column(db.Text)
    diagnosis = db.Column(db.Text)
    saw_doctor = db.Column(db.Boolean, default=False)
    is_current = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DailyCheckin(db.Model):
    __tablename__ = 'daily_checkins'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    energy_level = db.Column(db.Integer)
    sleep_quality = db.Column(db.Integer)
    stress_level = db.Column(db.Integer)
    motivation = db.Column(db.Integer)
    soreness_level = db.Column(db.Integer)
    body_weight_kg = db.Column(db.Float)
    cycle_day = db.Column(db.Integer)
    notes = db.Column(db.Text)


class PainJournal(db.Model):
    __tablename__ = 'pain_journal'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    body_part = db.Column(db.String(100), nullable=False)
    pain_type = db.Column(db.String(20))  # sharp / dull / aching / burning
    intensity = db.Column(db.Integer)
    when_occurs = db.Column(db.String(20))  # during / after / morning / always
    related_exercise_id = db.Column(db.Integer, db.ForeignKey('exercises.id'), nullable=True)
    notes = db.Column(db.Text)


class AIConversation(db.Model):
    __tablename__ = 'ai_conversations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    module = db.Column(db.String(50), nullable=False)  # training / nutrition / sleep / psychology
    role = db.Column(db.String(20), nullable=False)    # user / assistant
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

> Note: `PainJournal.related_exercise_id` references `exercises.id` which is in the Training module. SQLite doesn't enforce FK order at creation time so this is safe for SQLite. For production Postgres, ensure exercises table is created first.

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/core/test_models.py -v
```
Expected: 3 PASS

- [ ] **Step 6: Commit**

```bash
git add app/core/__init__.py app/core/models.py tests/core/test_models.py
git commit -m "feat: add core shared models (User, DailyCheckin, PainJournal, AIConversation)"
```

---

## Task 3: Auth — Telegram initData Validation + JWT

**Files:**
- Create: `app/core/auth.py`
- Test: `tests/core/test_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_auth.py
import hashlib
import hmac
import json
import urllib.parse
import pytest
from app.core.auth import validate_telegram_init_data, create_jwt, decode_jwt

BOT_TOKEN = 'test-bot-token-1234567890'

def _make_init_data(bot_token=BOT_TOKEN, telegram_id=123456, extra_params=None):
    user_json = json.dumps({"id": telegram_id, "first_name": "Natalie"})
    params = {"user": user_json, "auth_date": "1700000000"}
    if extra_params:
        params.update(extra_params)
    data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
    hash_val = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    params['hash'] = hash_val
    return urllib.parse.urlencode(params)

def test_valid_init_data():
    result = validate_telegram_init_data(_make_init_data(), BOT_TOKEN)
    assert result['auth_date'] == '1700000000'
    assert 'Natalie' in result['user']

def test_tampered_hash_raises():
    init_data = _make_init_data()
    tampered = init_data[:-5] + 'aaaaa'
    with pytest.raises(ValueError, match="Invalid hash"):
        validate_telegram_init_data(tampered, BOT_TOKEN)

def test_wrong_bot_token_raises():
    init_data = _make_init_data(bot_token=BOT_TOKEN)
    with pytest.raises(ValueError, match="Invalid hash"):
        validate_telegram_init_data(init_data, 'wrong-token')

def test_create_and_decode_jwt():
    token = create_jwt(42, 'my-secret')
    payload = decode_jwt(token, 'my-secret')
    assert payload['user_id'] == 42

def test_require_auth_missing_token(client):
    resp = client.get('/api/checkin/today')
    assert resp.status_code == 401

def test_require_auth_invalid_token(client):
    resp = client.get('/api/checkin/today', headers={'Authorization': 'Bearer bad.token.here'})
    assert resp.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/core/test_auth.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.auth'`

- [ ] **Step 3: Create app/core/auth.py**

```python
import hashlib
import hmac
import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request

from app.extensions import db
from app.core.models import User


def validate_telegram_init_data(init_data: str, bot_token: str) -> dict:
    parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop('hash', '')
    data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed_hash, received_hash):
        raise ValueError("Invalid hash")
    return parsed


def create_jwt(user_id: int, secret_key: str) -> str:
    payload = {
        'user_id': user_id,
        'exp': datetime.now(timezone.utc) + timedelta(days=30),
    }
    return jwt.encode(payload, secret_key, algorithm='HS256')


def decode_jwt(token: str, secret_key: str) -> dict:
    return jwt.decode(token, secret_key, algorithms=['HS256'])


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': {'code': 'UNAUTHORIZED', 'message': 'Missing token'}}), 401
        token = auth_header[7:]
        try:
            payload = decode_jwt(token, current_app.config['SECRET_KEY'])
            g.user_id = payload['user_id']
        except jwt.ExpiredSignatureError:
            return jsonify({'success': False, 'error': {'code': 'TOKEN_EXPIRED', 'message': 'Token expired'}}), 401
        except jwt.InvalidTokenError:
            return jsonify({'success': False, 'error': {'code': 'INVALID_TOKEN', 'message': 'Invalid token'}}), 401
        return f(*args, **kwargs)
    return decorated


def get_or_create_user(telegram_id: int) -> User:
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)
        db.session.add(user)
        db.session.commit()
    return user
```

- [ ] **Step 4: Create app/core/routes.py (stub — enough for auth tests to pass)**

```python
from flask import Blueprint, g, jsonify, request
from app.core.auth import require_auth

bp = Blueprint('core', __name__)


@bp.route('/checkin/today', methods=['GET'])
@require_auth
def get_checkin_today():
    return jsonify({'success': True, 'data': None})
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/core/test_auth.py -v
```
Expected: 6 PASS

- [ ] **Step 6: Commit**

```bash
git add app/core/auth.py app/core/routes.py tests/core/test_auth.py
git commit -m "feat: add Telegram initData validation, JWT auth, require_auth decorator"
```

---

## Task 4: Conversation Module

**Files:**
- Create: `app/core/conversation.py`
- Test: `tests/core/test_conversation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_conversation.py
import pytest
from app.core.models import User
from app.core.conversation import save_message, load_conversation_window


def _make_user(db, telegram_id):
    user = User(telegram_id=telegram_id)
    db.session.add(user)
    db.session.commit()
    return user


def test_save_and_load(db, app):
    user = _make_user(db, 10001)
    save_message(user.id, 'training', 'user', 'Hello coach')
    save_message(user.id, 'training', 'assistant', 'Hello! Ready to train?')
    window = load_conversation_window(user.id, 'training')
    assert len(window) == 2
    assert window[0] == {'role': 'user', 'content': 'Hello coach'}
    assert window[1] == {'role': 'assistant', 'content': 'Hello! Ready to train?'}


def test_module_isolation(db, app):
    user = _make_user(db, 10002)
    save_message(user.id, 'training', 'user', 'Training msg')
    save_message(user.id, 'nutrition', 'user', 'Nutrition msg')
    training = load_conversation_window(user.id, 'training')
    nutrition = load_conversation_window(user.id, 'nutrition')
    assert len(training) == 1
    assert training[0]['content'] == 'Training msg'
    assert len(nutrition) == 1
    assert nutrition[0]['content'] == 'Nutrition msg'


def test_window_limit(db, app):
    user = _make_user(db, 10003)
    for i in range(20):
        save_message(user.id, 'training', 'user', f'msg {i}')
    window = load_conversation_window(user.id, 'training', limit=15)
    assert len(window) == 15
    # most recent 15 messages
    assert window[-1]['content'] == 'msg 19'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/core/test_conversation.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.conversation'`

- [ ] **Step 3: Create app/core/conversation.py**

```python
from app.extensions import db
from app.core.models import AIConversation


def save_message(user_id: int, module: str, role: str, content: str) -> None:
    msg = AIConversation(user_id=user_id, module=module, role=role, content=content)
    db.session.add(msg)
    db.session.commit()


def load_conversation_window(user_id: int, module: str, limit: int = 15) -> list[dict]:
    messages = (
        AIConversation.query
        .filter_by(user_id=user_id, module=module)
        .filter(AIConversation.role.in_(['user', 'assistant']))
        .order_by(AIConversation.created_at.desc())
        .limit(limit)
        .all()
    )
    return [{'role': m.role, 'content': m.content} for m in reversed(messages)]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/core/test_conversation.py -v
```
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/conversation.py tests/core/test_conversation.py
git commit -m "feat: add conversation window save/load with module isolation"
```

---

## Task 5: AI Client

**Files:**
- Create: `app/core/ai.py`
- Test: `tests/core/test_ai.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_ai.py
from unittest.mock import MagicMock, patch
from app.core.models import User, DailyCheckin
from datetime import date


def _make_user(db):
    user = User(
        telegram_id=20001, name='Natalie', gender='female', age=28,
        weight_kg=60.0, height_cm=165.0,
        goal_primary='hypertrophy', level='intermediate',
        equipment=['full_gym'],
    )
    db.session.add(user)
    db.session.commit()
    return user


def test_build_base_system_contains_user_data(db, app):
    from app.core.ai import build_base_system
    user = _make_user(db)
    system = build_base_system(user.id)
    assert 'Natalie' in system
    assert 'hypertrophy' in system
    assert 'intermediate' in system


def test_build_base_system_includes_checkin(db, app):
    from app.core.ai import build_base_system
    user = _make_user(db)
    checkin = DailyCheckin(
        user_id=user.id, date=date.today(),
        energy_level=8, sleep_quality=7, stress_level=3,
        motivation=9, soreness_level=2
    )
    db.session.add(checkin)
    db.session.commit()
    system = build_base_system(user.id)
    assert 'Energy: 8' in system


def test_stream_chat_saves_messages(db, app, mock_anthropic):
    from app.core.ai import stream_chat
    from app.core.models import AIConversation
    user = _make_user(db)

    # Mock streaming response
    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.text_stream = iter(['Hello', ' there', '!'])
    mock_anthropic.messages.stream.return_value = mock_stream

    chunks = list(stream_chat(user.id, 'training', 'What should I train today?'))
    assert chunks == ['Hello', ' there', '!']

    msgs = AIConversation.query.filter_by(user_id=user.id, module='training').all()
    assert len(msgs) == 2
    assert msgs[0].role == 'user'
    assert msgs[1].role == 'assistant'
    assert msgs[1].content == 'Hello there!'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/core/test_ai.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.ai'`

- [ ] **Step 3: Create app/core/ai.py**

```python
import anthropic
from datetime import date
from flask import current_app

from app.core.conversation import load_conversation_window, save_message
from app.core.models import DailyCheckin, User

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=current_app.config['ANTHROPIC_API_KEY'])
    return _client


def build_base_system(user_id: int) -> str:
    user = db_get_user(user_id)
    parts = [
        "You are a professional AI body coach — personal, evidence-based, and motivating.",
        "\n## User Profile",
        f"Name: {user.name}, Gender: {user.gender}, Age: {user.age}",
        f"Weight: {user.weight_kg}kg, Height: {user.height_cm}cm"
        + (f", Body fat: {user.body_fat_pct}%" if user.body_fat_pct else ""),
        f"Primary goal: {user.goal_primary}, Level: {user.level}",
        f"Training: {user.training_days_per_week} days/week, {user.session_duration_min} min/session",
        f"Equipment: {user.equipment}",
    ]
    if user.injuries_current:
        parts.append(f"Current injuries: {user.injuries_current}")
    if user.postural_issues:
        parts.append(f"Postural issues: {user.postural_issues}")
    if user.mobility_issues:
        parts.append(f"Mobility restrictions: {user.mobility_issues}")

    checkin = DailyCheckin.query.filter_by(user_id=user_id, date=date.today()).first()
    if checkin:
        parts += [
            "\n## Today's Check-in",
            f"Energy: {checkin.energy_level}/10, Sleep: {checkin.sleep_quality}/10",
            f"Stress: {checkin.stress_level}/10, Motivation: {checkin.motivation}/10",
            f"Soreness: {checkin.soreness_level}/10",
        ]
        if checkin.notes:
            parts.append(f"Notes: {checkin.notes}")

    return '\n'.join(parts)


def db_get_user(user_id: int) -> User:
    return User.query.get(user_id)


def stream_chat(user_id: int, module: str, user_message: str, extra_context: str = ""):
    """Generator that yields text chunks. Saves messages to conversation history."""
    system = build_base_system(user_id)
    if extra_context:
        system += f"\n\n{extra_context}"

    window_size = current_app.config.get('CONVERSATION_WINDOW_SIZE', 15)
    history = load_conversation_window(user_id, module, limit=window_size)
    messages = history + [{"role": "user", "content": user_message}]

    save_message(user_id, module, 'user', user_message)

    full_response = []
    with get_client().messages.stream(
        model=current_app.config['AI_MODEL'],
        max_tokens=2048,
        system=system,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            full_response.append(text)
            yield text

    save_message(user_id, module, 'assistant', ''.join(full_response))


def complete(system_prompt: str, user_message: str, max_tokens: int = 4096) -> str:
    """Non-streaming completion for structured outputs (program gen, reports)."""
    response = get_client().messages.create(
        model=current_app.config['AI_MODEL'],
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/core/test_ai.py -v
```
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/ai.py tests/core/test_ai.py
git commit -m "feat: add Anthropic AI client with streaming and conversation memory"
```

---

## Task 6: Core Routes (auth, checkin, pain, measurements)

**Files:**
- Modify: `app/core/routes.py`
- Test: `tests/core/test_core_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_core_routes.py
import json
import hashlib
import hmac
import urllib.parse
from datetime import date
from app.core.models import User, DailyCheckin, PainJournal, BodyMeasurement
from app.core.auth import create_jwt


def _auth_header(app, user_id):
    token = create_jwt(user_id, app.config['SECRET_KEY'])
    return {'Authorization': f'Bearer {token}'}


def _make_init_data(bot_token, telegram_id=123456):
    user_json = json.dumps({"id": telegram_id, "first_name": "Natalie"})
    params = {"user": user_json, "auth_date": "1700000000"}
    data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
    params['hash'] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(params)


def test_auth_validate_creates_user(client, app, db):
    init_data = _make_init_data(app.config['TELEGRAM_BOT_TOKEN'])
    resp = client.post('/api/auth/validate', json={'init_data': init_data})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert 'token' in data['data']
    assert User.query.filter_by(telegram_id=123456).first() is not None


def test_auth_validate_invalid(client):
    resp = client.post('/api/auth/validate', json={'init_data': 'bad=data&hash=wrong'})
    assert resp.status_code == 401


def test_create_checkin(client, app, db):
    user = User(telegram_id=30001)
    db.session.add(user)
    db.session.commit()
    resp = client.post('/api/checkin', json={
        'energy_level': 7, 'sleep_quality': 6, 'stress_level': 4,
        'motivation': 8, 'soreness_level': 3
    }, headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    assert DailyCheckin.query.filter_by(user_id=user.id).count() == 1


def test_get_checkin_today(client, app, db):
    user = User(telegram_id=30002)
    db.session.add(user)
    db.session.commit()
    checkin = DailyCheckin(user_id=user.id, date=date.today(), energy_level=9, sleep_quality=8,
                           stress_level=2, motivation=10, soreness_level=1)
    db.session.add(checkin)
    db.session.commit()
    resp = client.get('/api/checkin/today', headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    assert resp.get_json()['data']['energy_level'] == 9


def test_create_pain_entry(client, app, db):
    user = User(telegram_id=30003)
    db.session.add(user)
    db.session.commit()
    resp = client.post('/api/pain', json={
        'body_part': 'left knee', 'pain_type': 'sharp',
        'intensity': 6, 'when_occurs': 'during'
    }, headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    assert PainJournal.query.filter_by(user_id=user.id).count() == 1


def test_create_measurement(client, app, db):
    user = User(telegram_id=30004)
    db.session.add(user)
    db.session.commit()
    resp = client.post('/api/measurements', json={
        'weight_kg': 62.5, 'waist_cm': 72.0, 'hips_cm': 95.0
    }, headers=_auth_header(app, user.id))
    assert resp.status_code == 200
    assert BodyMeasurement.query.filter_by(user_id=user.id).count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/core/test_core_routes.py -v
```
Expected: FAIL — routes don't exist yet

- [ ] **Step 3: Replace app/core/routes.py with full implementation**

```python
from datetime import date, datetime
from flask import Blueprint, g, jsonify, request
from app.core.auth import (
    create_jwt, get_or_create_user, require_auth, validate_telegram_init_data
)
from app.core.models import BodyMeasurement, DailyCheckin, PainJournal
from app.extensions import db
from flask import current_app

bp = Blueprint('core', __name__)


@bp.route('/auth/validate', methods=['POST'])
def auth_validate():
    init_data = request.json.get('init_data', '')
    try:
        parsed = validate_telegram_init_data(init_data, current_app.config['TELEGRAM_BOT_TOKEN'])
    except ValueError:
        return jsonify({'success': False, 'error': {'code': 'UNAUTHORIZED', 'message': 'Invalid Telegram data'}}), 401

    import json
    user_info = json.loads(parsed.get('user', '{}'))
    telegram_id = user_info.get('id')
    if not telegram_id:
        return jsonify({'success': False, 'error': {'code': 'BAD_REQUEST', 'message': 'Missing user id'}}), 400

    user = get_or_create_user(telegram_id)
    if user_info.get('first_name') and not user.name:
        user.name = user_info['first_name']
        db.session.commit()

    token = create_jwt(user.id, current_app.config['SECRET_KEY'])
    return jsonify({'success': True, 'data': {
        'token': token,
        'user_id': user.id,
        'onboarding_completed': user.onboarding_completed_at is not None,
    }})


@bp.route('/checkin', methods=['POST'])
@require_auth
def create_checkin():
    data = request.json or {}
    checkin = DailyCheckin(
        user_id=g.user_id,
        date=date.today(),
        energy_level=data.get('energy_level'),
        sleep_quality=data.get('sleep_quality'),
        stress_level=data.get('stress_level'),
        motivation=data.get('motivation'),
        soreness_level=data.get('soreness_level'),
        body_weight_kg=data.get('body_weight_kg'),
        cycle_day=data.get('cycle_day'),
        notes=data.get('notes'),
    )
    db.session.add(checkin)
    db.session.commit()
    return jsonify({'success': True, 'data': {'id': checkin.id}})


@bp.route('/checkin/today', methods=['GET'])
@require_auth
def get_checkin_today():
    checkin = DailyCheckin.query.filter_by(user_id=g.user_id, date=date.today()).first()
    if not checkin:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': {
        'id': checkin.id,
        'date': checkin.date.isoformat(),
        'energy_level': checkin.energy_level,
        'sleep_quality': checkin.sleep_quality,
        'stress_level': checkin.stress_level,
        'motivation': checkin.motivation,
        'soreness_level': checkin.soreness_level,
        'body_weight_kg': checkin.body_weight_kg,
        'cycle_day': checkin.cycle_day,
        'notes': checkin.notes,
    }})


@bp.route('/pain', methods=['POST'])
@require_auth
def create_pain():
    data = request.json or {}
    entry = PainJournal(
        user_id=g.user_id,
        date=date.today(),
        body_part=data.get('body_part', ''),
        pain_type=data.get('pain_type'),
        intensity=data.get('intensity'),
        when_occurs=data.get('when_occurs'),
        notes=data.get('notes'),
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({'success': True, 'data': {'id': entry.id}})


@bp.route('/pain/recent', methods=['GET'])
@require_auth
def get_pain_recent():
    from datetime import timedelta
    since = date.today() - timedelta(days=30)
    entries = PainJournal.query.filter(
        PainJournal.user_id == g.user_id,
        PainJournal.date >= since
    ).order_by(PainJournal.date.desc()).all()
    return jsonify({'success': True, 'data': [{
        'id': e.id, 'date': e.date.isoformat(), 'body_part': e.body_part,
        'pain_type': e.pain_type, 'intensity': e.intensity,
        'when_occurs': e.when_occurs, 'notes': e.notes,
    } for e in entries]})


@bp.route('/measurements', methods=['POST'])
@require_auth
def create_measurement():
    data = request.json or {}
    m = BodyMeasurement(
        user_id=g.user_id,
        date=date.today(),
        weight_kg=data.get('weight_kg'),
        body_fat_pct=data.get('body_fat_pct'),
        waist_cm=data.get('waist_cm'),
        hips_cm=data.get('hips_cm'),
        chest_cm=data.get('chest_cm'),
        left_arm_cm=data.get('left_arm_cm'),
        right_arm_cm=data.get('right_arm_cm'),
        left_leg_cm=data.get('left_leg_cm'),
        right_leg_cm=data.get('right_leg_cm'),
    )
    db.session.add(m)
    db.session.commit()
    return jsonify({'success': True, 'data': {'id': m.id}})


@bp.route('/measurements/history', methods=['GET'])
@require_auth
def get_measurements_history():
    entries = BodyMeasurement.query.filter_by(user_id=g.user_id).order_by(BodyMeasurement.date.desc()).all()
    return jsonify({'success': True, 'data': [{
        'id': e.id, 'date': e.date.isoformat(),
        'weight_kg': e.weight_kg, 'body_fat_pct': e.body_fat_pct,
        'waist_cm': e.waist_cm, 'hips_cm': e.hips_cm,
        'chest_cm': e.chest_cm,
        'left_arm_cm': e.left_arm_cm, 'right_arm_cm': e.right_arm_cm,
        'left_leg_cm': e.left_leg_cm, 'right_leg_cm': e.right_leg_cm,
    } for e in entries]})
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/core/test_core_routes.py -v
```
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/routes.py tests/core/test_core_routes.py
git commit -m "feat: add core routes — auth, daily checkin, pain journal, measurements"
```

---

## Task 7: Training Models

**Files:**
- Create: `app/modules/__init__.py`
- Create: `app/modules/training/__init__.py`
- Create: `app/modules/training/models.py`
- Test: `tests/training/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/training/test_models.py
def test_program_mesocycle_hierarchy(db, app):
    from app.core.models import User
    from app.modules.training.models import (
        Exercise, LoggedExercise, LoggedSet, Mesocycle,
        PlannedSet, Program, ProgramWeek, Workout, WorkoutExercise, WorkoutSession
    )
    from datetime import date

    user = User(telegram_id=40001)
    db.session.add(user)
    db.session.commit()

    program = Program(user_id=user.id, name='4-Week Hypertrophy', periodization_type='block', total_weeks=4)
    db.session.add(program)
    db.session.commit()

    meso = Mesocycle(program_id=program.id, name='Accumulation', order_index=0, weeks_count=3)
    db.session.add(meso)
    db.session.commit()

    week = ProgramWeek(mesocycle_id=meso.id, week_number=1)
    db.session.add(week)
    db.session.commit()

    workout = Workout(program_week_id=week.id, day_of_week=0, name='Upper Body A', order_index=0)
    db.session.add(workout)
    db.session.commit()

    exercise = Exercise(name='Bench Press', muscle_group='chest', equipment_needed='barbell',
                        contraindication_severity='none', is_corrective=False, is_prehab=False)
    db.session.add(exercise)
    db.session.commit()

    we = WorkoutExercise(workout_id=workout.id, exercise_id=exercise.id, order_index=0)
    db.session.add(we)
    db.session.commit()

    ps = PlannedSet(workout_exercise_id=we.id, set_number=1,
                    target_reps='8-10', target_weight_kg=60.0, target_rpe=7.0, rest_seconds=120)
    db.session.add(ps)
    db.session.commit()

    # Verify hierarchy via relationships
    assert len(program.mesocycles) == 1
    assert len(program.mesocycles[0].weeks) == 1
    assert len(program.mesocycles[0].weeks[0].workouts) == 1

    # Session logging
    session = WorkoutSession(user_id=user.id, workout_id=workout.id, date=date.today())
    db.session.add(session)
    db.session.commit()

    le = LoggedExercise(session_id=session.id, exercise_id=exercise.id, order_index=0)
    db.session.add(le)
    db.session.commit()

    ls = LoggedSet(logged_exercise_id=le.id, set_number=1, actual_reps=9, actual_weight_kg=62.5, actual_rpe=7.5)
    db.session.add(ls)
    db.session.commit()

    assert ls.actual_weight_kg == 62.5
    assert session.status == 'in_progress'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/training/test_models.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.training.models'`

- [ ] **Step 3: Create app/modules/__init__.py and app/modules/training/__init__.py**

```python
# app/modules/__init__.py
```
```python
# app/modules/training/__init__.py
from flask import Blueprint

bp = Blueprint('training', __name__)

from . import routes  # noqa: F401, E402
```

- [ ] **Step 4: Create app/modules/training/models.py**

```python
from datetime import datetime, date
from app.extensions import db


class Program(db.Model):
    __tablename__ = 'programs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    periodization_type = db.Column(db.String(20), nullable=False)  # linear / wave / block
    total_weeks = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='active')  # active / completed / paused
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    mesocycles = db.relationship('Mesocycle', backref='program', order_by='Mesocycle.order_index',
                                 cascade='all, delete-orphan')


class Mesocycle(db.Model):
    __tablename__ = 'mesocycles'
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)  # Accumulation / Intensification / Deload
    order_index = db.Column(db.Integer, nullable=False)
    weeks_count = db.Column(db.Integer, nullable=False)

    weeks = db.relationship('ProgramWeek', backref='mesocycle', order_by='ProgramWeek.week_number',
                            cascade='all, delete-orphan')


class ProgramWeek(db.Model):
    __tablename__ = 'program_weeks'
    id = db.Column(db.Integer, primary_key=True)
    mesocycle_id = db.Column(db.Integer, db.ForeignKey('mesocycles.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text)

    workouts = db.relationship('Workout', backref='week', order_by='Workout.order_index',
                               cascade='all, delete-orphan')


class Workout(db.Model):
    __tablename__ = 'workouts'
    id = db.Column(db.Integer, primary_key=True)
    program_week_id = db.Column(db.Integer, db.ForeignKey('program_weeks.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Mon … 6=Sun
    name = db.Column(db.String(200), nullable=False)
    order_index = db.Column(db.Integer, nullable=False)

    workout_exercises = db.relationship('WorkoutExercise', backref='workout',
                                        order_by='WorkoutExercise.order_index',
                                        cascade='all, delete-orphan')


class Exercise(db.Model):
    __tablename__ = 'exercises'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    muscle_group = db.Column(db.String(100))
    equipment_needed = db.Column(db.String(100))
    contraindications = db.Column(db.JSON)
    contraindication_severity = db.Column(db.String(20), default='none')  # none / caution / avoid
    mobility_requirements = db.Column(db.JSON)
    posture_considerations = db.Column(db.JSON)
    injury_modifications = db.Column(db.JSON)
    muscle_position = db.Column(db.String(20))  # stretched / shortened / mid
    is_corrective = db.Column(db.Boolean, default=False)
    is_prehab = db.Column(db.Boolean, default=False)


class WorkoutExercise(db.Model):
    __tablename__ = 'workout_exercises'
    id = db.Column(db.Integer, primary_key=True)
    workout_id = db.Column(db.Integer, db.ForeignKey('workouts.id'), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey('exercises.id'), nullable=False)
    order_index = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text)

    planned_sets = db.relationship('PlannedSet', backref='workout_exercise',
                                   order_by='PlannedSet.set_number',
                                   cascade='all, delete-orphan')
    exercise = db.relationship('Exercise')


class PlannedSet(db.Model):
    __tablename__ = 'planned_sets'
    id = db.Column(db.Integer, primary_key=True)
    workout_exercise_id = db.Column(db.Integer, db.ForeignKey('workout_exercises.id'), nullable=False)
    set_number = db.Column(db.Integer, nullable=False)
    target_reps = db.Column(db.String(20))    # e.g. "8-10"
    target_weight_kg = db.Column(db.Float)
    target_rpe = db.Column(db.Float)
    rest_seconds = db.Column(db.Integer)


class WorkoutSession(db.Model):
    __tablename__ = 'workout_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    workout_id = db.Column(db.Integer, db.ForeignKey('workouts.id'), nullable=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(20), default='in_progress')  # in_progress / completed
    notes = db.Column(db.Text)
    ai_feedback = db.Column(db.Text)

    logged_exercises = db.relationship('LoggedExercise', backref='session',
                                       order_by='LoggedExercise.order_index',
                                       cascade='all, delete-orphan')


class LoggedExercise(db.Model):
    __tablename__ = 'logged_exercises'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('workout_sessions.id'), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey('exercises.id'), nullable=False)
    order_index = db.Column(db.Integer, nullable=False)

    logged_sets = db.relationship('LoggedSet', backref='logged_exercise',
                                  order_by='LoggedSet.set_number',
                                  cascade='all, delete-orphan')
    exercise = db.relationship('Exercise')


class LoggedSet(db.Model):
    __tablename__ = 'logged_sets'
    id = db.Column(db.Integer, primary_key=True)
    logged_exercise_id = db.Column(db.Integer, db.ForeignKey('logged_exercises.id'), nullable=False)
    set_number = db.Column(db.Integer, nullable=False)
    actual_reps = db.Column(db.Integer)
    actual_weight_kg = db.Column(db.Float)
    actual_rpe = db.Column(db.Float)
    notes = db.Column(db.Text)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow)
```

- [ ] **Step 5: Create app/modules/training/routes.py (stub)**

```python
from flask import jsonify
from . import bp


@bp.route('/training/ping', methods=['GET'])
def ping():
    return jsonify({'success': True, 'data': 'training module online'})
```

- [ ] **Step 6: Run test to verify it passes**

```bash
pytest tests/training/test_models.py -v
```
Expected: 1 PASS

- [ ] **Step 7: Commit**

```bash
git add app/modules/__init__.py app/modules/training/__init__.py \
        app/modules/training/models.py app/modules/training/routes.py \
        tests/training/test_models.py
git commit -m "feat: add Training module models with full block periodization schema"
```

---

## Task 8: Onboarding Flow

**Files:**
- Create: `app/modules/training/onboarding.py`
- Modify: `app/modules/training/routes.py`
- Test: `tests/training/test_onboarding.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/training/test_onboarding.py
from app.core.models import User
from app.core.auth import create_jwt


def _headers(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


def _make_user(db, telegram_id=50001):
    user = User(telegram_id=telegram_id)
    db.session.add(user)
    db.session.commit()
    return user


def test_onboarding_status_not_completed(client, app, db):
    user = _make_user(db)
    resp = client.get('/api/onboarding/status', headers=_headers(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['data']['completed'] is False
    assert data['data']['next_step'] == 'basic_data'


def test_basic_data_step(client, app, db):
    user = _make_user(db, 50002)
    resp = client.post('/api/onboarding/step', json={
        'step': 'basic_data',
        'data': {'name': 'Natalie', 'gender': 'female', 'age': 26, 'weight_kg': 58.0, 'height_cm': 163.0}
    }, headers=_headers(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['data']['next_step'] == 'goals'
    user = User.query.get(user.id)
    assert user.name == 'Natalie'
    assert user.weight_kg == 58.0


def test_goals_step(client, app, db):
    user = _make_user(db, 50003)
    user.name = 'Test'
    db.session.commit()
    resp = client.post('/api/onboarding/step', json={
        'step': 'goals',
        'data': {'goal_primary': 'hypertrophy', 'goal_secondary': ['health']}
    }, headers=_headers(app, user.id))
    assert resp.status_code == 200
    updated = User.query.get(user.id)
    assert updated.goal_primary == 'hypertrophy'


def test_complete_onboarding(client, app, db):
    user = _make_user(db, 50004)
    resp = client.post('/api/onboarding/complete', headers=_headers(app, user.id))
    assert resp.status_code == 200
    updated = User.query.get(user.id)
    assert updated.onboarding_completed_at is not None


def test_invalid_step_name(client, app, db):
    user = _make_user(db, 50005)
    resp = client.post('/api/onboarding/step', json={
        'step': 'nonexistent_step', 'data': {}
    }, headers=_headers(app, user.id))
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/training/test_onboarding.py -v
```
Expected: FAIL — routes not implemented

- [ ] **Step 3: Create app/modules/training/onboarding.py**

```python
from datetime import datetime
from app.extensions import db
from app.core.models import User

ONBOARDING_STEPS = [
    'basic_data',
    'goals',
    'training_experience',
    'physical_characteristics',
    'menstrual_cycle',
    'training_style',
    'psychology',
    'previous_program',
    'body_measurements',
]


def get_next_step(user: User, current_step: str) -> str | None:
    steps = ONBOARDING_STEPS.copy()
    if user.gender != 'female':
        steps = [s for s in steps if s != 'menstrual_cycle']
    if current_step not in steps:
        return steps[0]
    idx = steps.index(current_step)
    return steps[idx + 1] if idx + 1 < len(steps) else None


def get_first_step(user: User) -> str:
    return ONBOARDING_STEPS[0]


def apply_step(user: User, step: str, data: dict) -> None:
    handlers = {
        'basic_data': _apply_basic_data,
        'goals': _apply_goals,
        'training_experience': _apply_training_experience,
        'physical_characteristics': _apply_physical_characteristics,
        'menstrual_cycle': _apply_menstrual_cycle,
        'training_style': _apply_training_style,
        'psychology': _apply_psychology,
        'previous_program': _apply_previous_program,
        'body_measurements': _apply_body_measurements,
    }
    if step not in handlers:
        raise ValueError(f"Unknown step: {step}")
    handlers[step](user, data)
    db.session.commit()


def _apply_basic_data(user: User, data: dict) -> None:
    user.name = data.get('name', user.name)
    user.gender = data.get('gender', user.gender)
    user.age = data.get('age', user.age)
    user.weight_kg = data.get('weight_kg', user.weight_kg)
    user.height_cm = data.get('height_cm', user.height_cm)
    user.body_fat_pct = data.get('body_fat_pct', user.body_fat_pct)


def _apply_goals(user: User, data: dict) -> None:
    user.goal_primary = data.get('goal_primary', user.goal_primary)
    user.goal_secondary = data.get('goal_secondary', user.goal_secondary)


def _apply_training_experience(user: User, data: dict) -> None:
    user.level = data.get('level', user.level)
    user.training_days_per_week = data.get('training_days_per_week', user.training_days_per_week)
    user.session_duration_min = data.get('session_duration_min', user.session_duration_min)
    user.equipment = data.get('equipment', user.equipment)


def _apply_physical_characteristics(user: User, data: dict) -> None:
    user.injuries_current = data.get('injuries_current', user.injuries_current)
    user.injuries_history = data.get('injuries_history', user.injuries_history)
    user.postural_issues = data.get('postural_issues', user.postural_issues)
    user.mobility_issues = data.get('mobility_issues', user.mobility_issues)
    user.muscle_imbalances = data.get('muscle_imbalances', user.muscle_imbalances)


def _apply_menstrual_cycle(user: User, data: dict) -> None:
    user.menstrual_tracking = data.get('menstrual_tracking', user.menstrual_tracking)
    user.cycle_length_days = data.get('cycle_length_days', user.cycle_length_days)
    if data.get('last_period_date'):
        from datetime import date
        user.last_period_date = date.fromisoformat(data['last_period_date'])


def _apply_training_style(user: User, data: dict) -> None:
    user.training_likes = data.get('training_likes', user.training_likes)
    user.training_dislikes = data.get('training_dislikes', user.training_dislikes)
    user.previous_methods = data.get('previous_methods', user.previous_methods)
    user.had_coach_before = data.get('had_coach_before', user.had_coach_before)


def _apply_psychology(user: User, data: dict) -> None:
    user.motivation_type = data.get('motivation_type', user.motivation_type)


def _apply_previous_program(user: User, data: dict) -> None:
    # Stored as part of training_likes/dislikes context for now
    if data.get('previous_program_notes'):
        existing = user.training_likes or ''
        user.training_likes = existing + f"\nPrevious program: {data['previous_program_notes']}"


def _apply_body_measurements(user: User, data: dict) -> None:
    from datetime import date
    from app.core.models import BodyMeasurement
    m = BodyMeasurement(
        user_id=user.id, date=date.today(),
        weight_kg=data.get('weight_kg'),
        body_fat_pct=data.get('body_fat_pct'),
        waist_cm=data.get('waist_cm'),
        hips_cm=data.get('hips_cm'),
        chest_cm=data.get('chest_cm'),
        left_arm_cm=data.get('left_arm_cm'),
        right_arm_cm=data.get('right_arm_cm'),
        left_leg_cm=data.get('left_leg_cm'),
        right_leg_cm=data.get('right_leg_cm'),
    )
    db.session.add(m)
```

- [ ] **Step 4: Replace app/modules/training/routes.py with onboarding routes added**

```python
from datetime import datetime
from flask import g, jsonify, request
from app.core.auth import require_auth
from app.core.models import User
from app.extensions import db
from . import bp
from .onboarding import ONBOARDING_STEPS, apply_step, get_first_step, get_next_step


# ── Onboarding ────────────────────────────────────────────────────────────────

@bp.route('/onboarding/status', methods=['GET'])
@require_auth
def onboarding_status():
    user = User.query.get(g.user_id)
    completed = user.onboarding_completed_at is not None
    return jsonify({'success': True, 'data': {
        'completed': completed,
        'next_step': None if completed else get_first_step(user),
        'steps': ONBOARDING_STEPS,
    }})


@bp.route('/onboarding/step', methods=['POST'])
@require_auth
def onboarding_step():
    user = User.query.get(g.user_id)
    data = request.json or {}
    step = data.get('step')
    step_data = data.get('data', {})
    try:
        apply_step(user, step, step_data)
    except ValueError as e:
        return jsonify({'success': False, 'error': {'code': 'BAD_REQUEST', 'message': str(e)}}), 400
    next_step = get_next_step(user, step)
    return jsonify({'success': True, 'data': {'next_step': next_step}})


@bp.route('/onboarding/complete', methods=['POST'])
@require_auth
def onboarding_complete():
    user = User.query.get(g.user_id)
    user.onboarding_completed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'data': {'completed': True}})


# ── Ping ──────────────────────────────────────────────────────────────────────

@bp.route('/training/ping', methods=['GET'])
def ping():
    return jsonify({'success': True, 'data': 'training module online'})
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/training/test_onboarding.py -v
```
Expected: 5 PASS

- [ ] **Step 6: Commit**

```bash
git add app/modules/training/onboarding.py app/modules/training/routes.py tests/training/test_onboarding.py
git commit -m "feat: add onboarding step flow with 9 steps and gender-aware menstrual step"
```

---

## Task 9: Training Coach + Program Generation

**Files:**
- Create: `app/modules/training/coach.py`
- Modify: `app/modules/training/routes.py`
- Test: `tests/training/test_coach.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/training/test_coach.py
import json
from unittest.mock import MagicMock
from app.core.models import User
from app.core.auth import create_jwt
from app.modules.training.models import Program, Mesocycle, ProgramWeek, Workout, WorkoutExercise, PlannedSet, Exercise

SAMPLE_PROGRAM = {
    "name": "4-Week Block Program",
    "periodization_type": "block",
    "total_weeks": 4,
    "mesocycles": [
        {
            "name": "Accumulation",
            "order_index": 0,
            "weeks_count": 3,
            "weeks": [
                {
                    "week_number": 1,
                    "notes": "Focus on form",
                    "workouts": [
                        {
                            "day_of_week": 0,
                            "name": "Upper Body A",
                            "order_index": 0,
                            "exercises": [
                                {
                                    "exercise_name": "Bench Press",
                                    "order_index": 0,
                                    "notes": None,
                                    "sets": [
                                        {"set_number": 1, "target_reps": "8-10",
                                         "target_weight_kg": 50.0, "target_rpe": 7.0, "rest_seconds": 120}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    ]
}


def _make_user(db):
    user = User(
        telegram_id=60001, name='Natalie', gender='female', age=26,
        weight_kg=58.0, height_cm=163.0, goal_primary='hypertrophy',
        level='intermediate', training_days_per_week=4, session_duration_min=60,
        equipment=['full_gym'], onboarding_completed_at=__import__('datetime').datetime.utcnow()
    )
    db.session.add(user)
    db.session.commit()
    return user


def test_build_training_context_with_program(db, app):
    from app.modules.training.coach import build_training_context, save_program_from_dict
    user = _make_user(db)
    save_program_from_dict(user.id, SAMPLE_PROGRAM)
    context = build_training_context(user.id)
    assert '4-Week Block Program' in context
    assert 'block' in context


def test_save_program_creates_full_hierarchy(db, app):
    from app.modules.training.coach import save_program_from_dict
    user = _make_user(db)
    program = save_program_from_dict(user.id, SAMPLE_PROGRAM)
    assert program.id is not None
    assert len(program.mesocycles) == 1
    assert len(program.mesocycles[0].weeks) == 1
    assert len(program.mesocycles[0].weeks[0].workouts) == 1
    exercise = Exercise.query.filter_by(name='Bench Press').first()
    assert exercise is not None
    ps = PlannedSet.query.first()
    assert ps.target_reps == '8-10'


def test_generate_program_endpoint(client, app, db, mock_anthropic):
    user = _make_user(db)
    mock_anthropic.messages.create.return_value = MagicMock(
        content=[MagicMock(text=json.dumps(SAMPLE_PROGRAM))]
    )
    token = create_jwt(user.id, app.config['SECRET_KEY'])
    resp = client.post('/api/training/program/generate',
                       headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert Program.query.filter_by(user_id=user.id).count() == 1


def test_generate_program_requires_onboarding(client, app, db):
    user = User(telegram_id=60002)
    db.session.add(user)
    db.session.commit()
    token = create_jwt(user.id, app.config['SECRET_KEY'])
    resp = client.post('/api/training/program/generate',
                       headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/training/test_coach.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.training.coach'`

- [ ] **Step 3: Create app/modules/training/coach.py**

```python
import json
from app.core.ai import complete
from app.core.models import User
from app.extensions import db
from .models import (
    Exercise, LoggedExercise, LoggedSet, Mesocycle, PlannedSet,
    Program, ProgramWeek, Workout, WorkoutExercise, WorkoutSession
)


def build_training_context(user_id: int, session_id: int = None) -> str:
    parts = []
    program = Program.query.filter_by(user_id=user_id, status='active').first()
    if program:
        parts.append(f"\n## Active Program: {program.name} ({program.periodization_type})")
        parts.append(f"Total weeks: {program.total_weeks}")

    if session_id:
        session = WorkoutSession.query.get(session_id)
        if session and session.status == 'in_progress':
            parts.append("\n## Current Workout Session (in progress)")
            for le in session.logged_exercises:
                sets_text = ', '.join(
                    f"{s.actual_reps}x{s.actual_weight_kg}kg@RPE{s.actual_rpe}"
                    for s in le.logged_sets
                )
                parts.append(f"- {le.exercise.name}: {sets_text or 'no sets yet'}")

    return '\n'.join(parts) if parts else ''


def save_program_from_dict(user_id: int, program_dict: dict) -> Program:
    """Parse AI-generated program JSON and persist to DB."""
    # Deactivate any existing active program
    Program.query.filter_by(user_id=user_id, status='active').update({'status': 'paused'})

    program = Program(
        user_id=user_id,
        name=program_dict['name'],
        periodization_type=program_dict['periodization_type'],
        total_weeks=program_dict['total_weeks'],
    )
    db.session.add(program)
    db.session.flush()

    for meso_data in program_dict.get('mesocycles', []):
        meso = Mesocycle(
            program_id=program.id,
            name=meso_data['name'],
            order_index=meso_data['order_index'],
            weeks_count=meso_data['weeks_count'],
        )
        db.session.add(meso)
        db.session.flush()

        for week_data in meso_data.get('weeks', []):
            week = ProgramWeek(
                mesocycle_id=meso.id,
                week_number=week_data['week_number'],
                notes=week_data.get('notes'),
            )
            db.session.add(week)
            db.session.flush()

            for wo_data in week_data.get('workouts', []):
                workout = Workout(
                    program_week_id=week.id,
                    day_of_week=wo_data['day_of_week'],
                    name=wo_data['name'],
                    order_index=wo_data['order_index'],
                )
                db.session.add(workout)
                db.session.flush()

                for ex_data in wo_data.get('exercises', []):
                    exercise = _get_or_create_exercise(ex_data['exercise_name'])
                    we = WorkoutExercise(
                        workout_id=workout.id,
                        exercise_id=exercise.id,
                        order_index=ex_data['order_index'],
                        notes=ex_data.get('notes'),
                    )
                    db.session.add(we)
                    db.session.flush()

                    for set_data in ex_data.get('sets', []):
                        ps = PlannedSet(
                            workout_exercise_id=we.id,
                            set_number=set_data['set_number'],
                            target_reps=set_data.get('target_reps'),
                            target_weight_kg=set_data.get('target_weight_kg'),
                            target_rpe=set_data.get('target_rpe'),
                            rest_seconds=set_data.get('rest_seconds'),
                        )
                        db.session.add(ps)

    db.session.commit()
    return program


def _get_or_create_exercise(name: str) -> Exercise:
    exercise = Exercise.query.filter_by(name=name).first()
    if not exercise:
        exercise = Exercise(name=name)
        db.session.add(exercise)
        db.session.flush()
    return exercise


def generate_program(user: User) -> dict:
    system_prompt = """You are an expert strength and conditioning coach.
Generate a complete periodized training program as JSON only — no prose, no markdown, just valid JSON.
Structure:
{
  "name": "...",
  "periodization_type": "linear|wave|block",
  "total_weeks": N,
  "mesocycles": [
    {
      "name": "Accumulation|Intensification|Deload",
      "order_index": 0,
      "weeks_count": N,
      "weeks": [
        {
          "week_number": 1,
          "notes": "optional",
          "workouts": [
            {
              "day_of_week": 0,
              "name": "Upper Body A",
              "order_index": 0,
              "exercises": [
                {
                  "exercise_name": "Bench Press",
                  "order_index": 0,
                  "notes": null,
                  "sets": [
                    {"set_number": 1, "target_reps": "8-10",
                     "target_weight_kg": 60.0, "target_rpe": 7.0, "rest_seconds": 120}
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}"""

    user_prompt = f"""Create a training program for:
- Name: {user.name}, Gender: {user.gender}, Age: {user.age}
- Weight: {user.weight_kg}kg, Height: {user.height_cm}cm, Body fat: {user.body_fat_pct}%
- Primary goal: {user.goal_primary}, Secondary: {user.goal_secondary}
- Level: {user.level}
- Training: {user.training_days_per_week} days/week, {user.session_duration_min} min/session
- Equipment: {user.equipment}
- Current injuries: {user.injuries_current}
- Postural issues: {user.postural_issues}
- Mobility issues: {user.mobility_issues}
- Likes: {user.training_likes}, Dislikes: {user.training_dislikes}

Ensure all exercises respect the user's injuries and mobility restrictions."""

    result = complete(system_prompt, user_prompt, max_tokens=8192)
    return json.loads(result)
```

- [ ] **Step 4: Add program routes to app/modules/training/routes.py**

Append to the existing routes.py after the onboarding section:

```python
from .coach import build_training_context, generate_program, save_program_from_dict
from .models import Program


# ── Program ───────────────────────────────────────────────────────────────────

@bp.route('/training/program/generate', methods=['POST'])
@require_auth
def program_generate():
    user = User.query.get(g.user_id)
    if not user.onboarding_completed_at:
        return jsonify({'success': False, 'error': {
            'code': 'BAD_REQUEST', 'message': 'Complete onboarding first'
        }}), 400
    program_dict = generate_program(user)
    program = save_program_from_dict(user.id, program_dict)
    return jsonify({'success': True, 'data': {
        'program_id': program.id,
        'name': program.name,
        'total_weeks': program.total_weeks,
        'periodization_type': program.periodization_type,
    }})


@bp.route('/training/program/current', methods=['GET'])
@require_auth
def program_current():
    program = Program.query.filter_by(user_id=g.user_id, status='active').first()
    if not program:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': _serialize_program(program)})


@bp.route('/training/program/week/<int:week_num>', methods=['GET'])
@require_auth
def program_week(week_num):
    program = Program.query.filter_by(user_id=g.user_id, status='active').first()
    if not program:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'No active program'}}), 404
    from .models import ProgramWeek
    week = (ProgramWeek.query
            .join(Mesocycle)
            .filter(Mesocycle.program_id == program.id, ProgramWeek.week_number == week_num)
            .first())
    if not week:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': f'Week {week_num} not found'}}), 404
    return jsonify({'success': True, 'data': _serialize_week(week)})


def _serialize_program(program):
    return {
        'id': program.id,
        'name': program.name,
        'periodization_type': program.periodization_type,
        'total_weeks': program.total_weeks,
        'status': program.status,
        'mesocycles': [{
            'id': m.id, 'name': m.name, 'order_index': m.order_index, 'weeks_count': m.weeks_count
        } for m in program.mesocycles],
    }


def _serialize_week(week):
    return {
        'week_number': week.week_number,
        'notes': week.notes,
        'workouts': [{
            'id': w.id, 'day_of_week': w.day_of_week, 'name': w.name,
            'exercises': [{
                'exercise_name': we.exercise.name,
                'notes': we.notes,
                'sets': [{
                    'set_number': ps.set_number,
                    'target_reps': ps.target_reps,
                    'target_weight_kg': ps.target_weight_kg,
                    'target_rpe': ps.target_rpe,
                    'rest_seconds': ps.rest_seconds,
                } for ps in we.planned_sets]
            } for we in w.workout_exercises]
        } for w in week.workouts]
    }
```

> Also add `from .models import Mesocycle` at the top of routes.py if not present.

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/training/test_coach.py -v
```
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add app/modules/training/coach.py app/modules/training/routes.py tests/training/test_coach.py
git commit -m "feat: add program generation, AI coach context builder, program save/serialize"
```

---

## Task 10: Workout Session — Today, Start, Log Set, Complete

**Files:**
- Create: `app/modules/training/progress.py`
- Modify: `app/modules/training/routes.py`
- Test: `tests/training/test_session.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/training/test_session.py
import json
from datetime import date, datetime
from unittest.mock import MagicMock
from app.core.models import User
from app.core.auth import create_jwt
from app.modules.training.coach import save_program_from_dict
from app.modules.training.models import (
    Exercise, LoggedExercise, LoggedSet, Workout, WorkoutSession
)

SAMPLE_PROGRAM = {
    "name": "Test Program", "periodization_type": "linear", "total_weeks": 4,
    "mesocycles": [{
        "name": "Accumulation", "order_index": 0, "weeks_count": 4,
        "weeks": [{
            "week_number": 1, "notes": None,
            "workouts": [{
                "day_of_week": date.today().weekday(), "name": "Full Body", "order_index": 0,
                "exercises": [{
                    "exercise_name": "Squat", "order_index": 0, "notes": None,
                    "sets": [
                        {"set_number": 1, "target_reps": "5", "target_weight_kg": 80.0,
                         "target_rpe": 8.0, "rest_seconds": 180}
                    ]
                }]
            }]
        }]
    }]
}


def _make_user(db):
    user = User(
        telegram_id=70001, name='Test', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='strength',
        level='intermediate', training_days_per_week=3, session_duration_min=60,
        equipment=['full_gym'], onboarding_completed_at=datetime.utcnow()
    )
    db.session.add(user)
    db.session.commit()
    return user


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


def test_get_today_workout(client, app, db):
    user = _make_user(db)
    save_program_from_dict(user.id, SAMPLE_PROGRAM)
    resp = client.get('/api/training/today', headers=_h(app, user.id))
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data is not None
    assert data['name'] == 'Full Body'
    assert len(data['exercises']) == 1


def test_start_session(client, app, db):
    user = _make_user(db)
    save_program_from_dict(user.id, SAMPLE_PROGRAM)
    today_resp = client.get('/api/training/today', headers=_h(app, user.id))
    workout_id = today_resp.get_json()['data']['id']
    resp = client.post('/api/training/session/start', json={'workout_id': workout_id},
                       headers=_h(app, user.id))
    assert resp.status_code == 200
    session_id = resp.get_json()['data']['session_id']
    assert WorkoutSession.query.get(session_id).status == 'in_progress'


def test_log_set(client, app, db):
    user = _make_user(db)
    save_program_from_dict(user.id, SAMPLE_PROGRAM)
    exercise = Exercise.query.filter_by(name='Squat').first()
    session = WorkoutSession(user_id=user.id, date=date.today())
    db.session.add(session)
    db.session.commit()
    resp = client.post('/api/training/session/log-set', json={
        'session_id': session.id,
        'exercise_id': exercise.id,
        'set_number': 1,
        'actual_reps': 5,
        'actual_weight_kg': 82.5,
        'actual_rpe': 8.5,
    }, headers=_h(app, user.id))
    assert resp.status_code == 200
    assert LoggedSet.query.count() == 1
    assert LoggedExercise.query.count() == 1


def test_log_second_set_appends_to_same_logged_exercise(client, app, db):
    user = _make_user(db)
    save_program_from_dict(user.id, SAMPLE_PROGRAM)
    exercise = Exercise.query.filter_by(name='Squat').first()
    session = WorkoutSession(user_id=user.id, date=date.today())
    db.session.add(session)
    db.session.commit()
    for i, (reps, weight) in enumerate([(5, 80.0), (5, 82.5)], start=1):
        client.post('/api/training/session/log-set', json={
            'session_id': session.id, 'exercise_id': exercise.id,
            'set_number': i, 'actual_reps': reps, 'actual_weight_kg': weight, 'actual_rpe': 8.0,
        }, headers=_h(app, user.id))
    assert LoggedExercise.query.count() == 1
    assert LoggedSet.query.count() == 2


def test_complete_session(client, app, db, mock_anthropic):
    user = _make_user(db)
    session = WorkoutSession(user_id=user.id, date=date.today())
    db.session.add(session)
    db.session.commit()
    mock_anthropic.messages.create.return_value = MagicMock(
        content=[MagicMock(text='Great workout! You hit all your targets.')]
    )
    resp = client.post('/api/training/session/complete', json={'session_id': session.id},
                       headers=_h(app, user.id))
    assert resp.status_code == 200
    updated = WorkoutSession.query.get(session.id)
    assert updated.status == 'completed'
    assert updated.ai_feedback == 'Great workout! You hit all your targets.'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/training/test_session.py -v
```
Expected: FAIL — routes not implemented

- [ ] **Step 3: Create app/modules/training/progress.py**

```python
from app.core.ai import build_base_system, complete
from .models import LoggedExercise, LoggedSet, WorkoutSession, Program, ProgramWeek, Mesocycle, Exercise


def generate_post_workout_feedback(session: WorkoutSession, user_id: int) -> str:
    system = build_base_system(user_id) + "\n\nYou are reviewing a completed workout. Be encouraging, specific, and concise (3-5 sentences)."

    lines = ["## Completed Workout Log"]
    for le in session.logged_exercises:
        sets_text = ', '.join(
            f"Set {s.set_number}: {s.actual_reps} reps @ {s.actual_weight_kg}kg RPE {s.actual_rpe}"
            for s in le.logged_sets
        )
        lines.append(f"- {le.exercise.name}: {sets_text or 'no sets logged'}")

    if session.workout_id:
        from .models import Workout
        workout = Workout.query.get(session.workout_id)
        if workout:
            lines.append(f"\nPlanned workout: {workout.name}")

    return complete(system, '\n'.join(lines))


def generate_weekly_report(user_id: int, week_sessions: list[WorkoutSession]) -> str:
    from app.core.ai import build_base_system, complete
    from app.core.models import PainJournal
    from datetime import date, timedelta
    system = build_base_system(user_id) + "\n\nGenerate a weekly training report. Include: performance trends, volume analysis, pain/recovery notes, and 2-3 actionable recommendations for next week."

    lines = [f"## Weekly Report — {date.today().isoformat()}"]
    for session in week_sessions:
        lines.append(f"\n### Session {session.date.isoformat()}")
        for le in session.logged_exercises:
            sets_text = ', '.join(f"{s.actual_reps}x{s.actual_weight_kg}kg" for s in le.logged_sets)
            lines.append(f"- {le.exercise.name}: {sets_text}")

    since = date.today() - timedelta(days=7)
    from app.core.models import PainJournal
    pain_entries = PainJournal.query.filter(
        PainJournal.user_id == user_id, PainJournal.date >= since
    ).all()
    if pain_entries:
        lines.append("\n## Pain Journal This Week")
        for p in pain_entries:
            lines.append(f"- {p.date}: {p.body_part} ({p.pain_type}, intensity {p.intensity})")

    return complete(system, '\n'.join(lines))
```

- [ ] **Step 4: Add session routes to app/modules/training/routes.py**

Append to routes.py:

```python
from datetime import date, timedelta
from .models import (
    LoggedExercise, LoggedSet, Workout, WorkoutSession, Mesocycle, ProgramWeek
)
from .progress import generate_post_workout_feedback, generate_weekly_report


# ── Today's workout ───────────────────────────────────────────────────────────

@bp.route('/training/today', methods=['GET'])
@require_auth
def training_today():
    program = Program.query.filter_by(user_id=g.user_id, status='active').first()
    if not program:
        return jsonify({'success': True, 'data': None})

    today_dow = date.today().weekday()
    # Find week number based on days since program creation
    days_elapsed = (date.today() - program.created_at.date()).days
    current_week_num = (days_elapsed // 7) + 1

    week = (ProgramWeek.query
            .join(Mesocycle)
            .filter(Mesocycle.program_id == program.id, ProgramWeek.week_number == current_week_num)
            .first())
    if not week:
        return jsonify({'success': True, 'data': None})

    workout = Workout.query.filter_by(program_week_id=week.id, day_of_week=today_dow).first()
    if not workout:
        return jsonify({'success': True, 'data': {'rest_day': True}})

    return jsonify({'success': True, 'data': _serialize_workout_with_sets(workout)})


def _serialize_workout_with_sets(workout: Workout) -> dict:
    return {
        'id': workout.id,
        'name': workout.name,
        'day_of_week': workout.day_of_week,
        'exercises': [{
            'exercise_id': we.exercise_id,
            'exercise_name': we.exercise.name,
            'order_index': we.order_index,
            'sets': [{
                'set_number': ps.set_number,
                'target_reps': ps.target_reps,
                'target_weight_kg': ps.target_weight_kg,
                'target_rpe': ps.target_rpe,
                'rest_seconds': ps.rest_seconds,
            } for ps in we.planned_sets]
        } for we in workout.workout_exercises]
    }


# ── Session ───────────────────────────────────────────────────────────────────

@bp.route('/training/session/start', methods=['POST'])
@require_auth
def session_start():
    data = request.json or {}
    session = WorkoutSession(
        user_id=g.user_id,
        workout_id=data.get('workout_id'),
        date=date.today(),
        status='in_progress',
    )
    db.session.add(session)
    db.session.commit()
    return jsonify({'success': True, 'data': {'session_id': session.id}})


@bp.route('/training/session/log-set', methods=['POST'])
@require_auth
def session_log_set():
    data = request.json or {}
    session_id = data.get('session_id')
    exercise_id = data.get('exercise_id')

    # Get or create LoggedExercise for this session+exercise
    le = LoggedExercise.query.filter_by(session_id=session_id, exercise_id=exercise_id).first()
    if not le:
        existing_count = LoggedExercise.query.filter_by(session_id=session_id).count()
        le = LoggedExercise(session_id=session_id, exercise_id=exercise_id, order_index=existing_count)
        db.session.add(le)
        db.session.flush()

    ls = LoggedSet(
        logged_exercise_id=le.id,
        set_number=data.get('set_number', 1),
        actual_reps=data.get('actual_reps'),
        actual_weight_kg=data.get('actual_weight_kg'),
        actual_rpe=data.get('actual_rpe'),
        notes=data.get('notes'),
    )
    db.session.add(ls)
    db.session.commit()
    return jsonify({'success': True, 'data': {'logged_set_id': ls.id}})


@bp.route('/training/session/complete', methods=['POST'])
@require_auth
def session_complete():
    data = request.json or {}
    session = WorkoutSession.query.filter_by(id=data.get('session_id'), user_id=g.user_id).first()
    if not session:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Session not found'}}), 404

    session.status = 'completed'
    db.session.commit()

    feedback = generate_post_workout_feedback(session, g.user_id)
    session.ai_feedback = feedback
    db.session.commit()

    return jsonify({'success': True, 'data': {
        'session_id': session.id,
        'feedback': feedback,
    }})


@bp.route('/training/session/<int:session_id>', methods=['GET'])
@require_auth
def session_detail(session_id):
    session = WorkoutSession.query.filter_by(id=session_id, user_id=g.user_id).first()
    if not session:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Session not found'}}), 404
    return jsonify({'success': True, 'data': {
        'id': session.id,
        'date': session.date.isoformat(),
        'status': session.status,
        'ai_feedback': session.ai_feedback,
        'exercises': [{
            'exercise_name': le.exercise.name,
            'sets': [{
                'set_number': s.set_number,
                'actual_reps': s.actual_reps,
                'actual_weight_kg': s.actual_weight_kg,
                'actual_rpe': s.actual_rpe,
            } for s in le.logged_sets]
        } for le in session.logged_exercises]
    }})


# ── Progress ──────────────────────────────────────────────────────────────────

@bp.route('/training/progress/weekly', methods=['GET'])
@require_auth
def progress_weekly():
    since = date.today() - timedelta(days=7)
    sessions = (WorkoutSession.query
                .filter(WorkoutSession.user_id == g.user_id,
                        WorkoutSession.date >= since,
                        WorkoutSession.status == 'completed')
                .order_by(WorkoutSession.date)
                .all())
    report = generate_weekly_report(g.user_id, sessions)
    return jsonify({'success': True, 'data': {'report': report}})


@bp.route('/training/progress/history', methods=['GET'])
@require_auth
def progress_history():
    sessions = (WorkoutSession.query
                .filter_by(user_id=g.user_id)
                .order_by(WorkoutSession.date.desc())
                .limit(50)
                .all())
    return jsonify({'success': True, 'data': [{
        'id': s.id, 'date': s.date.isoformat(),
        'status': s.status, 'workout_id': s.workout_id,
    } for s in sessions]})
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/training/test_session.py -v
```
Expected: 5 PASS

- [ ] **Step 6: Commit**

```bash
git add app/modules/training/progress.py app/modules/training/routes.py tests/training/test_session.py
git commit -m "feat: add workout session — today, start, log-set, complete with AI feedback"
```

---

## Task 11: Training Chat (SSE Streaming)

**Files:**
- Modify: `app/modules/training/routes.py`
- Test: `tests/training/test_chat.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/training/test_chat.py
from unittest.mock import MagicMock
from app.core.models import User, AIConversation
from app.core.auth import create_jwt


def _make_user(db):
    from datetime import datetime
    user = User(
        telegram_id=80001, name='Natalie', gender='female', age=26,
        weight_kg=58.0, height_cm=163.0, goal_primary='hypertrophy',
        level='intermediate', training_days_per_week=4, session_duration_min=60,
        equipment=['full_gym'], onboarding_completed_at=datetime.utcnow()
    )
    db.session.add(user)
    db.session.commit()
    return user


def test_training_chat_streams_response(client, app, db, mock_anthropic):
    user = _make_user(db)

    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.text_stream = iter(['Great', ' plan', '!'])
    mock_anthropic.messages.stream.return_value = mock_stream

    token = create_jwt(user.id, app.config['SECRET_KEY'])
    resp = client.post('/api/training/chat',
                       json={'message': 'What should I focus on today?'},
                       headers={'Authorization': f'Bearer {token}'})

    assert resp.status_code == 200
    assert resp.content_type == 'text/event-stream'
    body = resp.data.decode()
    assert 'Great' in body
    assert 'plan' in body


def test_training_chat_saves_conversation(client, app, db, mock_anthropic):
    user = _make_user(db)

    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.text_stream = iter(['Keep it up!'])
    mock_anthropic.messages.stream.return_value = mock_stream

    token = create_jwt(user.id, app.config['SECRET_KEY'])
    client.post('/api/training/chat',
                json={'message': 'How many sets should I do?'},
                headers={'Authorization': f'Bearer {token}'})

    msgs = AIConversation.query.filter_by(user_id=user.id, module='training').all()
    assert len(msgs) == 2
    assert msgs[0].role == 'user'
    assert msgs[1].role == 'assistant'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/training/test_chat.py -v
```
Expected: FAIL — chat route not implemented

- [ ] **Step 3: Add chat route to app/modules/training/routes.py**

Add to routes.py (after existing imports, add `from flask import Response, stream_with_context`):

```python
from flask import Response, stream_with_context
from app.core.ai import stream_chat


@bp.route('/training/chat', methods=['POST'])
@require_auth
def training_chat():
    data = request.json or {}
    message = data.get('message', '')
    session_id = data.get('session_id')  # optional — enriches context if in active session

    extra_context = build_training_context(g.user_id, session_id=session_id)

    def generate():
        for chunk in stream_chat(g.user_id, 'training', message, extra_context=extra_context):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/training/test_chat.py -v
```
Expected: 2 PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/modules/training/routes.py tests/training/test_chat.py
git commit -m "feat: add training chat SSE streaming endpoint"
```

---

## Task 12: Initialize DB Migrations

**Files:**
- Initialize Flask-Migrate

- [ ] **Step 1: Run migrations init**

```bash
flask --app run db init
flask --app run db migrate -m "initial schema"
flask --app run db upgrade
```
Expected: `migrations/` folder created, `body_coach.db` created with all tables.

- [ ] **Step 2: Verify tables exist**

```bash
python -c "
from app import create_app
from app.extensions import db
app = create_app()
with app.app_context():
    tables = db.engine.table_names()
    print('Tables:', sorted(tables))
"
```
Expected: Output includes `users`, `programs`, `mesocycles`, `program_weeks`, `workouts`, `exercises`, `workout_exercises`, `planned_sets`, `workout_sessions`, `logged_exercises`, `logged_sets`, `daily_checkins`, `pain_journal`, `ai_conversations`, `body_measurements`, `injury_details`.

- [ ] **Step 3: Commit migrations**

```bash
git add migrations/
git commit -m "feat: add Flask-Migrate initial schema migration"
```

---

## Self-Review

**Spec coverage check:**
- ✅ Universal foundation (extensions.py, blueprints, core patterns)
- ✅ Shared schema: users, body_measurements, injury_details, daily_checkins, pain_journal, ai_conversations
- ✅ Training schema: full block periodization hierarchy
- ✅ Auth: Telegram initData validation → JWT
- ✅ Conversation memory: per user per module, 15-message window
- ✅ AI context: base system prompt + training context + daily checkin
- ✅ Onboarding: 9 steps, gender-aware menstrual step
- ✅ Program generation: AI generates JSON → saved to DB
- ✅ Today's workout: week calculation from program start
- ✅ Session: start, log-set (get-or-create LoggedExercise), complete
- ✅ Post-workout feedback: AI analyzes actual vs planned
- ✅ Weekly report: 7-day sessions + pain journal
- ✅ SSE streaming chat: with training context injection
- ✅ Core routes: auth, checkin, pain, measurements
- ✅ Migrations

**Type consistency check:**
- `save_program_from_dict(user_id, program_dict)` — consistent across coach.py, routes.py, tests
- `build_training_context(user_id, session_id=None)` — consistent across coach.py, routes.py, tests
- `generate_post_workout_feedback(session, user_id)` — consistent across progress.py, routes.py, tests
- `stream_chat(user_id, module, user_message, extra_context)` — consistent across ai.py, routes.py, tests

**No placeholders found.**
