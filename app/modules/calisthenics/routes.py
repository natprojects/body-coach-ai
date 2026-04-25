from flask import g, jsonify, request
from app.core.auth import require_auth
from app.extensions import db
from . import bp
from .models import CalisthenicsProfile, CalisthenicsAssessment

_VALID_GOALS = {'muscle', 'strength', 'skill', 'weight_loss', 'endurance'}
_VALID_EQUIPMENT = {'none', 'floor', 'bands', 'dumbbells', 'pullup_bar', 'dip_bars', 'rings', 'parallettes'}
_VALID_MOTIVATION = {'look', 'feel', 'achieve', 'health'}
_ALWAYS_REQUIRED_FIELDS = [
    'australian_pullups', 'pushups', 'pike_pushups', 'squats',
    'superman_hold', 'plank', 'hollow_body', 'lunges',
]


def _profile_to_dict(profile: CalisthenicsProfile) -> dict:
    return {
        'goals':                profile.goals or [],
        'equipment':            profile.equipment or [],
        'days_per_week':        profile.days_per_week,
        'session_duration_min': profile.session_duration_min,
        'injuries':             profile.injuries or [],
        'motivation':           profile.motivation,
    }


def _assessment_to_dict(a: CalisthenicsAssessment) -> dict:
    return {
        'id':                 a.id,
        'assessed_at':        a.assessed_at.isoformat(),
        'pullups':            a.pullups,
        'australian_pullups': a.australian_pullups,
        'pushups':            a.pushups,
        'pike_pushups':       a.pike_pushups,
        'squats':             a.squats,
        'superman_hold':      a.superman_hold,
        'plank':              a.plank,
        'hollow_body':        a.hollow_body,
        'lunges':             a.lunges,
        'notes':              a.notes,
    }


@bp.route('/calisthenics/profile', methods=['GET'])
@require_auth
def get_calisthenics_profile():
    profile = CalisthenicsProfile.query.filter_by(user_id=g.user_id).first()
    if not profile:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': _profile_to_dict(profile)})


@bp.route('/calisthenics/profile', methods=['POST'])
@require_auth
def set_calisthenics_profile():
    data = request.json or {}

    goals = data.get('goals')
    equipment = data.get('equipment', [])
    days_per_week = data.get('days_per_week')
    session_duration_min = data.get('session_duration_min')
    injuries = data.get('injuries', [])
    motivation = data.get('motivation')

    # Validate
    if not goals or not isinstance(goals, list) or not all(goal in _VALID_GOALS for goal in goals):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': f"goals must be a non-empty list from: {', '.join(sorted(_VALID_GOALS))}",
        }}), 400
    if not isinstance(equipment, list) or not all(eq in _VALID_EQUIPMENT for eq in equipment):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': f"equipment items must be from: {', '.join(sorted(_VALID_EQUIPMENT))}",
        }}), 400
    if not isinstance(days_per_week, int) or isinstance(days_per_week, bool) or not (1 <= days_per_week <= 7):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': 'days_per_week must be an integer between 1 and 7',
        }}), 400
    if not isinstance(session_duration_min, int) or isinstance(session_duration_min, bool) or not (15 <= session_duration_min <= 180):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': 'session_duration_min must be between 15 and 180',
        }}), 400
    if motivation not in _VALID_MOTIVATION:
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': f"motivation must be one of: {', '.join(sorted(_VALID_MOTIVATION))}",
        }}), 400

    profile = CalisthenicsProfile.query.filter_by(user_id=g.user_id).first()
    is_new = profile is None
    if is_new:
        profile = CalisthenicsProfile(user_id=g.user_id)
    profile.goals = goals
    profile.equipment = equipment
    profile.days_per_week = days_per_week
    profile.session_duration_min = session_duration_min
    profile.injuries = injuries
    profile.motivation = motivation
    if is_new:
        db.session.add(profile)
    db.session.commit()
    return jsonify({'success': True, 'data': _profile_to_dict(profile)})


