import logging
import secrets
from datetime import datetime, timezone

from flasgger import Swagger
from flask import Flask, jsonify, render_template, request, session
from flask_session import Session
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError
from werkzeug.exceptions import RequestEntityTooLarge, TooManyRequests

from app import extensions
from app.config import Config
from app.security import limiter
from app.swagger_config import SWAGGER_CONFIG, SWAGGER_TEMPLATE


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

    from app.routes import files, main, upload, search, api, ui

    app.register_blueprint(main.bp)
    app.register_blueprint(upload.bp)
    app.register_blueprint(files.bp)
    app.register_blueprint(search.bp)
    app.register_blueprint(api.bp)
    app.register_blueprint(ui.bp)

    # Documentation Swagger : interface sur /apidocs/, spécification sur /apispec.json
    Swagger(app, config=SWAGGER_CONFIG, template=SWAGGER_TEMPLATE)
    # Les fichiers statiques de Swagger UI ne doivent pas consommer la limite de requêtes
    if "flasgger" in app.blueprints:
        limiter.exempt(app.blueprints["flasgger"])

    @app.before_request
    def manage_session():
        session.permanent = True
        session.setdefault("visitor_id", secrets.token_urlsafe(16))
        session["last_activity"] = datetime.now(timezone.utc).isoformat()

    @app.errorhandler(404)
    def page_not_found(error):
        # Page HTML pour un navigateur, JSON pour les appels API
        if request.accept_mimetypes.best == "text/html":
            return render_template("404.html", active=""), 404
        return jsonify(error="Ressource introuvable."), 404

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
