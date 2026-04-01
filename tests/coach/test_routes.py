import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
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


def test_build_coach_context_returns_string(app, db):
    user = _make_user(db)
    from app.modules.coach.context import build_coach_context
    ctx = build_coach_context(user.id)
    assert isinstance(ctx, str)
    assert len(ctx) > 50


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


def test_chat_saves_messages(client, app, db):
    user = _make_user(db)
    h = _h(app, user.id)

    thread_id = client.post('/api/coach/threads', headers=h, json={}).get_json()['data']['thread_id']

    mock_stream = MagicMock()
    mock_stream.__enter__ = lambda s: s
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.text_stream = iter(['Hello', ' there'])

    with patch('app.modules.coach.routes.get_client') as mock_get_client:
        mock_get_client.return_value.messages.stream.return_value = mock_stream
        resp = client.post(
            f'/api/coach/threads/{thread_id}/chat',
            headers=h,
            json={'message': 'Як покращити техніку присідань?'},
        )
    assert resp.status_code == 200
    # Consume the SSE response body to force the generator to run to completion
    _ = resp.data

    msgs = ChatMessage.query.filter_by(thread_id=thread_id).order_by(ChatMessage.created_at).all()
    assert len(msgs) == 2
    assert msgs[0].role == 'user'
    assert msgs[0].content == 'Як покращити техніку присідань?'
    assert msgs[1].role == 'assistant'
    assert msgs[1].content == 'Hello there'
