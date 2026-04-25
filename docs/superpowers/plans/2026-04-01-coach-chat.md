# Coach Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-conversation AI coach chat in the Coach tab — thread list + thread view with SSE streaming, backed by a new isolated `coach` Flask blueprint.

**Architecture:** New `app/modules/coach/` module (models, routes, context). Frontend is two view-states inside `#panel-coach`: list and thread. Auth uses JWT Bearer header (same as all other routes). SSE stream via `Response(stream_with_context(...))`.

**Tech Stack:** Flask, SQLAlchemy, Anthropic API (`claude-sonnet-4-6` chat, `claude-haiku-4-5-20251001` title gen), existing `build_base_system()`, JWT auth, SSE streaming.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `app/modules/coach/__init__.py` | Blueprint definition |
| Create | `app/modules/coach/models.py` | `ChatThread`, `ChatMessage` models |
| Create | `app/modules/coach/context.py` | `build_coach_context()` + `COACH_SYSTEM` prompt |
| Create | `app/modules/coach/routes.py` | All 6 endpoints |
| Modify | `app/__init__.py` | Register coach blueprint |
| Modify | `app/templates/index.html` | Coach tab CSS + HTML + JS |
| Create | `migrations/versions/xxx_add_coach_chat.py` | Auto-generated migration |
| Create | `tests/coach/test_routes.py` | API endpoint tests |
| Create | `tests/coach/__init__.py` | Test package marker |

---

## Task 1: DB Models + Blueprint + Migration

**Files:**
- Create: `app/modules/coach/__init__.py`
- Create: `app/modules/coach/models.py`
- Create: `migrations/versions/xxx_add_coach_chat_tables.py` (auto-generated)
- Modify: `app/__init__.py`

- [ ] **Step 1: Create blueprint init**

```python
# app/modules/coach/__init__.py
from flask import Blueprint

bp = Blueprint('coach', __name__)

from . import routes  # noqa
```

- [ ] **Step 2: Create models**

```python
# app/modules/coach/models.py
from datetime import datetime
from app.extensions import db


class ChatThread(db.Model):
    __tablename__ = 'chat_threads'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False, default='Нова розмова')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    messages = db.relationship(
        'ChatMessage', backref='thread',
        order_by='ChatMessage.created_at',
        cascade='all, delete-orphan',
    )


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey('chat_threads.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)   # 'user' | 'assistant'
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

- [ ] **Step 3: Register blueprint in app factory**

In `app/__init__.py`, add after the training blueprint registration:

```python
    from .modules.coach import bp as coach_bp
    app.register_blueprint(coach_bp, url_prefix='/api')
```

Also add this line before the blueprint imports (so models are picked up by SQLAlchemy):

```python
    from .modules.coach import models as coach_models  # noqa: F401
```

Full updated `app/__init__.py`:

```python
from flask import Flask, jsonify, render_template
from .config import Config
from .extensions import db, migrate


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)

    from .core import models  # noqa: F401
    from .modules.coach import models as coach_models  # noqa: F401

    from .core.routes import bp as core_bp
    app.register_blueprint(core_bp, url_prefix='/api')

    from .modules.training import bp as training_bp
    app.register_blueprint(training_bp, url_prefix='/api')

    from .modules.coach import bp as coach_bp
    app.register_blueprint(coach_bp, url_prefix='/api')

    @app.route('/')
    def index():
        return render_template('index.html')

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

- [ ] **Step 4: Create empty routes.py so blueprint import doesn't fail**

```python
# app/modules/coach/routes.py
from flask import g, jsonify, request
from app.core.auth import require_auth
from app.extensions import db
from . import bp
from .models import ChatMessage, ChatThread
```

- [ ] **Step 5: Generate and apply migration**

```bash
flask db migrate -m "add coach chat tables"
flask db upgrade
```

Expected output contains:
```
Detected added table 'chat_threads'
Detected added table 'chat_messages'
```

If the migration adds FK constraints that cause errors on SQLite (like in previous migrations), open the generated file and remove any `batch_op.create_foreign_key(...)` lines, keeping only `add_column` calls.

- [ ] **Step 6: Write failing model test**

```python
# tests/coach/__init__.py
# (empty)
```

