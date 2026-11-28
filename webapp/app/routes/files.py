from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from app import extensions as ext

bp = Blueprint("files", __name__, url_prefix="/api/v1")

# Paramètre `sort` de l'API -> champ MongoDB
SORT_FIELDS = {
    "date": "uploaded_at",
    "name": "original_name",
    "size": "size_bytes",
    "status": "status",
    "logs": "logs_count",
}


def _serialize(doc):
    doc = {k: v for k, v in doc.items() if k != "_id"}
    for key, value in doc.items():
        if hasattr(value, "isoformat"):
            doc[key] = value.isoformat()
    return doc


def _parse_date(value):
    """Date ISO 8601 (2026-11-10 ou 2026-11-10T08:00:00Z) -> datetime UTC.
    Sans fuseau indiqué, la date est considérée comme UTC."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@bp.get("/files")
def list_files():
    """Liste paginée des fichiers envoyés, avec filtres et tri
    ---
    tags: [Fichiers]
    parameters:
      - $ref: '#/parameters/page'
      - $ref: '#/parameters/per_page'
      - name: status
        in: query
        type: string
        required: false
        enum: [uploaded, validating, queued, ingesting, indexed, error]
        description: Filtrer par statut
      - $ref: '#/parameters/date_from'
      - $ref: '#/parameters/date_to'
      - name: sort
        in: query
        type: string
        enum: [date, name, size, status, logs]
        default: date
        description: Champ de tri
      - name: order
        in: query
        type: string
        enum: [asc, desc]
        default: desc
        description: Sens du tri
    responses:
      200:
        description: Page de fiches de fichiers (les plus récents d'abord par défaut)
        schema:
          $ref: '#/definitions/FilePage'
      400:
        description: Paramètre de pagination, de tri ou de date invalide
        schema:
          $ref: '#/definitions/Error'
      503:
        description: MongoDB indisponible
        schema:
          $ref: '#/definitions/Error'
    """
    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 20)), 1), 100)
    except ValueError:
        return jsonify({"error": "Paramètre de pagination invalide."}), 400

    sort_key = request.args.get("sort", "date")
    order = request.args.get("order", "desc")
    if sort_key not in SORT_FIELDS:
        return jsonify({"error": "Paramètre sort invalide (date, name, size, status, logs)."}), 400
    if order not in ("asc", "desc"):
        return jsonify({"error": "Paramètre order invalide (asc, desc)."}), 400

    query = {}
    if request.args.get("status"):
        query["status"] = request.args["status"]

    date_filter = {}
    try:
        if request.args.get("from"):
            date_filter["$gte"] = _parse_date(request.args["from"])
        if request.args.get("to"):
            raw_to = request.args["to"]
            end = _parse_date(raw_to)
            if len(raw_to) == 10:  # date seule : jusqu'à la fin de la journée
                date_filter["$lt"] = end + timedelta(days=1)
            else:
                date_filter["$lte"] = end
    except ValueError:
        return jsonify({"error": "Date invalide (format ISO 8601, ex. 2026-11-10)."}), 400
    if date_filter:
        query["uploaded_at"] = date_filter

    direction = 1 if order == "asc" else -1
    files = ext.files()
    total = files.count_documents(query)
    docs = (files.find(query)
            .sort([(SORT_FIELDS[sort_key], direction), ("_id", direction)])
            .skip((page - 1) * per_page).limit(per_page))
    return jsonify({"total": total, "page": page, "per_page": per_page,
                    "items": [_serialize(d) for d in docs]})


@bp.get("/files/<file_id>")
def get_file(file_id):
    """Détail et statut d'un fichier
    ---
    tags: [Fichiers]
    parameters:
      - name: file_id
        in: path
        type: string
        required: true
        description: Identifiant du fichier
        x-example: f_20261110_1bd09c
    responses:
      200:
        description: Fiche du fichier
        schema:
          $ref: '#/definitions/FileRecord'
      404:
        description: Fichier inconnu
        schema:
          $ref: '#/definitions/Error'

    """
    doc = ext.files().find_one({"file_id": file_id})
    if not doc:
        return jsonify({"error": "Fichier inconnu."}), 404
    return jsonify(_serialize(doc))
