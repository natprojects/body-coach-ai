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
