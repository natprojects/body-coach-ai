from flask import Blueprint, g, jsonify, request
from app.core.auth import require_auth

bp = Blueprint('core', __name__)


@bp.route('/checkin/today', methods=['GET'])
@require_auth
def get_checkin_today():
    return jsonify({'success': True, 'data': None})