@bp.route('/calisthenics/assessment', methods=['POST'])
@require_auth
def post_assessment():
    profile = CalisthenicsProfile.query.filter_by(user_id=g.user_id).first()
    if not profile:
        return jsonify({'success': False, 'error': {
            'code': 'PROFILE_REQUIRED',
            'message': 'Complete the calisthenics profile setup first',
        }}), 400

    data = request.json or {}

    # Validate always-required fields: must be int >= 0 (not bool)
    for field in _ALWAYS_REQUIRED_FIELDS:
        val = data.get(field)
        if not isinstance(val, int) or isinstance(val, bool) or val < 0:
            return jsonify({'success': False, 'error': {
                'code': 'INVALID_FIELD',
                'message': f"{field} must be an integer >= 0",
            }}), 400

    # pullups: None allowed (no equipment), or int >= 0
    pullups = data.get('pullups')
    if pullups is not None and (not isinstance(pullups, int) or isinstance(pullups, bool) or pullups < 0):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': 'pullups must be an integer >= 0 or null',
        }}), 400

    assessment = CalisthenicsAssessment(
        user_id=g.user_id,
        pullups=pullups,
        australian_pullups=data['australian_pullups'],
        pushups=data['pushups'],
        pike_pushups=data['pike_pushups'],
        squats=data['squats'],
        superman_hold=data['superman_hold'],
        plank=data['plank'],
        hollow_body=data['hollow_body'],
        lunges=data['lunges'],
        notes=data.get('notes'),
    )
    db.session.add(assessment)
    db.session.commit()
    return jsonify({'success': True, 'data': _assessment_to_dict(assessment)})


@bp.route('/calisthenics/assessment/history', methods=['GET'])
@require_auth
def get_assessment_history():
    assessments = (CalisthenicsAssessment.query
                   .filter_by(user_id=g.user_id)
                   .order_by(CalisthenicsAssessment.assessed_at.desc())
                   .all())
    return jsonify({'success': True, 'data': [_assessment_to_dict(a) for a in assessments]})


from app.core.models import User
from app.modules.training.models import (
    Program, Mesocycle, ProgramWeek, Workout, Exercise, WorkoutExercise, PlannedSet, WorkoutSession,
)
from .coach import generate_calisthenics_program, save_calisthenics_program_from_dict


def _serialize_program(program: Program) -> dict:
    """Serialize a Program with full hierarchy."""
    return {
        'id': program.id,
        'name': program.name,
        'periodization_type': program.periodization_type,
        'total_weeks': program.total_weeks,
        'status': program.status,
        'module': program.module,
        'created_at': program.created_at.isoformat() if program.created_at else None,
        'mesocycles': [{
            'id': m.id,
            'name': m.name,
            'order_index': m.order_index,
            'weeks_count': m.weeks_count,
            'weeks': [{
                'id': w.id,
                'week_number': w.week_number,
                'notes': w.notes,
                'workouts': [{
                    'id': wo.id,
                    'day_of_week': wo.day_of_week,
                    'name': wo.name,
                    'order_index': wo.order_index,
                    'target_muscle_groups': wo.target_muscle_groups,
                    'estimated_duration_min': wo.estimated_duration_min,
                    'warmup_notes': wo.warmup_notes,
                    'exercises': [{
                        'id': we.id,
                        'exercise_id': we.exercise_id,
                        'exercise_name': db.session.get(Exercise, we.exercise_id).name,
                        'order_index': we.order_index,
                        'tempo': we.tempo,
                        'is_mandatory': we.is_mandatory,
                        'notes': we.notes,
                        'sets': [{
                            'id': ps.id,
                            'set_number': ps.set_number,
                            'target_reps': ps.target_reps,
                            'target_seconds': ps.target_seconds,
                            'target_rpe': ps.target_rpe,
                            'rest_seconds': ps.rest_seconds,
                            'is_amrap': ps.is_amrap,
                        } for ps in PlannedSet.query.filter_by(
                            workout_exercise_id=we.id
                        ).order_by(PlannedSet.set_number).all()],
                    } for we in sorted(wo.workout_exercises, key=lambda x: x.order_index)],
                } for wo in sorted(w.workouts, key=lambda x: x.order_index)],
            } for w in sorted(m.weeks, key=lambda x: x.week_number)],
        } for m in sorted(program.mesocycles, key=lambda x: x.order_index)],
    }


