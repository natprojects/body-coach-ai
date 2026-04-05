from datetime import date, timedelta, datetime
from app.core.models import User, DailyCheckin
from app.modules.nutrition.models import NutritionProfile, MealLog
from app.modules.nutrition.context import build_nutrition_context
from app.extensions import db


def _make_full_user(db):
    u = User(
        telegram_id=60001, name='CtxTest', gender='female', age=28,
        weight_kg=65.0, height_cm=168.0, goal_primary='fat_loss',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['home'], onboarding_completed_at=datetime.utcnow(),
    )
    db.session.add(u)
    db.session.commit()
    return u


def test_context_no_profile(app, db):
    user = _make_full_user(db)
    ctx = build_nutrition_context(user.id)
    assert 'not set up' in ctx


def test_context_with_profile(app, db):
    user = _make_full_user(db)
    p = NutritionProfile(
        user_id=user.id, diet_type='omnivore', allergies=['lactose'],
        calorie_target=1400.0, protein_g=130.0, fat_g=43.6, carbs_g=175.0,
        activity_outside='sedentary',
    )
    db.session.add(p)
    db.session.commit()
    ctx = build_nutrition_context(user.id)
    assert 'omnivore' in ctx
    assert '1400' in ctx
    assert 'lactose' in ctx


def test_context_includes_recent_meals(app, db):
    user = _make_full_user(db)
    today = date.today()
    db.session.add(MealLog(user_id=user.id, date=today, description='Вівсянка з ягодами'))
    db.session.add(MealLog(user_id=user.id, date=today - timedelta(days=10),
                           description='Стара страва'))
    db.session.commit()
    ctx = build_nutrition_context(user.id)
    assert 'Вівсянка з ягодами' in ctx
    assert 'Стара страва' not in ctx   # older than 7 days


def test_context_includes_todays_checkin(app, db):
    user = _make_full_user(db)
    checkin = DailyCheckin(user_id=user.id, date=date.today(), energy_level=7, sleep_quality=8)
    db.session.add(checkin)
    db.session.commit()
    ctx = build_nutrition_context(user.id)
    assert '7' in ctx   # energy level present