```python
# tests/coach/test_routes.py
import pytest
from datetime import datetime
from app.core.models import User
from app.core.auth import create_jwt
from app.modules.coach.models import ChatMessage, ChatThread


def _make_user(db):
    user = User(
        telegram_id=90001, name='CoachTest', gender='female', age=25,
        weight_kg=60.0, height_cm=165.0, goal_primary='hypertrophy',
        level='intermediate', training_days_per_week=3, session_duration_min=60,
        equipment=['full_gym'], onboarding_completed_at=datetime.utcnow(),
    )
    db.session.add(user)
    db.session.commit()
    return user


def _h(app, user_id):
    return {'Authorization': f'Bearer {create_jwt(user_id, app.config["SECRET_KEY"])}'}


def test_models_exist(app, db):
    user = _make_user(db)
    thread = ChatThread(user_id=user.id)
    db.session.add(thread)
    db.session.commit()
    assert thread.id is not None
    assert thread.title == 'Нова розмова'

    msg = ChatMessage(thread_id=thread.id, role='user', content='hello')
    db.session.add(msg)
    db.session.commit()
    assert msg.id is not None
```

- [ ] **Step 7: Run test to verify it passes**

```bash
pytest tests/coach/test_routes.py::test_models_exist -v
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add app/modules/coach/ app/__init__.py migrations/
git commit -m "feat: add coach module — ChatThread + ChatMessage models"
```

---

## Task 2: Coach Context Builder

**Files:**
- Create: `app/modules/coach/context.py`

- [ ] **Step 1: Write failing test**

Add to `tests/coach/test_routes.py`:

```python
def test_build_coach_context_returns_string(app, db):
    user = _make_user(db)
    from app.modules.coach.context import build_coach_context
    ctx = build_coach_context(user.id)
    assert isinstance(ctx, str)
    assert len(ctx) > 50
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/coach/test_routes.py::test_build_coach_context_returns_string -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement context.py**

```python
# app/modules/coach/context.py
from datetime import date, timedelta

from app.core.ai import build_base_system

COACH_SYSTEM = """You are an elite personal coach combining expertise of:
physical therapist, rehabilitation therapist, biomechanics specialist,
sports nutritionist, registered dietitian, sport psychologist,
exercise psychologist, strength & conditioning coach, wellness coach.

Rules:
- Always respond in the user's language (Ukrainian if app_language='uk', else English)
- Be specific — reference the user's actual data (program, last workout, check-in numbers)
- Never give generic advice. Say "Your bench press was 60kg at RPE 8 yesterday" not "keep training hard"
- Keep responses concise: 3-5 bullet points or short paragraphs
- If asked about pain or injury: give guidance AND recommend seeing a doctor for diagnosis
- Use markdown headers (##) and bullets (-) — they render correctly in the app
- Never say "I'm just an AI" — you are their coach"""


def build_coach_context(user_id: int) -> str:
    from app.core.models import PainJournal
    from app.extensions import db
    from app.modules.training.models import (
        Mesocycle, Program, ProgramWeek, WorkoutSession,
    )

    parts = [build_base_system(user_id)]

    # Active program
    program = Program.query.filter_by(user_id=user_id, status='active').first()
    if program:
        parts.append(f"\n## Active Program: {program.name} ({program.periodization_type})")
        parts.append(f"Total weeks: {program.total_weeks}")

    # Last completed workout
    last_session = (WorkoutSession.query
                    .filter_by(user_id=user_id, status='completed')
                    .order_by(WorkoutSession.date.desc())
                    .first())
    if last_session:
        parts.append(f"\n## Last Workout ({last_session.date.isoformat()})")
        for le in last_session.logged_exercises:
            sets_text = ', '.join(
                f"{s.actual_reps}r×{s.actual_weight_kg}kg RPE{s.actual_rpe}"
                for s in le.logged_sets
            )
            parts.append(f"- {le.exercise.name}: {sets_text or 'no sets'}")

    # Recent pain journal (last 14 days, max 3 entries)
    since = date.today() - timedelta(days=14)
    pain_entries = (PainJournal.query
                    .filter(PainJournal.user_id == user_id, PainJournal.date >= since)
                    .order_by(PainJournal.date.desc())
                    .limit(3)
                    .all())
    if pain_entries:
        parts.append("\n## Recent Pain Journal")
        for p in pain_entries:
            parts.append(f"- {p.date}: {p.body_part} ({p.pain_type}, intensity {p.intensity}/10)")

    return '\n'.join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/coach/test_routes.py::test_build_coach_context_returns_string -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/coach/context.py tests/coach/
