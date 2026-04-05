# tests/nutrition/test_routes.py
from datetime import date, datetime
import pytest
from app.core.models import User
from app.modules.nutrition.models import NutritionProfile, MealLog
from app.extensions import db as _db


def _make_user(db):
    u = User(
        telegram_id=50001, name='NutrTest', gender='female', age=28,
        weight_kg=65.0, height_cm=168.0, goal_primary='fat_loss',
        level='beginner', training_days_per_week=3, session_duration_min=45,
        equipment=['home'], onboarding_completed_at=datetime.utcnow(),
    )
    db.session.add(u)
    db.session.commit()
    return u


def test_nutrition_profile_creation(app, db):
    user = _make_user(db)
    profile = NutritionProfile(
        user_id=user.id, diet_type='omnivore', allergies=['lactose'],
        cooking_skill='beginner', budget='medium', activity_outside='sedentary',
        bmr=1500.0, tdee=1800.0, calorie_target=1400.0,
        protein_g=130.0, fat_g=43.6, carbs_g=175.0,
    )
    db.session.add(profile)
    db.session.commit()
    fetched = NutritionProfile.query.filter_by(user_id=user.id).first()
    assert fetched is not None
    assert fetched.diet_type == 'omnivore'
    assert fetched.allergies == ['lactose']


def test_meal_log_creation(app, db):
    user = _make_user(db)
    log = MealLog(user_id=user.id, date=date.today(), description='Гречка з куркою')
    db.session.add(log)
    db.session.commit()
    fetched = MealLog.query.filter_by(user_id=user.id).first()
    assert fetched.description == 'Гречка з куркою'
