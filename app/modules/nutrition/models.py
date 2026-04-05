from datetime import datetime
from app.extensions import db


class NutritionProfile(db.Model):
    __tablename__ = 'nutrition_profiles'
    id               = db.Column(db.Integer, primary_key=True)
    user_id          = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    diet_type        = db.Column(db.String(20))
    allergies        = db.Column(db.JSON)
    cooking_skill    = db.Column(db.String(20))
    budget           = db.Column(db.String(20))
    activity_outside = db.Column(db.String(20))
    bmr              = db.Column(db.Float)
    tdee             = db.Column(db.Float)
    calorie_target   = db.Column(db.Float)
    protein_g        = db.Column(db.Float)
    fat_g            = db.Column(db.Float)
    carbs_g          = db.Column(db.Float)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class MealLog(db.Model):
    __tablename__ = 'meal_logs'
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date        = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=False)
    logged_at   = db.Column(db.DateTime, default=datetime.utcnow)