git commit -m "feat: coach context builder with full user + program + workout context"
```

---

## Task 3: Backend CRUD Endpoints

**Files:**
- Modify: `app/modules/coach/routes.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/coach/test_routes.py`:

```python
def test_list_threads_empty(client, app, db):
    user = _make_user(db)
    resp = client.get('/api/coach/threads', headers=_h(app, user.id))
    assert resp.status_code == 200
    assert resp.get_json() == {'success': True, 'data': []}


def test_create_and_list_thread(client, app, db):
    user = _make_user(db)
    h = _h(app, user.id)

    resp = client.post('/api/coach/threads', headers=h, json={})
    assert resp.status_code == 200
    thread_id = resp.get_json()['data']['thread_id']
    assert isinstance(thread_id, int)

    resp = client.get('/api/coach/threads', headers=h)
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['id'] == thread_id
    assert data[0]['title'] == 'Нова розмова'


def test_get_thread_messages(client, app, db):
    user = _make_user(db)
    h = _h(app, user.id)

    thread_id = client.post('/api/coach/threads', headers=h, json={}).get_json()['data']['thread_id']
    resp = client.get(f'/api/coach/threads/{thread_id}', headers=h)
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['id'] == thread_id
    assert data['messages'] == []


def test_get_thread_not_found(client, app, db):
    user = _make_user(db)
    resp = client.get('/api/coach/threads/99999', headers=_h(app, user.id))
    assert resp.status_code == 404


def test_delete_thread(client, app, db):
    user = _make_user(db)
    h = _h(app, user.id)

    thread_id = client.post('/api/coach/threads', headers=h, json={}).get_json()['data']['thread_id']
    resp = client.delete(f'/api/coach/threads/{thread_id}', headers=h)
    assert resp.status_code == 200

    resp = client.get('/api/coach/threads', headers=h)
    assert resp.get_json()['data'] == []


def test_cannot_access_other_users_thread(client, app, db):
    user1 = _make_user(db)
    user2 = User(
        telegram_id=90002, name='Other', gender='male', age=30,
        weight_kg=80.0, height_cm=180.0, goal_primary='strength',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['home'], onboarding_completed_at=datetime.utcnow(),
    )
    db.session.add(user2)
    db.session.commit()

    thread_id = client.post(
        '/api/coach/threads', headers=_h(app, user1.id), json={}
    ).get_json()['data']['thread_id']

    resp = client.get(f'/api/coach/threads/{thread_id}', headers=_h(app, user2.id))
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/coach/test_routes.py -k "thread" -v
```

Expected: all FAIL with 404 (routes not implemented)

- [ ] **Step 3: Implement CRUD routes**

Replace `app/modules/coach/routes.py` with:

```python
from datetime import datetime

from flask import Response, g, jsonify, request, stream_with_context

from app.core.auth import require_auth
from app.extensions import db
from . import bp
from .models import ChatMessage, ChatThread


@bp.route('/coach/threads', methods=['GET'])
@require_auth
def list_threads():
    threads = (ChatThread.query
               .filter_by(user_id=g.user_id)
               .order_by(ChatThread.updated_at.desc())
               .all())
    return jsonify({'success': True, 'data': [
        {'id': t.id, 'title': t.title, 'updated_at': t.updated_at.isoformat()}
        for t in threads
    ]})


@bp.route('/coach/threads', methods=['POST'])
@require_auth
def create_thread():
    thread = ChatThread(user_id=g.user_id)
    db.session.add(thread)
    db.session.commit()
    return jsonify({'success': True, 'data': {'thread_id': thread.id}})


@bp.route('/coach/threads/<int:thread_id>', methods=['GET'])
@require_auth
def get_thread(thread_id):
    thread = ChatThread.query.filter_by(id=thread_id, user_id=g.user_id).first()
    if not thread:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Thread not found'}}), 404
    messages = (ChatMessage.query
                .filter_by(thread_id=thread_id)
                .order_by(ChatMessage.created_at)
                .limit(100)
                .all())
    return jsonify({'success': True, 'data': {
        'id': thread.id,
        'title': thread.title,
        'messages': [
            {'role': m.role, 'content': m.content, 'created_at': m.created_at.isoformat()}
            for m in messages
        ],
    }})


