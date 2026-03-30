from flask import Flask, jsonify
from .config import Config
from .extensions import db, migrate


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)

    from .core import models  # noqa: F401 — ensure models are registered with SQLAlchemy

    from .core.routes import bp as core_bp
    app.register_blueprint(core_bp, url_prefix='/api')

    from .modules.training import bp as training_bp
    app.register_blueprint(training_bp, url_prefix='/api')

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({'success': False, 'error': {'code': 'BAD_REQUEST', 'message': str(e)}}), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({'success': False, 'error': {'code': 'UNAUTHORIZED', 'message': str(e)}}), 401

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'success': False, 'error': {'code': 'NOT_FOUND', 'message': str(e)}}), 404

    @app.errorhandler(Exception)
    def handle_exception(e):
        app.logger.error(f"Unhandled exception: {e}", exc_info=True)
        return jsonify({'success': False, 'error': {'code': 'INTERNAL_ERROR', 'message': 'Internal server error'}}), 500

    return app
