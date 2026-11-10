"""Suivi des ingestions : lit la file Redis, attend Logstash puis met à jour le statut MongoDB."""
import logging
import threading
import time
from datetime import datetime, timezone

from app import extensions as ext

log = logging.getLogger(__name__)

POLL_S = 2        # fréquence de vérification dans Elasticsearch
STABLE_S = 15     # délai sans nouveau log avant de considérer l'ingestion terminée


def _now():
    return datetime.now(timezone.utc)


def count_docs(file_id):
    query = {"term": {"file_id": file_id}}
    logs = ext.es_client.count(index="smartbuilding-logs-*", query=query, ignore_unavailable=True)["count"]
    errors = ext.es_client.count(index="smartbuilding-errors", query=query, ignore_unavailable=True)["count"]
    return logs, errors


def process(file_id, timeout):
    files = ext.files()
    doc = files.find_one_and_update(
        {"file_id": file_id, "status": {"$in": ["queued", "ingesting"]}},
        {"$set": {"status": "ingesting", "ingest_started_at": _now()}},
    )
    if not doc:
        return
    expected = doc.get("expected_rows", 0)
    last_total, last_change = -1, time.monotonic()
    logs = errors = 0
    while True:
        logs, errors = count_docs(file_id)
        total = logs + errors
        now = time.monotonic()
        if total != last_total:
            last_total, last_change = total, now
        if total >= expected or (total > 0 and now - last_change >= STABLE_S):
            files.update_one(
                {"file_id": file_id},
                {"$set": {"status": "indexed", "logs_count": logs, "errors_count": errors,
                          "indexed_at": _now(), "error_message": None}},
            )
            log.info("Fichier %s indexé : %s logs, %s en erreur", file_id, logs, errors)
            return
        if now - last_change >= timeout:
            message = ("Aucun log indexé : vérifiez que Logstash est démarré." if total == 0
                       else f"Ingestion incomplète : {total} logs sur {expected} attendus.")
            files.update_one({"file_id": file_id},
                             {"$set": {"status": "error", "error_message": message,
                                       "logs_count": logs, "errors_count": errors}})
            log.error("Fichier %s : %s", file_id, message)
            return
        time.sleep(POLL_S)


def run_worker(app):
    queue = app.config["INGEST_QUEUE"]
    timeout = app.config["INGEST_TIMEOUT_S"]
    # Après un redémarrage, on reprend les fichiers restés en cours d'ingestion
    try:
        for doc in ext.files().find({"status": "ingesting"}, {"file_id": 1}):
            ext.redis_client.rpush(queue, doc["file_id"])
    except Exception:  # noqa: BLE001
        log.exception("Reprise des ingestions impossible")
    while True:
        file_id = None
        try:
            item = ext.redis_client.blpop(queue, timeout=5)
            if item:
                file_id = item[1]
                process(file_id, timeout)
        except Exception as exc:  # noqa: BLE001
            log.exception("Erreur du worker d'ingestion")
            if file_id:
                ext.files().update_one({"file_id": file_id},
                                       {"$set": {"status": "error",
                                                 "error_message": f"Erreur de suivi : {str(exc)[:150]}"}})
            time.sleep(5)


def start_worker(app):
    thread = threading.Thread(target=run_worker, args=(app,), name="ingest-worker", daemon=True)
    thread.start()
    return thread
