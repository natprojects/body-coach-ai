from datetime import datetime, date
from app.extensions import db


class Program(db.Model):
    __tablename__ = 'programs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    periodization_type = db.Column(db.String(20), nullable=False)  # linear / wave / block
    total_weeks = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='active')  # active / completed / paused
    module = db.Column(db.String(20), default='gym', nullable=False, server_default='gym')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    mesocycles = db.relationship('Mesocycle', backref='program', order_by='Mesocycle.order_index',
                                 cascade='all, delete-orphan')


class Mesocycle(db.Model):
    __tablename__ = 'mesocycles'
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)  # Accumulation / Intensification / Deload
    order_index = db.Column(db.Integer, nullable=False)
    weeks_count = db.Column(db.Integer, nullable=False)

    weeks = db.relationship('ProgramWeek', backref='mesocycle', order_by='ProgramWeek.week_number',
                            cascade='all, delete-orphan')


class ProgramWeek(db.Model):
    __tablename__ = 'program_weeks'
    id = db.Column(db.Integer, primary_key=True)
    mesocycle_id = db.Column(db.Integer, db.ForeignKey('mesocycles.id'), nullable=False)
    week_number = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text)

    workouts = db.relationship('Workout', backref='week', order_by='Workout.order_index',
                               cascade='all, delete-orphan')


class Workout(db.Model):
    __tablename__ = 'workouts'
    id = db.Column(db.Integer, primary_key=True)
    program_week_id = db.Column(db.Integer, db.ForeignKey('program_weeks.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    mini_kind = db.Column(db.String(20))  # 'stretch' | 'short' | 'skill' for mini-sessions; NULL for main
    day_of_week = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    order_index = db.Column(db.Integer, nullable=False)
    target_muscle_groups = db.Column(db.String(200))
    estimated_duration_min = db.Column(db.Integer)
    warmup_notes = db.Column(db.Text)

    workout_exercises = db.relationship('WorkoutExercise', backref='workout',
                                        order_by='WorkoutExercise.order_index',
                                        cascade='all, delete-orphan')


class Exercise(db.Model):
    __tablename__ = 'exercises'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    muscle_group = db.Column(db.String(100))
    equipment_needed = db.Column(db.String(100))
    contraindications = db.Column(db.JSON)
    contraindication_severity = db.Column(db.String(20), default='none')  # none / caution / avoid
    mobility_requirements = db.Column(db.JSON)
    posture_considerations = db.Column(db.JSON)
    injury_modifications = db.Column(db.JSON)
    muscle_position = db.Column(db.String(20))  # stretched / shortened / mid
    is_corrective = db.Column(db.Boolean, default=False)
    is_prehab = db.Column(db.Boolean, default=False)
    technique_text = db.Column(db.Text)
    module = db.Column(db.String(20), default='gym', nullable=False, server_default='gym')
    progression_chain = db.Column(db.String(30))     # 'push' | 'pull' | 'squat' | 'core_dynamic' | 'core_static' | 'lunge'
    progression_level = db.Column(db.Integer)        # 0..N within chain
    unit = db.Column(db.String(10))                  # 'reps' | 'seconds'


class WorkoutExercise(db.Model):
    __tablename__ = 'workout_exercises'
    id = db.Column(db.Integer, primary_key=True)
    workout_id = db.Column(db.Integer, db.ForeignKey('workouts.id'), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey('exercises.id'), nullable=False)
    order_index = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text)
    tempo = db.Column(db.String(20))
    is_mandatory = db.Column(db.Boolean, default=True)
    selection_reason = db.Column(db.Text)
    expected_outcome = db.Column(db.Text)
    modifications_applied = db.Column(db.Text)

    planned_sets = db.relationship('PlannedSet', backref='workout_exercise',
                                   order_by='PlannedSet.set_number',
                                   cascade='all, delete-orphan')
    exercise = db.relationship('Exercise')


class PlannedSet(db.Model):
    __tablename__ = 'planned_sets'
    id = db.Column(db.Integer, primary_key=True)
    workout_exercise_id = db.Column(db.Integer, db.ForeignKey('workout_exercises.id'), nullable=False)
    set_number = db.Column(db.Integer, nullable=False)
    target_reps = db.Column(db.String(20))    # e.g. "8-10"
    target_weight_kg = db.Column(db.Float)
    target_rpe = db.Column(db.Float)
    rest_seconds = db.Column(db.Integer)
    is_amrap = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    target_seconds = db.Column(db.Integer)


class WorkoutSession(db.Model):
    __tablename__ = 'workout_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    workout_id = db.Column(db.Integer, db.ForeignKey('workouts.id'), nullable=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    status = db.Column(db.String(20), default='in_progress')  # in_progress / completed
    notes = db.Column(db.Text)
    ai_feedback = db.Column(db.Text)
    cycle_phase = db.Column(db.String(20), nullable=True)
    cycle_adapted = db.Column(db.Boolean, default=False)
    last_exercise_id = db.Column(db.Integer, db.ForeignKey('exercises.id'), nullable=True)
    module = db.Column(db.String(20), default='gym', nullable=False, server_default='gym')
    kind = db.Column(db.String(20), default='main', nullable=False, server_default='main')  # 'main' | 'mini'

    logged_exercises = db.relationship('LoggedExercise', backref='session',
                                       order_by='LoggedExercise.order_index',
                                       cascade='all, delete-orphan')


class LoggedExercise(db.Model):
    __tablename__ = 'logged_exercises'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('workout_sessions.id'), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey('exercises.id'), nullable=False)
    order_index = db.Column(db.Integer, nullable=False)

    logged_sets = db.relationship('LoggedSet', backref='logged_exercise',
                                  order_by='LoggedSet.set_number',
                                  cascade='all, delete-orphan')
    exercise = db.relationship('Exercise')


class LoggedSet(db.Model):
    __tablename__ = 'logged_sets'
    id = db.Column(db.Integer, primary_key=True)
    logged_exercise_id = db.Column(db.Integer, db.ForeignKey('logged_exercises.id'), nullable=False)
    set_number = db.Column(db.Integer, nullable=False)
    actual_reps = db.Column(db.Integer)
    actual_weight_kg = db.Column(db.Float)
    actual_rpe = db.Column(db.Float)
    actual_seconds = db.Column(db.Integer)
    notes = db.Column(db.Text)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow)


class ExerciseRecommendation(db.Model):
    __tablename__ = 'exercise_recommendations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    exercise_id = db.Column(db.Integer, db.ForeignKey('exercises.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('workout_sessions.id'), nullable=True)
    recommended_weight_kg = db.Column(db.Float)
    recommended_reps_min = db.Column(db.Integer)
    recommended_reps_max = db.Column(db.Integer)
    recommendation_type = db.Column(db.String(30), nullable=False)
    reason_text = db.Column(db.Text)
    is_applied = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    exercise = db.relationship('Exercise')