@bp.route('/calisthenics/program/generate', methods=['POST'])
@require_auth
def post_generate_program():
    user = db.session.get(User, g.user_id)
    profile = CalisthenicsProfile.query.filter_by(user_id=g.user_id).first()
    if not profile:
        return jsonify({'success': False, 'error': {
            'code': 'PROFILE_REQUIRED',
            'message': 'Complete the calisthenics profile setup first',
        }}), 400

    last_assessment = (CalisthenicsAssessment.query
                       .filter_by(user_id=g.user_id)
                       .order_by(CalisthenicsAssessment.assessed_at.desc())
                       .first())
    if not last_assessment:
        return jsonify({'success': False, 'error': {
            'code': 'ASSESSMENT_REQUIRED',
            'message': 'Take the assessment first',
        }}), 400

    try:
        program_dict = generate_calisthenics_program(user, profile, last_assessment)
        program = save_calisthenics_program_from_dict(g.user_id, program_dict)
    except ValueError as e:
        return jsonify({'success': False, 'error': {
            'code': 'AI_GENERATION_FAILED',
            'message': str(e),
        }}), 500

    return jsonify({'success': True, 'data': _serialize_program(program)})


@bp.route('/calisthenics/program/active', methods=['GET'])
@require_auth
def get_active_program():
    program = Program.query.filter_by(
        user_id=g.user_id, module='calisthenics', status='active'
    ).first()
    if not program:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': _serialize_program(program)})


from datetime import date, timedelta


def _serialize_workout_with_exercises(workout: Workout, ad_hoc: bool = False) -> dict:
    return {
        'id': workout.id,
        'name': workout.name,
        'day_of_week': workout.day_of_week,
        'target_muscle_groups': workout.target_muscle_groups,
        'estimated_duration_min': workout.estimated_duration_min,
        'warmup_notes': workout.warmup_notes,
        'ad_hoc': ad_hoc,
        'exercises': [{
            'id': we.id,
            'exercise_id': we.exercise_id,
            'exercise_name': db.session.get(Exercise, we.exercise_id).name,
            'unit': db.session.get(Exercise, we.exercise_id).unit,
            'order_index': we.order_index,
            'tempo': we.tempo,
            'notes': we.notes,
            'sets': [{
                'id': ps.id, 'set_number': ps.set_number,
                'target_reps': ps.target_reps, 'target_seconds': ps.target_seconds,
                'target_rpe': ps.target_rpe, 'rest_seconds': ps.rest_seconds,
                'is_amrap': ps.is_amrap,
            } for ps in PlannedSet.query.filter_by(
                workout_exercise_id=we.id
            ).order_by(PlannedSet.set_number).all()],
        } for we in sorted(workout.workout_exercises, key=lambda x: x.order_index)],
    }


def _get_active_calisthenics_workout(program, user_id, today):
    """Return (workout, ad_hoc, rest_day). rest_day=True when all week workouts are done."""
    week = (ProgramWeek.query.join(Mesocycle).filter(Mesocycle.program_id == program.id).first())
    if not week:
        return None, False, False
    today_dow = today.weekday()
    week_start = today - timedelta(days=today_dow)

    week_workouts = (Workout.query.filter_by(program_week_id=week.id)
                     .order_by(Workout.order_index).all())
    if not week_workouts:
        return None, False, False

    completed_ids = {
        s.workout_id for s in WorkoutSession.query.filter(
            WorkoutSession.user_id == user_id,
            WorkoutSession.module == 'calisthenics',
            WorkoutSession.status == 'completed',
            WorkoutSession.date >= week_start,
            WorkoutSession.workout_id.in_([w.id for w in week_workouts]),
        ).all()
    }

    scheduled = Workout.query.filter_by(program_week_id=week.id, day_of_week=today_dow).first()
    if scheduled and scheduled.id not in completed_ids:
        return scheduled, False, False

    for w in week_workouts:
        if w.id not in completed_ids:
            ad_hoc = not (scheduled and w.id == scheduled.id)
            return w, ad_hoc, False
    return None, False, True  # all done → rest


