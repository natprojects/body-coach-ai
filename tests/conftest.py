import pytest
from unittest.mock import MagicMock, patch
from app import create_app
from app.config import TestConfig
from app.extensions import db as _db


@pytest.fixture(scope='function')
def app():
    app = create_app(TestConfig)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def mock_anthropic():
    mock_client = MagicMock()
    with patch('app.core.ai.get_client', return_value=mock_client):
        yield mock_client
