from datetime import datetime, date, timedelta
from flask import g, jsonify, request, Response, stream_with_context
from app.core.auth import require_auth
from app.core.ai import stream_chat
from app.core.models import User
from app.extensions import db
from . import bp
from .onboarding import ONBOARDING_STEPS, apply_step, get_first_step, get_next_step
from .coach import build_training_context, generate_program, save_program_from_dict
from .models import Program, Mesocycle, LoggedExercise, LoggedSet, Workout, WorkoutSession, ProgramWeek
from .progress import generate_post_workout_feedback, generate_weekly_report


# ── Onboarding ────────────────────────────────────────────────────────────────

@bp.route('/onboarding/status', methods=['GET'])
@require_auth
def onboarding_status():
    user = User.query.get(g.user_id)
    completed = user.onboarding_completed_at is not None
    return jsonify({'success': True, 'data': {
        'completed': completed,
        'next_step': None if completed else get_first_step(user),
        'steps': ONBOARDING_STEPS,
    }})


@bp.route('/onboarding/step', methods=['POST'])
@require_auth
def onboarding_step():
    user = User.query.get(g.user_id)
    data = request.json or {}
    step = data.get('step')
    step_data = data.get('data', {})
    try:
        apply_step(user, step, step_data)
    except ValueError as e:
        return jsonify({'success': False, 'error': {'code': 'BAD_REQUEST', 'message': str(e)}}), 400
    next_step = get_next_step(user, step)
    return jsonify({'success': True, 'data': {'next_step': next_step}})


@bp.route('/onboarding/complete', methods=['POST'])
@require_auth
def onboarding_complete():
    user = User.query.get(g.user_id)
    user.onboarding_completed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({'success': True, 'data': {'completed': True}})


# ── Ping (keep for health check) ───────────────────────────────────────────────

@bp.route('/training/ping', methods=['GET'])
def ping():
    return jsonify({'success': True, 'data': 'training module online'})


# ── Program ───────────────────────────────────────────────────────────────────

@bp.route('/training/program/generate', methods=['POST'])
@require_auth
def program_generate():
    user = db.session.get(User, g.user_id)
    if not user.onboarding_completed_at:
        return jsonify({'success': False, 'error': {
            'code': 'BAD_REQUEST', 'message': 'Complete onboarding first'
        }}), 400
    try:
        program_dict = generate_program(user)
    except ValueError as e:
        return jsonify({'success': False, 'error': {
            'code': 'AI_ERROR', 'message': 'Failed to generate program. Please try again.'
        }}), 500
    program = save_program_from_dict(user.id, program_dict)
    return jsonify({'success': True, 'data': {
        'program_id': program.id,
        'name': program.name,
        'total_weeks': program.total_weeks,
        'periodization_type': program.periodization_type,
    }})


@bp.route('/training/program/current', methods=['GET'])
@require_auth
def program_current():
    program = Program.query.filter_by(user_id=g.user_id, status='active').first()
    if not program:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': _serialize_program(program)})


@bp.route('/training/program/week/<int:week_num>', methods=['GET'])
@require_auth
def program_week(week_num):
    program = Program.query.filter_by(user_id=g.user_id, status='active').first()
    if not program:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'No active program'}}), 404
    from .models import ProgramWeek
    week = (ProgramWeek.query
            .join(Mesocycle)
            .filter(Mesocycle.program_id == program.id, ProgramWeek.week_number == week_num)
            .first())
    if not week:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': f'Week {week_num} not found'}}), 404
    return jsonify({'success': True, 'data': _serialize_week(week)})


def _serialize_program(program):
    return {
        'id': program.id,
        'name': program.name,
        'periodization_type': program.periodization_type,
        'total_weeks': program.total_weeks,
        'status': program.status,
        'mesocycles': [{
            'id': m.id, 'name': m.name, 'order_index': m.order_index, 'weeks_count': m.weeks_count
        } for m in program.mesocycles],
    }


def _serialize_week(week):
    return {
        'week_number': week.week_number,
        'notes': week.notes,
        'workouts': [{
            'id': w.id, 'day_of_week': w.day_of_week, 'name': w.name,
            'exercises': [{
                'exercise_name': we.exercise.name,
                'notes': we.notes,
                'sets': [{
                    'set_number': ps.set_number,
                    'target_reps': ps.target_reps,
                    'target_weight_kg': ps.target_weight_kg,
                    'target_rpe': ps.target_rpe,
                    'rest_seconds': ps.rest_seconds,
                } for ps in we.planned_sets]
            } for we in w.workout_exercises]
        } for w in week.workouts]
    }


# ── Today's workout ───────────────────────────────────────────────────────────

