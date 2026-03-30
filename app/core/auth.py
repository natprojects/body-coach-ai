import hashlib
import hmac
import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request

from app.extensions import db
from app.core.models import User


def validate_telegram_init_data(init_data: str, bot_token: str) -> dict:
    parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop('hash', '')
    data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed_hash, received_hash):
        raise ValueError("Invalid hash")
    return parsed


def create_jwt(user_id: int, secret_key: str) -> str:
    payload = {
        'user_id': user_id,
        'exp': datetime.now(timezone.utc) + timedelta(days=30),
    }
    return jwt.encode(payload, secret_key, algorithm='HS256')


def decode_jwt(token: str, secret_key: str) -> dict:
    return jwt.decode(token, secret_key, algorithms=['HS256'])


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': {'code': 'UNAUTHORIZED', 'message': 'Missing token'}}), 401
        token = auth_header[7:]
        try:
            payload = decode_jwt(token, current_app.config['SECRET_KEY'])
            g.user_id = payload['user_id']
        except jwt.ExpiredSignatureError:
            return jsonify({'success': False, 'error': {'code': 'TOKEN_EXPIRED', 'message': 'Token expired'}}), 401
        except jwt.InvalidTokenError:
            return jsonify({'success': False, 'error': {'code': 'INVALID_TOKEN', 'message': 'Invalid token'}}), 401
        return f(*args, **kwargs)
    return decorated


def get_or_create_user(telegram_id: int) -> User:
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)
        db.session.add(user)
        db.session.commit()
    return user
