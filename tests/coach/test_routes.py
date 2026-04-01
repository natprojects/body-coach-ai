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