@bp.route('/coach/threads/<int:thread_id>', methods=['DELETE'])
@require_auth
def delete_thread(thread_id):
    thread = ChatThread.query.filter_by(id=thread_id, user_id=g.user_id).first()
    if not thread:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Thread not found'}}), 404
    db.session.delete(thread)
    db.session.commit()
    return jsonify({'success': True})


@bp.route('/coach/threads/<int:thread_id>/generate-title', methods=['POST'])
@require_auth
def generate_title(thread_id):
    thread = ChatThread.query.filter_by(id=thread_id, user_id=g.user_id).first()
    if not thread:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Thread not found'}}), 404
    first_msg = (ChatMessage.query
                 .filter_by(thread_id=thread_id, role='user')
                 .order_by(ChatMessage.created_at)
                 .first())
    if not first_msg:
        return jsonify({'success': True, 'data': {'title': thread.title}})
    from app.core.ai import complete
    raw = complete(
        'Generate a short conversation title (4-6 words, Ukrainian). Return ONLY the title, no punctuation, no quotes.',
        first_msg.content,
        max_tokens=30,
        model='claude-haiku-4-5-20251001',
    ).strip()
    thread.title = raw
    db.session.commit()
    return jsonify({'success': True, 'data': {'title': raw}})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/coach/test_routes.py -k "thread" -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add app/modules/coach/routes.py tests/coach/test_routes.py
git commit -m "feat: coach CRUD endpoints — list/create/get/delete/generate-title"
```

---

## Task 4: Chat Streaming Endpoint

**Files:**
- Modify: `app/modules/coach/routes.py`

- [ ] **Step 1: Write failing test**

Add to `tests/coach/test_routes.py`:

```python
def test_chat_saves_messages(client, app, db, mock_anthropic):
    user = _make_user(db)
    h = _h(app, user.id)

    # Configure mock to return a stream of chunks
    mock_stream = MagicMock()
    mock_stream.__enter__ = lambda s: s
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.text_stream = iter(['Hello', ' there'])
    mock_anthropic.messages.stream.return_value = mock_stream

    thread_id = client.post('/api/coach/threads', headers=h, json={}).get_json()['data']['thread_id']

    resp = client.post(
        f'/api/coach/threads/{thread_id}/chat',
        headers=h,
        json={'message': 'Як покращити техніку присідань?'},
    )
    assert resp.status_code == 200

    # Both user and assistant messages should be saved
    msgs = ChatMessage.query.filter_by(thread_id=thread_id).order_by(ChatMessage.created_at).all()
    assert len(msgs) == 2
    assert msgs[0].role == 'user'
    assert msgs[0].content == 'Як покращити техніку присідань?'
    assert msgs[1].role == 'assistant'
    assert msgs[1].content == 'Hello there'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/coach/test_routes.py::test_chat_saves_messages -v
