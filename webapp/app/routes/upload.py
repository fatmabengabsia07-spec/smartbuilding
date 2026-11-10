import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request
from pymongo import ReturnDocument
from werkzeug.utils import secure_filename

from app import extensions as ext
from app.services import validation

bp = Blueprint("upload", __name__)


def _now():
    return datetime.now(timezone.utc)


def _error(message, status):
    return jsonify({"error": message}), status


@bp.post("/upload")
def upload():
    """Étape 1 : contrôle du fichier et aperçu. Rien n'est injecté avant la confirmation."""
    f = request.files.get("file")
    if f is None or not f.filename:
        return _error("Aucun fichier reçu (champ « file » attendu).", 400)

    name = secure_filename(f.filename) or "fichier"
    stem = Path(name).stem[:80] or "fichier"
    raw = f.read()
    file_id = f"f_{_now():%Y%m%d}_{secrets.token_hex(3)}"

    ext.files().insert_one({
        "file_id": file_id, "original_name": f.filename, "type": None, "size_bytes": len(raw),
        "status": "validating", "logs_count": 0, "uploaded_by": "anonymous",
        "uploaded_at": _now(), "error_message": None,
    })
    try:
        result = validation.validate_upload(name, raw)
    except validation.ValidationError as exc:
        ext.files().update_one({"file_id": file_id},
                               {"$set": {"status": "error", "error_message": str(exc)}})
        return _error(str(exc), exc.status)

    staging = Path(current_app.config["STAGING_DIR"])
    staging.mkdir(parents=True, exist_ok=True)
    (staging / f"{file_id}.{result.fmt}").write_bytes(raw)

    ext.files().update_one({"file_id": file_id}, {"$set": {
        "type": result.fmt, "status": "uploaded", "expected_rows": result.rows,
        "stored_name": f"{file_id}__{stem}.{result.fmt}",
    }})
    return jsonify({
        "file_id": file_id, "original_name": f.filename, "type": result.fmt,
        "size_bytes": len(raw), "status": "uploaded", "rows": result.rows,
        "preview": {"columns": result.columns, "rows": result.preview},
    })


@bp.post("/upload/<file_id>/confirm")
def confirm(file_id):
    """Étape 2 : dépôt dans le dossier surveillé par Logstash et mise en file de suivi."""
    files = ext.files()
    doc = files.find_one_and_update(
        {"file_id": file_id, "status": "uploaded"},
        {"$set": {"status": "queued", "queued_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        existing = files.find_one({"file_id": file_id})
        if not existing:
            return _error("Fichier inconnu.", 404)
        return _error(f"Confirmation impossible : statut actuel « {existing['status']} ».", 409)

    staged = Path(current_app.config["STAGING_DIR"]) / f"{file_id}.{doc['type']}"
    dest_dir = Path(current_app.config["LOGS_DIR"]) / doc["type"]
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        tmp = dest_dir / f".{doc['stored_name']}.tmp"      # ignoré par Logstash tant que la copie n'est pas finie
        tmp.write_bytes(staged.read_bytes())
        os.replace(tmp, dest_dir / doc["stored_name"])
        staged.unlink(missing_ok=True)
    except OSError as exc:
        files.update_one({"file_id": file_id}, {"$set": {
            "status": "error", "error_message": f"Dépôt du fichier impossible : {exc.strerror or exc}"}})
        return _error("Dépôt du fichier impossible (fichier temporaire introuvable ou dossier inaccessible).", 500)

    ext.redis_client.rpush(current_app.config["INGEST_QUEUE"], file_id)
    return jsonify({"file_id": file_id, "status": "queued"}), 202
