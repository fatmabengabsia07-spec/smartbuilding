"""Connexions MongoDB, Redis et Elasticsearch (créées une fois au démarrage)."""
import logging
import time

import redis
from elasticsearch import Elasticsearch
from pymongo import ASCENDING, MongoClient

log = logging.getLogger(__name__)

mongo_client = None
db = None
redis_client = None
es_client = None


def init_extensions(config):
    global mongo_client, db, redis_client, es_client
    mongo_client = MongoClient(config["MONGO_URI"], serverSelectionTimeoutMS=5000)
    db = mongo_client[config["MONGO_DB"]]
    redis_client = redis.Redis.from_url(
        config["REDIS_URL"], decode_responses=True, socket_connect_timeout=5
    )
    es_client = Elasticsearch(config["ELASTICSEARCH_URL"], request_timeout=10)

    # Test de connectivité au démarrage : on journalise, sans empêcher l'application de démarrer
    for name, (ok, detail) in check_all().items():
        if ok:
            log.info("Connexion %s : OK", name)
        else:
            log.error("Connexion %s : ECHEC (%s)", name, detail)
    try:
        db["files"].create_index("file_id", unique=True)
        db["files"].create_index([("uploaded_at", ASCENDING)])
        db["files"].create_index("status")
    except Exception as exc:  # noqa: BLE001
        log.error("Création des index MongoDB impossible : %s", exc)


def files():
    return db["files"]


def check_all():
    """Retourne {service: (ok, détail)} avec le temps de réponse en millisecondes."""
    checks = {
        "mongodb": lambda: mongo_client.admin.command("ping"),
        "redis": lambda: redis_client.ping(),
        "elasticsearch": lambda: es_client.cluster.health(),
    }
    result = {}
    for name, fn in checks.items():
        start = time.monotonic()
        try:
            fn()
            result[name] = (True, f"{round((time.monotonic() - start) * 1000)} ms")
        except Exception as exc:  # noqa: BLE001
            result[name] = (False, str(exc)[:200])
    return result
