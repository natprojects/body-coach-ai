from datetime import datetime
from flask import g, jsonify, request
from app.core.auth import require_auth
from app.core.models import User
from app.extensions import db
from . import bp
from .models import CalisthenicsProfile, CalisthenicsAssessment

_VALID_GOALS = {'muscle', 'strength', 'skill', 'weight_loss', 'endurance'}
_VALID_EQUIPMENT = {'none', 'floor', 'bands', 'dumbbells', 'pullup_bar', 'dip_bars', 'rings', 'parallettes'}
_VALID_MOTIVATION = {'look', 'feel', 'achieve', 'health'}
_PULLUP_EQUIPMENT = {'pullup_bar', 'dip_bars', 'rings'}


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
    if not isinstance(days_per_week, int) or not (1 <= days_per_week <= 7):
        return jsonify({'success': False, 'error': {
            'code': 'INVALID_FIELD',
            'message': 'days_per_week must be an integer between 1 and 7',
        }}), 400
    if not isinstance(session_duration_min, int) or not (15 <= session_duration_min <= 180):
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
