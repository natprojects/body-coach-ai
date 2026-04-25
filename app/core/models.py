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
    app_language = db.Column(db.String(10), default='en')
    username = db.Column(db.String(100), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=True)
    onboarding_completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    active_module = db.Column(db.String(20), default='gym', nullable=False, server_default='gym')


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
    related_exercise_id = db.Column(db.Integer, nullable=True)  # soft ref to exercises.id (Task 7)
    notes = db.Column(db.Text)


class AIConversation(db.Model):
    __tablename__ = 'ai_conversations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    module = db.Column(db.String(50), nullable=False)  # training / nutrition / sleep / psychology
    role = db.Column(db.String(20), nullable=False)    # user / assistant
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
