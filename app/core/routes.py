from datetime import date
from flask import Blueprint, g, jsonify, request, current_app
from app.core.auth import (
    create_jwt, get_or_create_user, require_auth, validate_telegram_init_data
)
from app.core.models import BodyMeasurement, DailyCheckin, PainJournal
from app.extensions import db

bp = Blueprint('core', __name__)


@bp.route('/auth/validate', methods=['POST'])
def auth_validate():
    body = request.json or {}
    init_data = body.get('init_data', '')
    try:
        parsed = validate_telegram_init_data(init_data, current_app.config['TELEGRAM_BOT_TOKEN'])
    except ValueError:
        return jsonify({'success': False, 'error': {'code': 'UNAUTHORIZED', 'message': 'Invalid Telegram data'}}), 401

    import json as _json
    user_info = _json.loads(parsed.get('user', '{}'))
    telegram_id = user_info.get('id')
    if not telegram_id:
        return jsonify({'success': False, 'error': {'code': 'BAD_REQUEST', 'message': 'Missing user id'}}), 400

    user = get_or_create_user(telegram_id)
    if user_info.get('first_name') and not user.name:
        user.name = user_info['first_name']
        db.session.commit()

    token = create_jwt(user.id, current_app.config['SECRET_KEY'])
    return jsonify({'success': True, 'data': {
        'token': token,
        'user_id': user.id,
        'onboarding_completed': user.onboarding_completed_at is not None,
    }})


@bp.route('/checkin', methods=['POST'])
@require_auth
def create_checkin():
    data = request.json or {}
    checkin = DailyCheckin(
        user_id=g.user_id,
        date=date.today(),
        energy_level=data.get('energy_level'),
        sleep_quality=data.get('sleep_quality'),
        stress_level=data.get('stress_level'),
        motivation=data.get('motivation'),
        soreness_level=data.get('soreness_level'),
        body_weight_kg=data.get('body_weight_kg'),
        cycle_day=data.get('cycle_day'),
        notes=data.get('notes'),
    )
    db.session.add(checkin)
    db.session.commit()
    return jsonify({'success': True, 'data': {'id': checkin.id}})


@bp.route('/checkin/today', methods=['GET'])
@require_auth
def get_checkin_today():
    checkin = DailyCheckin.query.filter_by(user_id=g.user_id, date=date.today()).first()
    if not checkin:
        return jsonify({'success': True, 'data': None})
    return jsonify({'success': True, 'data': {
        'id': checkin.id,
        'date': checkin.date.isoformat(),
        'energy_level': checkin.energy_level,
        'sleep_quality': checkin.sleep_quality,
        'stress_level': checkin.stress_level,
        'motivation': checkin.motivation,
        'soreness_level': checkin.soreness_level,
        'body_weight_kg': checkin.body_weight_kg,
        'cycle_day': checkin.cycle_day,
        'notes': checkin.notes,
    }})


@bp.route('/pain', methods=['POST'])
@require_auth
def create_pain():
    data = request.json or {}
    entry = PainJournal(
        user_id=g.user_id,
        date=date.today(),
        body_part=data.get('body_part', ''),
        pain_type=data.get('pain_type'),
        intensity=data.get('intensity'),
        when_occurs=data.get('when_occurs'),
        notes=data.get('notes'),
    )
    db.session.add(entry)
    db.session.commit()
    return jsonify({'success': True, 'data': {'id': entry.id}})


@bp.route('/pain/recent', methods=['GET'])
@require_auth
def get_pain_recent():
    from datetime import timedelta
    since = date.today() - timedelta(days=30)
    entries = PainJournal.query.filter(
        PainJournal.user_id == g.user_id,
        PainJournal.date >= since
    ).order_by(PainJournal.date.desc()).all()
    return jsonify({'success': True, 'data': [{
        'id': e.id, 'date': e.date.isoformat(), 'body_part': e.body_part,
        'pain_type': e.pain_type, 'intensity': e.intensity,
        'when_occurs': e.when_occurs, 'notes': e.notes,
    } for e in entries]})


@bp.route('/measurements', methods=['POST'])
@require_auth
def create_measurement():
    data = request.json or {}
    m = BodyMeasurement(
        user_id=g.user_id,
        date=date.today(),
        weight_kg=data.get('weight_kg'),
        body_fat_pct=data.get('body_fat_pct'),
        waist_cm=data.get('waist_cm'),
        hips_cm=data.get('hips_cm'),
        chest_cm=data.get('chest_cm'),
        left_arm_cm=data.get('left_arm_cm'),
        right_arm_cm=data.get('right_arm_cm'),
        left_leg_cm=data.get('left_leg_cm'),
        right_leg_cm=data.get('right_leg_cm'),
    )
    db.session.add(m)
    db.session.commit()
    return jsonify({'success': True, 'data': {'id': m.id}})


@bp.route('/measurements/history', methods=['GET'])
@require_auth
def get_measurements_history():
    entries = BodyMeasurement.query.filter_by(user_id=g.user_id).order_by(BodyMeasurement.date.desc()).all()
    return jsonify({'success': True, 'data': [{
        'id': e.id, 'date': e.date.isoformat(),
        'weight_kg': e.weight_kg, 'body_fat_pct': e.body_fat_pct,
        'waist_cm': e.waist_cm, 'hips_cm': e.hips_cm,
        'chest_cm': e.chest_cm,
        'left_arm_cm': e.left_arm_cm, 'right_arm_cm': e.right_arm_cm,
        'left_leg_cm': e.left_leg_cm, 'right_leg_cm': e.right_leg_cm,
    } for e in entries]})
