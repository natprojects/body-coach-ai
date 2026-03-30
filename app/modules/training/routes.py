from flask import jsonify
from . import bp

@bp.route('/training/ping')
def ping():
    return jsonify({'success': True})