@bp.route('/calisthenics/today', methods=['GET'])
@require_auth
def get_today():
    program = Program.query.filter_by(
        user_id=g.user_id, module='calisthenics', status='active'
    ).first()
    if not program:
        return jsonify({'success': True, 'data': None})
    workout, ad_hoc, rest_day = _get_active_calisthenics_workout(program, g.user_id, date.today())
    if rest_day:
        return jsonify({'success': True, 'data': {'rest_day': True}})
    if not workout:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': _serialize_workout_with_exercises(workout, ad_hoc=ad_hoc)})


from app.modules.training.models import LoggedExercise, LoggedSet
from .level_up import compute_level_up_suggestions


@bp.route('/calisthenics/session/start', methods=['POST'])
@require_auth
def post_session_start():
    data = request.json or {}
    workout_id = data.get('workout_id')
    if not isinstance(workout_id, int):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD', 'message': 'workout_id required',
        }}), 400

    workout = db.session.get(Workout, workout_id)
    if not workout:
        return jsonify({'success': False, 'error': {
            'code': 'WORKOUT_NOT_FOUND', 'message': 'Workout not found',
        }}), 404

    # Find program for this workout
    program = (Program.query
               .join(Mesocycle).join(ProgramWeek)
               .filter(ProgramWeek.id == workout.program_week_id)
               .first())
    if not program or program.user_id != g.user_id:
        return jsonify({'success': False, 'error': {
            'code': 'WORKOUT_NOT_FOUND', 'message': 'Workout not found',
        }}), 404
    if program.module != 'calisthenics':
        return jsonify({'success': False, 'error': {
            'code': 'MODULE_MISMATCH',
            'message': 'This workout belongs to a different module',
        }}), 400

    session = WorkoutSession(
        user_id=g.user_id, workout_id=workout_id,
        module='calisthenics', status='in_progress',
        date=date.today(),
    )
    db.session.add(session)
    db.session.commit()
    return jsonify({'success': True, 'data': {'session_id': session.id}})


@bp.route('/calisthenics/session/<int:session_id>/log-set', methods=['POST'])
@require_auth
def post_log_set(session_id):
    session = WorkoutSession.query.filter_by(
        id=session_id, user_id=g.user_id, module='calisthenics'
    ).first()
    if not session:
        return jsonify({'success': False, 'error': {
            'code': 'SESSION_NOT_FOUND', 'message': 'Session not found',
        }}), 404

    data = request.json or {}
    we_id = data.get('workout_exercise_id')
    set_number = data.get('set_number')
    actual_reps = data.get('actual_reps')
    actual_seconds = data.get('actual_seconds')

    if not isinstance(we_id, int) or not isinstance(set_number, int):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': 'workout_exercise_id and set_number required',
        }}), 400
    if actual_reps is None and actual_seconds is None:
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': 'Either actual_reps or actual_seconds required',
        }}), 400

    we = db.session.get(WorkoutExercise, we_id)
    if not we:
        return jsonify({'success': False, 'error': {
            'code': 'WORKOUT_EXERCISE_NOT_FOUND', 'message': 'Not found',
        }}), 404

    # Upsert LoggedExercise for this session+exercise pair
    le = LoggedExercise.query.filter_by(
        session_id=session.id, exercise_id=we.exercise_id
    ).first()
    if not le:
        le = LoggedExercise(
            session_id=session.id,
            exercise_id=we.exercise_id,
            order_index=we.order_index,
        )
        db.session.add(le)
        db.session.flush()

    # Upsert LoggedSet
    log = LoggedSet.query.filter_by(
        logged_exercise_id=le.id, set_number=set_number
    ).first()
    is_new = log is None
    if is_new:
        log = LoggedSet(logged_exercise_id=le.id, set_number=set_number)
    log.actual_reps = actual_reps
    log.actual_seconds = actual_seconds
    log.actual_weight_kg = None
    if is_new:
        db.session.add(log)
    db.session.commit()
    return jsonify({'success': True, 'data': {'log_id': log.id}})


