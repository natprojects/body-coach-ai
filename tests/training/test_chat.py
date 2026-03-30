from unittest.mock import MagicMock
from app.core.models import User, AIConversation
from app.core.auth import create_jwt
from datetime import datetime


def _make_user(db):
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
    assert resp.content_type.startswith('text/event-stream')
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

    user_id = user.id
    token = create_jwt(user_id, app.config['SECRET_KEY'])
    resp = client.post('/api/training/chat',
                       json={'message': 'How many sets should I do?'},
                       headers={'Authorization': f'Bearer {token}'})
    _ = resp.data  # force generator consumption so save_message('assistant') runs

    msgs = AIConversation.query.filter_by(user_id=user_id, module='training').all()
    assert len(msgs) == 2
    assert msgs[0].role == 'user'
    assert msgs[1].role == 'assistant'
