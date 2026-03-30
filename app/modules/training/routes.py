from datetime import datetime
from flask import g, jsonify, request
from app.core.auth import require_auth
from app.core.models import User
from app.extensions import db
from . import bp
from .onboarding import ONBOARDING_STEPS, apply_step, get_first_step, get_next_step


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
