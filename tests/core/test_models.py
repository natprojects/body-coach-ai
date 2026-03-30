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
