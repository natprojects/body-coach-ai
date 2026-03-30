import hashlib
import hmac
import json
import urllib.parse
import pytest
from app.core.auth import validate_telegram_init_data, create_jwt, decode_jwt

BOT_TOKEN = 'test-bot-token-1234567890'

def _make_init_data(bot_token=BOT_TOKEN, telegram_id=123456, extra_params=None):
    user_json = json.dumps({"id": telegram_id, "first_name": "Natalie"})
    params = {"user": user_json, "auth_date": "1700000000"}
    if extra_params:
        params.update(extra_params)
    data_check_string = '\n'.join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
    hash_val = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    params['hash'] = hash_val
    return urllib.parse.urlencode(params)

def test_valid_init_data():
    result = validate_telegram_init_data(_make_init_data(), BOT_TOKEN)
    assert result['auth_date'] == '1700000000'
    assert 'Natalie' in result['user']

def test_tampered_hash_raises():
    init_data = _make_init_data()
    tampered = init_data[:-5] + 'aaaaa'
    with pytest.raises(ValueError, match="Invalid hash"):
        validate_telegram_init_data(tampered, BOT_TOKEN)

def test_wrong_bot_token_raises():
    init_data = _make_init_data(bot_token=BOT_TOKEN)
    with pytest.raises(ValueError, match="Invalid hash"):
        validate_telegram_init_data(init_data, 'wrong-token')

def test_create_and_decode_jwt():
    token = create_jwt(42, 'my-secret')
    payload = decode_jwt(token, 'my-secret')
    assert payload['user_id'] == 42

def test_require_auth_missing_token(client):
    resp = client.get('/api/checkin/today')
    assert resp.status_code == 401

def test_require_auth_invalid_token(client):
    resp = client.get('/api/checkin/today', headers={'Authorization': 'Bearer bad.token.here'})
    assert resp.status_code == 401
