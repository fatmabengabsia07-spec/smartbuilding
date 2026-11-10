import logging
import secrets
from datetime import datetime, timezone

from flask import Flask, jsonify, session
from flask_session import Session
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError
from werkzeug.exceptions import RequestEntityTooLarge, TooManyRequests

from app import extensions
from app.config import Config
from app.security import limiter


def create_app():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    app = Flask(__name__)
    app.config.from_object(Config)

    if not app.config["SECRET_KEY"]:
        raise RuntimeError("La variable SECRET_KEY est absente du fichier .env.")

    # Connexion aux services
    extensions.init_extensions(app.config)

    # Sessions stockées dans Redis
    app.config["SESSION_REDIS"] = extensions.session_redis_client
    Session(app)

    # Limitation des requêtes avec Redis
    limiter.init_app(app)

    from app.routes import files, main, upload, search

    app.register_blueprint(main.bp)
    app.register_blueprint(upload.bp)
    app.register_blueprint(files.bp)
    app.register_blueprint(search.bp)

    @app.before_request
    def manage_session():
        session.permanent = True
        session.setdefault("visitor_id", secrets.token_urlsafe(16))
        session["last_activity"] = datetime.now(timezone.utc).isoformat()

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_):
        return jsonify(
            error=f"Fichier trop volumineux (maximum {app.config['MAX_UPLOAD_MB']} Mo)."
        ), 413

    @app.errorhandler(PyMongoError)
    def mongo_down(_):
        return jsonify(error="Base de données indisponible."), 503

    @app.errorhandler(RedisError)
    def redis_down(_):
        return jsonify(error="Service Redis indisponible."), 503

    @app.errorhandler(TooManyRequests)
    def rate_limit_exceeded(_):
        return jsonify(
            error="Trop de requêtes. Veuillez réessayer plus tard."
        ), 429

    from app.services.ingest_worker import start_worker
    start_worker(app)

    return app