```

Expected: FAIL with 404 or 405 (route not implemented)

- [ ] **Step 3: Add chat endpoint to routes.py**

Add to the end of `app/modules/coach/routes.py`:

```python
@bp.route('/coach/threads/<int:thread_id>/chat', methods=['POST'])
@require_auth
def thread_chat(thread_id):
    thread = ChatThread.query.filter_by(id=thread_id, user_id=g.user_id).first()
    if not thread:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Thread not found'}}), 404

    data = request.json or {}
    user_message = (data.get('message') or '').strip()
    if not user_message:
        return jsonify({'success': False, 'error': {'code': 'EMPTY', 'message': 'Message required'}}), 400

    # Save user message
    user_msg = ChatMessage(thread_id=thread_id, role='user', content=user_message)
    db.session.add(user_msg)
    thread.updated_at = datetime.utcnow()
    db.session.commit()

    # Build conversation history (last 49 messages before this one)
    history_msgs = (ChatMessage.query
                    .filter(ChatMessage.thread_id == thread_id,
                            ChatMessage.id != user_msg.id)
                    .order_by(ChatMessage.created_at.desc())
                    .limit(49)
                    .all())[::-1]
    messages = [{'role': m.role, 'content': m.content} for m in history_msgs]
    messages.append({'role': 'user', 'content': user_message})

    from app.core.ai import get_client
    from .context import COACH_SYSTEM, build_coach_context
    system = COACH_SYSTEM + '\n\n' + build_coach_context(g.user_id)

    def generate():
        full_response = []
        with get_client().messages.stream(
            model='claude-sonnet-4-6',
            max_tokens=2048,
            system=system,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                full_response.append(text)
                yield f'data: {text}\n\n'

        ai_content = ''.join(full_response)
        ai_msg = ChatMessage(thread_id=thread_id, role='assistant', content=ai_content)
        db.session.add(ai_msg)
        thread.updated_at = datetime.utcnow()
        db.session.commit()

        yield 'data: [DONE]\n\n'

    return Response(stream_with_context(generate()), mimetype='text/event-stream')
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/coach/test_routes.py::test_chat_saves_messages -v
```

Expected: PASS

- [ ] **Step 5: Run all coach tests**

```bash
pytest tests/coach/ -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add app/modules/coach/routes.py
git commit -m "feat: coach SSE streaming chat endpoint"
```

---

## Task 5: Frontend HTML + CSS

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Add CSS before `/* ── MISC ── */`**

Find the line `/* ── MISC ── */` and insert before it:

```css
    /* ── COACH TAB ── */
    #panel-coach { overflow: hidden; padding: 0; gap: 0; }
    #coach-list-view { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
    #coach-thread-view { display: none; flex-direction: column; height: 100%; overflow: hidden; }

    .coach-list-header { display: flex; justify-content: space-between; align-items: center;
      padding: 14px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
    .coach-list-title { font-family: 'Barlow Condensed', sans-serif; font-size: 18px;
      font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
    .coach-new-btn { background: none; border: 1px solid var(--border); border-radius: 4px;
      color: var(--accent); font-size: 15px; padding: 5px 10px; cursor: pointer; }
    .coach-new-btn:active { border-color: var(--accent); }

    #coach-threads-container { flex: 1; overflow-y: auto; }
    .coach-thread-card { padding: 14px 16px; border-bottom: 1px solid var(--border);
      cursor: pointer; display: flex; justify-content: space-between; align-items: center; }
    .coach-thread-card:active { background: var(--card); }
    .coach-thread-card-title { font-size: 14px; color: var(--text); }
    .coach-thread-card-date { font-size: 11px; color: var(--muted); flex-shrink: 0; margin-left: 12px; }
    .coach-del-btn { background: none; border: none; color: #ff4444; font-size: 14px;
      padding: 4px 8px; cursor: pointer; display: none; }

    .coach-empty { display: flex; flex-direction: column; align-items: center;
      justify-content: center; padding: 60px 32px; text-align: center; flex: 1; }
    .coach-empty-title { font-family: 'Barlow Condensed', sans-serif; font-size: 20px;
      font-weight: 700; text-transform: uppercase; margin-bottom: 8px; }
    .coach-empty-sub { font-size: 13px; color: var(--muted); margin-bottom: 24px; line-height: 1.5; }

    .coach-thread-header { display: flex; align-items: center; gap: 10px; padding: 10px 14px;
      border-bottom: 1px solid var(--border); flex-shrink: 0; }
    .coach-back-btn { background: none; border: none; color: var(--accent); font-size: 20px;
      cursor: pointer; padding: 4px 6px; line-height: 1; }
    .coach-thread-title-text { font-family: 'Barlow Condensed', sans-serif; font-size: 15px;
      font-weight: 700; text-transform: uppercase; letter-spacing: .06em; flex: 1;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

    .coach-messages { flex: 1; overflow-y: auto; padding: 14px 14px 8px;
      display: flex; flex-direction: column; gap: 10px; }
    .coach-msg-user { align-self: flex-end; background: var(--accent); color: #fff;
      padding: 10px 14px; border-radius: 16px 16px 4px 16px; max-width: 82%;
      font-size: 14px; line-height: 1.5; word-break: break-word; }
    .coach-msg-ai { align-self: flex-start; background: var(--card);
      border: 1px solid var(--border); padding: 12px 14px;
      border-radius: 4px 16px 16px 16px; max-width: 92%;
      font-size: 14px; line-height: 1.6; word-break: break-word; }

    .coach-input-area { display: flex; align-items: flex-end; gap: 8px;
      padding: 8px 12px 10px; border-top: 1px solid var(--border); flex-shrink: 0; }
    #coach-input { flex: 1; background: var(--card); border: 1px solid var(--border);
      border-radius: 20px; color: var(--text); font-family: 'DM Sans', sans-serif;
      font-size: 14px; padding: 9px 16px; outline: none; resize: none;
      max-height: 110px; overflow-y: auto; line-height: 1.45; }
    #coach-input:focus { border-color: var(--accent); }
    .coach-send-btn { width: 38px; height: 38px; background: var(--accent); border: none;
      border-radius: 50%; color: #fff; font-size: 17px; cursor: pointer; flex-shrink: 0;
      display: flex; align-items: center; justify-content: center; transition: opacity .15s; }
    .coach-send-btn:disabled { opacity: .35; cursor: default; }

    @keyframes blink { 0%,100%{opacity:1}50%{opacity:0} }
    .coach-cursor { display: inline-block; animation: blink 1s infinite; }
```

- [ ] **Step 2: Replace coach tab HTML**

Find:
```html
    <div class="tab-panel" id="panel-coach">
      <div class="coming-soon"><div class="cs-line"></div><div class="cs-text">Coach</div><div class="cs-line"></div></div>
    </div>
```

Replace with:
```html
    <div class="tab-panel" id="panel-coach">
      <!-- Thread list view -->
      <div id="coach-list-view">
        <div class="coach-list-header">
          <span class="coach-list-title">Coach</span>
          <button class="coach-new-btn" onclick="newCoachThread()">✏</button>
        </div>
        <div id="coach-threads-container"></div>
      </div>
      <!-- Thread view -->
      <div id="coach-thread-view">
        <div class="coach-thread-header">
          <button class="coach-back-btn" onclick="showCoachList()">←</button>
          <span class="coach-thread-title-text" id="coach-thread-title-text">Coach</span>
        </div>
        <div class="coach-messages" id="coach-messages"></div>
        <div class="coach-input-area">
          <textarea id="coach-input" placeholder="Запитай свого коача..." rows="1"></textarea>
          <button class="coach-send-btn" id="coach-send-btn" onclick="sendCoachMessage()">↑</button>
        </div>
      </div>
    </div>
```

- [ ] **Step 3: Verify the app loads without JS errors**

Run `python run.py`, open the app, click the Coach tab. Should show the list header ("COACH") with a pencil button — no JS errors in console.

- [ ] **Step 4: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: coach tab HTML structure and CSS"
```

---

## Task 6: Frontend JS — Thread List

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Add state fields to `S` object**

Find the `S` object initialisation (starts with `const S = {`). Add these fields:

```javascript
  coachThreads: [],
  activeThread: null,
  coachStreaming: false,
```

- [ ] **Step 2: Hook into switchTab**

Find `function switchTab(name)` and add the coach hook:

```javascript
function switchTab(name) {
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelector(`[data-tab="${name}"]`).classList.add('active');
  document.getElementById(`panel-${name}`).classList.add('active');
  haptic();
  if (name === 'program') loadProgramTab();
  if (name === 'coach') loadCoachTab();
}
```

- [ ] **Step 3: Add thread list functions**

Add this block after the `openWeeklyReport` function (search for `function openWeeklyReport`):

```javascript
// ── COACH ──

async function loadCoachTab() {
  const r = await api('GET', '/api/coach/threads');
  S.coachThreads = r.success ? r.data : [];
  renderCoachList();
}

function renderCoachList() {
  const container = document.getElementById('coach-threads-container');
  if (!container) return;
  if (!S.coachThreads.length) {
    container.innerHTML = `<div class="coach-empty">
      <div class="coach-empty-title">Твій AI коач</div>
      <div class="coach-empty-sub">Техніка вправ · Програма · Відновлення<br>Харчування · Сон · Мотивація</div>
      <button class="btn btn-primary" onclick="newCoachThread()">ПОЧАТИ РОЗМОВУ</button>
    </div>`;
    return;
  }
  container.innerHTML = S.coachThreads.map(t => `
    <div class="coach-thread-card" id="tc-${t.id}" onclick="openCoachThread(${t.id})">
      <div class="coach-thread-card-title">${_esc(t.title)}</div>
      <div style="display:flex;align-items:center;gap:6px">
        <span class="coach-thread-card-date">${_coachRelDate(t.updated_at)}</span>
        <button class="coach-del-btn" id="cdel-${t.id}"
          onclick="event.stopPropagation();deleteCoachThread(${t.id})">✕</button>
      </div>
    </div>`).join('');

  // Long-press to reveal delete button
  container.querySelectorAll('.coach-thread-card').forEach(card => {
    let timer;
    card.addEventListener('touchstart', () => {
      timer = setTimeout(() => {
        const id = card.id.replace('tc-', '');
        const btn = document.getElementById('cdel-' + id);
        if (btn) btn.style.display = 'block';
      }, 500);
    });
    card.addEventListener('touchend', () => clearTimeout(timer));
    card.addEventListener('touchmove', () => clearTimeout(timer));
  });
}

function _coachRelDate(isoStr) {
  const d = new Date(isoStr);
  const diffH = Math.floor((Date.now() - d) / 3600000);
  if (diffH < 1) return 'щойно';
  if (diffH < 24) return diffH + ' год тому';
  const diffD = Math.floor(diffH / 24);
  if (diffD === 1) return 'вчора';
  return diffD + ' дн тому';
}

async function newCoachThread() {
  haptic();
  const r = await api('POST', '/api/coach/threads');
  if (!r.success) return;
  S.activeThread = {id: r.data.thread_id, title: 'Нова розмова', messages: []};
  _showCoachThread();
}

async function openCoachThread(id) {
  haptic();
  const r = await api('GET', `/api/coach/threads/${id}`);
  if (!r.success) { loadCoachTab(); return; }
  S.activeThread = r.data;
  _showCoachThread();
  _renderCoachMessages();
  const msgs = document.getElementById('coach-messages');
  if (msgs) msgs.scrollTop = msgs.scrollHeight;
}

function showCoachList() {
  document.getElementById('coach-thread-view').style.display = 'none';
  document.getElementById('coach-list-view').style.display = 'flex';
  loadCoachTab();
}

function _showCoachThread() {
  document.getElementById('coach-list-view').style.display = 'none';
  const tv = document.getElementById('coach-thread-view');
  tv.style.display = 'flex';
  document.getElementById('coach-thread-title-text').textContent =
    (S.activeThread.title || 'Нова розмова').slice(0, 40);
  document.getElementById('coach-messages').innerHTML = '';
  document.getElementById('coach-input').value = '';
  _setupCoachInput();
}

function _setupCoachInput() {
  const input = document.getElementById('coach-input');
  if (!input || input._coachSetup) return;
  input._coachSetup = true;
  input.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 110) + 'px';
  });
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendCoachMessage(); }
  });
}

async function deleteCoachThread(id) {
  if (!confirm('Видалити розмову?')) return;
  haptic();
  await api('DELETE', `/api/coach/threads/${id}`);
  S.coachThreads = S.coachThreads.filter(t => t.id !== id);
  renderCoachList();
}
```

- [ ] **Step 4: Manually verify thread list works**

Run the app. Click Coach tab. Should see the empty state. Click "ПОЧАТИ РОЗМОВУ" → should show an empty thread view with back button and input.

- [ ] **Step 5: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: coach tab JS — thread list, navigation, delete"
```

---

## Task 7: Frontend JS — Thread View + Messages Rendering

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Add `_renderCoachMessages` function**

Add after `deleteCoachThread`:

```javascript
function _renderCoachMessages() {
  const container = document.getElementById('coach-messages');
  if (!container || !S.activeThread) return;
  container.innerHTML = (S.activeThread.messages || []).map(m => {
    if (m.role === 'user') {
      return `<div class="coach-msg-user"><span>${_esc(m.content)}</span></div>`;
    }
    return `<div class="coach-msg-ai">${parseTechniqueMarkdown(m.content)}</div>`;
  }).join('');
}
```

- [ ] **Step 2: Verify existing threads render messages**

Open the app, create a thread via "ПОЧАТИ РОЗМОВУ". Go back to list, tap the thread. Messages area should be empty but visible. No errors.

- [ ] **Step 3: Commit**

```bash
git add app/templates/index.html
git commit -m "feat: coach thread view — message bubble rendering"
```

---

## Task 8: Frontend JS — SSE Streaming + Title Generation

**Files:**
- Modify: `app/templates/index.html`

- [ ] **Step 1: Add `sendCoachMessage` function**

Add after `_renderCoachMessages`:

```javascript
async function sendCoachMessage() {
  const input = document.getElementById('coach-input');
  const msg = (input.value || '').trim();
  if (!msg || S.coachStreaming || !S.activeThread) return;

  const isFirst = !(S.activeThread.messages?.length);

  input.value = '';
  input.style.height = 'auto';
  const container = document.getElementById('coach-messages');

  // Append user bubble immediately
  const userBubble = document.createElement('div');
  userBubble.className = 'coach-msg-user';
  userBubble.innerHTML = `<span>${_esc(msg)}</span>`;
  container.appendChild(userBubble);

  // Append AI bubble with blinking cursor
  const aiBubble = document.createElement('div');
  aiBubble.className = 'coach-msg-ai';
  aiBubble.innerHTML = '<span class="coach-cursor">▌</span>';
  container.appendChild(aiBubble);
  container.scrollTop = container.scrollHeight;

  S.coachStreaming = true;
  const sendBtn = document.getElementById('coach-send-btn');
  sendBtn.disabled = true;

  let aiText = '';

  try {
    const resp = await fetch(`/api/coach/threads/${S.activeThread.id}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(S.jwt ? {'Authorization': 'Bearer ' + S.jwt} : {}),
      },
      body: JSON.stringify({message: msg}),
    });

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete last line
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const chunk = line.slice(6);
        if (chunk === '[DONE]') break;
        aiText += chunk;
        aiBubble.innerHTML = parseTechniqueMarkdown(aiText) + '<span class="coach-cursor">▌</span>';
        container.scrollTop = container.scrollHeight;
      }
    }
  } catch (e) {
    aiText = 'Помилка з\'єднання. Спробуй ще раз.';
  }

  // Finalize bubble (remove cursor)
  aiBubble.innerHTML = parseTechniqueMarkdown(aiText);
  container.scrollTop = container.scrollHeight;

  S.coachStreaming = false;
  sendBtn.disabled = false;
  haptic('light');

  // Update local cache
  if (!S.activeThread.messages) S.activeThread.messages = [];
  S.activeThread.messages.push({role: 'user', content: msg});
  S.activeThread.messages.push({role: 'assistant', content: aiText});

  // Generate title after first exchange
  if (isFirst) {
    const titleR = await api('POST', `/api/coach/threads/${S.activeThread.id}/generate-title`);
    if (titleR.success && titleR.data?.title) {
      S.activeThread.title = titleR.data.title;
      document.getElementById('coach-thread-title-text').textContent =
        titleR.data.title.slice(0, 40);
    }
  }
}
```

- [ ] **Step 2: Run all backend tests to confirm nothing broke**

```bash
pytest tests/ -v
```

Expected: all PASS

- [ ] **Step 3: Manual end-to-end test**

1. Open app → Coach tab → "ПОЧАТИ РОЗМОВУ"
2. Type "Як правильно присідати?" → press Enter
3. Verify: user bubble appears, AI bubble streams in with cursor, cursor disappears when done
4. Verify: title updates in header after first exchange (e.g. "Техніка Присідань")
5. Press ← → see thread in list with new title and "щойно"
6. Tap thread → messages load and display correctly
7. Long-press thread → ✕ button appears → tap to delete → thread disappears

- [ ] **Step 4: Commit and push**

```bash
git add app/templates/index.html
git commit -m "feat: coach chat SSE streaming + title generation"
git push origin main
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|-----------------|------|
| ChatThread + ChatMessage models | Task 1 |
| 6 backend endpoints | Tasks 3 + 4 |
| build_coach_context with program + last workout + pain journal | Task 2 |
| COACH_SYSTEM multi-domain persona | Task 2 |
| Coach tab — list view with empty state | Task 5 + 6 |
| Thread view — back button, title | Task 5 + 6 |
| User bubbles right, AI bubbles left | Task 7 |
| SSE streaming with cursor | Task 8 |
| Markdown rendering in AI bubbles | Task 7 |
| Title auto-generated after first exchange | Task 8 |
| Long-press delete | Task 6 |
| Enter sends, Shift+Enter newline | Task 6 |
| Auto-resize textarea | Task 6 |
| Error handling (network error) | Task 8 |
| Thread not found → redirect to list | Task 6 |
| Empty message → ignore | Task 8 |

All requirements covered. No placeholders. Type names consistent across all tasks.
