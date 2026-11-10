import logging

from flask import Flask, jsonify
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError
from werkzeug.exceptions import RequestEntityTooLarge

from app import extensions
from app.config import Config


def create_app():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = Flask(__name__)
    app.config.from_object(Config)
    extensions.init_extensions(app.config)

    from app.routes import files, main, upload
    app.register_blueprint(main.bp)
    app.register_blueprint(upload.bp)
    app.register_blueprint(files.bp)

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(_):
        return jsonify(error=f"Fichier trop volumineux (maximum {app.config['MAX_UPLOAD_MB']} Mo)."), 413

    @app.errorhandler(PyMongoError)
    def mongo_down(_):
        return jsonify(error="Base de données indisponible."), 503

    @app.errorhandler(RedisError)
    def redis_down(_):
        return jsonify(error="Service de file d'attente indisponible."), 503

    from app.services.ingest_worker import start_worker
    start_worker(app)
    return app