@bp.route('/training/today', methods=['GET'])
@require_auth
def training_today():
    program = Program.query.filter_by(user_id=g.user_id, status='active').first()
    if not program:
        return jsonify({'success': True, 'data': None})

    today_dow = date.today().weekday()
    days_elapsed = (date.today() - program.created_at.date()).days
    current_week_num = (days_elapsed // 7) + 1

    week = (ProgramWeek.query
            .join(Mesocycle)
            .filter(Mesocycle.program_id == program.id, ProgramWeek.week_number == current_week_num)
            .first())
    if not week:
        return jsonify({'success': True, 'data': None})

    workout = Workout.query.filter_by(program_week_id=week.id, day_of_week=today_dow).first()
    if not workout:
        return jsonify({'success': True, 'data': {'rest_day': True}})

    return jsonify({'success': True, 'data': _serialize_workout_with_sets(workout)})


def _serialize_workout_with_sets(workout: Workout) -> dict:
    return {
        'id': workout.id,
        'name': workout.name,
        'day_of_week': workout.day_of_week,
        'exercises': [{
            'exercise_id': we.exercise_id,
            'exercise_name': we.exercise.name,
            'order_index': we.order_index,
            'sets': [{
                'set_number': ps.set_number,
                'target_reps': ps.target_reps,
                'target_weight_kg': ps.target_weight_kg,
                'target_rpe': ps.target_rpe,
                'rest_seconds': ps.rest_seconds,
            } for ps in we.planned_sets]
        } for we in workout.workout_exercises]
    }


# ── Session ───────────────────────────────────────────────────────────────────

@bp.route('/training/session/start', methods=['POST'])
@require_auth
def session_start():
    data = request.json or {}
    session = WorkoutSession(
        user_id=g.user_id,
        workout_id=data.get('workout_id'),
        date=date.today(),
        status='in_progress',
    )
    db.session.add(session)
    db.session.commit()
    return jsonify({'success': True, 'data': {'session_id': session.id}})


@bp.route('/training/session/log-set', methods=['POST'])
@require_auth
def session_log_set():
    data = request.json or {}
    session_id = data.get('session_id')
    exercise_id = data.get('exercise_id')

    # Verify session belongs to authenticated user
    session = WorkoutSession.query.filter_by(id=session_id, user_id=g.user_id).first()
    if not session:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Session not found'}}), 404

    le = LoggedExercise.query.filter_by(session_id=session_id, exercise_id=exercise_id).first()
    if not le:
        existing_count = LoggedExercise.query.filter_by(session_id=session_id).count()
        le = LoggedExercise(session_id=session_id, exercise_id=exercise_id, order_index=existing_count)
        db.session.add(le)
        db.session.flush()

    ls = LoggedSet(
        logged_exercise_id=le.id,
        set_number=data.get('set_number', 1),
        actual_reps=data.get('actual_reps'),
        actual_weight_kg=data.get('actual_weight_kg'),
        actual_rpe=data.get('actual_rpe'),
        notes=data.get('notes'),
    )
    db.session.add(ls)
    db.session.commit()
    return jsonify({'success': True, 'data': {'logged_set_id': ls.id}})


@bp.route('/training/session/complete', methods=['POST'])
@require_auth
def session_complete():
    data = request.json or {}
    session = WorkoutSession.query.filter_by(id=data.get('session_id'), user_id=g.user_id).first()
    if not session:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Session not found'}}), 404

    session.status = 'completed'
    db.session.commit()

    feedback = generate_post_workout_feedback(session, g.user_id)
    session.ai_feedback = feedback
    db.session.commit()

    return jsonify({'success': True, 'data': {
        'session_id': session.id,
        'feedback': feedback,
    }})


@bp.route('/training/session/<int:session_id>', methods=['GET'])
@require_auth
def session_detail(session_id):
    session = WorkoutSession.query.filter_by(id=session_id, user_id=g.user_id).first()
    if not session:
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': 'Session not found'}}), 404
    return jsonify({'success': True, 'data': {
        'id': session.id,
        'date': session.date.isoformat(),
        'status': session.status,
        'ai_feedback': session.ai_feedback,
        'exercises': [{
            'exercise_name': le.exercise.name,
            'sets': [{
                'set_number': s.set_number,
                'actual_reps': s.actual_reps,
                'actual_weight_kg': s.actual_weight_kg,
                'actual_rpe': s.actual_rpe,
            } for s in le.logged_sets]
        } for le in session.logged_exercises]
    }})


# ── Progress ──────────────────────────────────────────────────────────────────

@bp.route('/training/progress/weekly', methods=['GET'])
@require_auth
def progress_weekly():
    since = date.today() - timedelta(days=7)
    sessions = (WorkoutSession.query
                .filter(WorkoutSession.user_id == g.user_id,
                        WorkoutSession.date >= since,
                        WorkoutSession.status == 'completed')
                .order_by(WorkoutSession.date)
                .all())
    report = generate_weekly_report(g.user_id, sessions)
    return jsonify({'success': True, 'data': {'report': report}})


@bp.route('/training/progress/history', methods=['GET'])
@require_auth
def progress_history():
    sessions = (WorkoutSession.query
                .filter_by(user_id=g.user_id)
                .order_by(WorkoutSession.date.desc())
                .limit(50)
                .all())
    return jsonify({'success': True, 'data': [{
        'id': s.id, 'date': s.date.isoformat(),
        'status': s.status, 'workout_id': s.workout_id,
    } for s in sessions]})


# ── AI Chat ───────────────────────────────────────────────────────────────────

@bp.route('/training/chat', methods=['POST'])
@require_auth
def training_chat():
    data = request.json or {}
    message = data.get('message', '')
    session_id = data.get('session_id')  # optional

    extra_context = build_training_context(g.user_id, session_id=session_id)

    def generate():
        for chunk in stream_chat(g.user_id, 'training', message, extra_context=extra_context):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


def _serialize_program_full(program):
    from datetime import date
    from .models import WorkoutExercise, Workout, ProgramWeek
    days_elapsed = (date.today() - program.created_at.date()).days
    current_week = (days_elapsed // 7) + 1

    total_wes = (WorkoutExercise.query
                 .join(Workout).join(ProgramWeek).join(Mesocycle)
                 .filter(Mesocycle.program_id == program.id).count())
    filled_wes = (WorkoutExercise.query
                  .join(Workout).join(ProgramWeek).join(Mesocycle)
                  .filter(Mesocycle.program_id == program.id,
                          WorkoutExercise.selection_reason.isnot(None)).count())
    insights_generated = total_wes > 0 and filled_wes == total_wes

    return {
        'id': program.id,
        'name': program.name,
        'periodization_type': program.periodization_type,
        'total_weeks': program.total_weeks,
        'current_week': current_week,
        'insights_generated': insights_generated,
        'mesocycles': [{
            'id': m.id,
            'name': m.name,
            'order_index': m.order_index,
            'weeks_count': m.weeks_count,
            'weeks': [{
                'week_number': w.week_number,
                'notes': w.notes,
                'workouts': [{
                    'id': wo.id,
                    'name': wo.name,
                    'day_of_week': wo.day_of_week,
                    'order_index': wo.order_index,
                    'exercises': [{
                        'workout_exercise_id': we.id,
                        'exercise_name': we.exercise.name,
                        'order_index': we.order_index,
                        'selection_reason': we.selection_reason,
                        'expected_outcome': we.expected_outcome,
                        'modifications_applied': we.modifications_applied,
                        'sets': [{
                            'set_number': ps.set_number,
                            'target_reps': ps.target_reps,
                            'target_weight_kg': ps.target_weight_kg,
                            'target_rpe': ps.target_rpe,
                            'rest_seconds': ps.rest_seconds,
                        } for ps in we.planned_sets]
                    } for we in wo.workout_exercises]
                } for wo in w.workouts]
            } for w in m.weeks]
        } for m in program.mesocycles]
    }


@bp.route('/training/program/full', methods=['GET'])
@require_auth
def program_full():
    program = Program.query.filter_by(user_id=g.user_id, status='active').first()
    if not program:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': _serialize_program_full(program)})


@bp.route('/training/program/insights', methods=['POST'])
@require_auth
def program_insights():
    program = Program.query.filter_by(user_id=g.user_id, status='active').first()
    if not program:
        return jsonify({'success': False, 'error': {
            'code': 'NOT_FOUND', 'message': 'No active program'
        }}), 404

    from .models import WorkoutExercise, Workout, ProgramWeek
    total = (WorkoutExercise.query
             .join(Workout).join(ProgramWeek).join(Mesocycle)
             .filter(Mesocycle.program_id == program.id).count())
    filled = (WorkoutExercise.query
              .join(Workout).join(ProgramWeek).join(Mesocycle)
              .filter(Mesocycle.program_id == program.id,
                      WorkoutExercise.selection_reason.isnot(None)).count())

    if total > 0 and filled == total:
        return jsonify({'success': True, 'data': {'count': total, 'already_done': True}})

    user = db.session.get(User, g.user_id)
    from .coach import generate_exercise_insights
    try:
        count = generate_exercise_insights(program, user)
    except Exception:
        return jsonify({'success': False, 'error': {
            'code': 'AI_ERROR', 'message': 'Failed to generate insights, please try again.'
        }}), 500

    return jsonify({'success': True, 'data': {'count': count, 'already_done': False}})
