from datetime import datetime
from flask import g, jsonify, request
from app.core.auth import require_auth
from app.core.models import User
from app.extensions import db
from . import bp
from .onboarding import ONBOARDING_STEPS, apply_step, get_first_step, get_next_step
from .coach import build_training_context, generate_program, save_program_from_dict
from .models import Program, Mesocycle


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
    program_dict = generate_program(user)
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