@bp.route('/calisthenics/session/<int:session_id>/complete', methods=['POST'])
@require_auth
def post_complete(session_id):
    session = WorkoutSession.query.filter_by(
        id=session_id, user_id=g.user_id, module='calisthenics'
    ).first()
    if not session:
        return jsonify({'success': False, 'error': {
            'code': 'SESSION_NOT_FOUND', 'message': 'Session not found',
        }}), 404

    session.status = 'completed'
    db.session.commit()

    program = Program.query.filter_by(
        user_id=g.user_id, module='calisthenics', status='active'
    ).first()
    suggestions = compute_level_up_suggestions(g.user_id, program) if program else []

    return jsonify({'success': True, 'data': {'level_up_suggestions': suggestions}})


@bp.route('/calisthenics/program/<int:program_id>/level-up', methods=['POST'])
@require_auth
def post_level_up(program_id):
    program = Program.query.filter_by(
        id=program_id, user_id=g.user_id, module='calisthenics', status='active'
    ).first()
    if not program:
        return jsonify({'success': False, 'error': {
            'code': 'PROGRAM_NOT_FOUND', 'message': 'Program not found',
        }}), 404

    data = request.json or {}
    from_id = data.get('from_exercise_id')
    to_id = data.get('to_exercise_id')

    suggestions = compute_level_up_suggestions(g.user_id, program)
    valid = any(s['exercise_id_current'] == from_id and s['exercise_id_next'] == to_id
                for s in suggestions)
    if not valid:
        return jsonify({'success': False, 'error': {
            'code': 'LEVEL_UP_NOT_READY',
            'message': 'Promotion criteria not met',
        }}), 400

    new_ex = Exercise.query.filter_by(id=to_id, module='calisthenics').first()
    if not new_ex:
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_EXERCISE', 'message': 'Target exercise invalid',
        }}), 400

    workout_exercises = (WorkoutExercise.query
                         .join(Workout).join(ProgramWeek).join(Mesocycle)
                         .filter(Mesocycle.program_id == program_id,
                                 WorkoutExercise.exercise_id == from_id)
                         .all())
    for we in workout_exercises:
        we.exercise_id = to_id
        for ps in PlannedSet.query.filter_by(workout_exercise_id=we.id).all():
            if new_ex.unit == 'seconds':
                ps.target_reps = None
                ps.target_seconds = max(15, (ps.target_seconds or 30) - 10)
            else:
                ps.target_reps = '6-10'
                ps.target_seconds = None
            ps.target_weight_kg = None

    db.session.commit()
    return jsonify({'success': True, 'data': {'swapped_count': len(workout_exercises)}})


@bp.route('/calisthenics/program/<int:program_id>/regenerate', methods=['POST'])
@require_auth
def post_regenerate(program_id):
    user = db.session.get(User, g.user_id)
    program = Program.query.filter_by(
        id=program_id, user_id=g.user_id, module='calisthenics'
    ).first()
    if not program:
        return jsonify({'success': False, 'error': {
            'code': 'PROGRAM_NOT_FOUND', 'message': 'Program not found',
        }}), 404

    profile = CalisthenicsProfile.query.filter_by(user_id=g.user_id).first()
    last_assessment = (CalisthenicsAssessment.query
                       .filter_by(user_id=g.user_id)
                       .order_by(CalisthenicsAssessment.assessed_at.desc())
                       .first())
    if not profile or not last_assessment:
        return jsonify({'success': False, 'error': {
            'code': 'ASSESSMENT_REQUIRED',
            'message': 'Take the assessment again before regenerating',
        }}), 400

    try:
        program_dict = generate_calisthenics_program(user, profile, last_assessment)
        new_program = save_calisthenics_program_from_dict(g.user_id, program_dict)
    except ValueError as e:
        return jsonify({'success': False, 'error': {
            'code': 'AI_GENERATION_FAILED', 'message': str(e),
        }}), 500

    return jsonify({'success': True, 'data': _serialize_program(new_program)})
