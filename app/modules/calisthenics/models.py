from datetime import datetime
from app.extensions import db


class CalisthenicsProfile(db.Model):
    __tablename__ = 'calisthenics_profiles'
    id                   = db.Column(db.Integer, primary_key=True)
    user_id              = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    goals                = db.Column(db.JSON)
    # ['muscle', 'strength', 'skill', 'weight_loss', 'endurance']
    equipment            = db.Column(db.JSON)
    # ['none', 'floor', 'bands', 'dumbbells', 'pullup_bar', 'dip_bars', 'rings', 'parallettes']
    days_per_week        = db.Column(db.Integer)
    session_duration_min = db.Column(db.Integer)
    injuries             = db.Column(db.JSON)
    motivation           = db.Column(db.String(50))
    # 'look' | 'feel' | 'achieve' | 'health'
    optional_target_per_week = db.Column(db.Integer, default=0, nullable=False, server_default='0')
    updated_at           = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CalisthenicsAssessment(db.Model):
    __tablename__ = 'calisthenics_assessments'
    id                  = db.Column(db.Integer, primary_key=True)
    user_id             = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assessed_at         = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    pullups             = db.Column(db.Integer, nullable=True)
    australian_pullups  = db.Column(db.Integer, nullable=True)
    pushups             = db.Column(db.Integer, nullable=True)
    pike_pushups        = db.Column(db.Integer, nullable=True)
    squats              = db.Column(db.Integer, nullable=True)
    superman_hold       = db.Column(db.Integer, nullable=True)
    plank               = db.Column(db.Integer, nullable=True)
    hollow_body         = db.Column(db.Integer, nullable=True)
    lunges              = db.Column(db.Integer, nullable=True)
    notes               = db.Column(db.Text, nullable=True)
