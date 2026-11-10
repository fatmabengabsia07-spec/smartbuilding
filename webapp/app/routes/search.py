import hashlib
import json
import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, session
from elasticsearch import ApiError, TransportError
from redis.exceptions import RedisError
from pymongo.errors import PyMongoError

from app import extensions as ext
from app.security import limiter

bp = Blueprint("search", __name__)
log = logging.getLogger(__name__)

INDEX = "smartbuilding-logs-*"
CACHE_TTL = 60

SORT_FIELDS = {
    "date": "@timestamp",
    "value": "value",
    "level": "level.keyword",
    "sensor": "sensor_id.keyword",
}

FILTER_FIELDS = {
    "sensor_id": "sensor_id.keyword",
    "sensor_type": "sensor_type.keyword",
    "zone": "zone.keyword",
    "level": "level.keyword",
}


def _positive_int(name, default, maximum):
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        return None

    if value < 1 or value > maximum:
        return None

    return value


def _save_search_history(params, total, cached):
    """Enregistre une recherche réussie dans MongoDB."""
    try:
        ext.search_history().insert_one({
            "session_id": session.get("visitor_id"),
            "searched_at": datetime.now(timezone.utc),
            "parameters": dict(params),
            "result_count": total,
            "cached": cached,
        })
    except PyMongoError as exc:
        log.warning("Enregistrement de l'historique impossible : %s", exc)


@bp.get("/search")
@limiter.limit("30 per minute")
def search_logs():
    page = _positive_int("page", 1, 1000000)
    per_page = _positive_int("per_page", 20, 100)

    if page is None or per_page is None:
        return jsonify({
            "error": "Paramètres page ou per_page invalides."
        }), 400

    text = request.args.get("q", "").strip()

    must = []
    if text:
        must.append({
            "multi_match": {
                "query": text,
                "fields": [
                    "message",
                    "sensor_id",
                    "sensor_type",
                    "zone",
                ],
                "type": "best_fields",
                "fuzziness": "AUTO",
            }
        })

    filters = []
    for param, field in FILTER_FIELDS.items():
        value = request.args.get(param)
        if value:
            filters.append({"term": {field: value}})

    date_range = {}
    date_from = request.args.get("from")
    date_to = request.args.get("to")

    if date_from:
        date_range["gte"] = date_from

    if date_to:
        date_range["lte"] = date_to

    if date_range:
        filters.append({
            "range": {
                "@timestamp": date_range
            }
        })

    value_range = {}

    for param, operator in [
        ("min_value", "gte"),
        ("max_value", "lte"),
    ]:
        raw = request.args.get(param)
        if raw is not None:
            try:
                value_range[operator] = float(raw)
            except ValueError:
                return jsonify({
                    "error": f"Le paramètre {param} doit être numérique."
                }), 400

    if value_range:
        filters.append({"range": {"value": value_range}})

    query = {
        "bool": {
            "must": must,
            "filter": filters,
        }
    }

    sort_by = request.args.get("sort", "date")
    order = request.args.get("order", "desc").lower()

    if sort_by not in SORT_FIELDS:
        return jsonify({"error": "Champ de tri invalide."}), 400

    if order not in ("asc", "desc"):
        return jsonify({"error": "Ordre de tri invalide."}), 400

    sort = [
        {SORT_FIELDS[sort_by]: {"order": order}}
    ]

    # Création d'une clé unique selon les paramètres de recherche
    params = sorted(request.args.items())
    params_json = json.dumps(params, ensure_ascii=False)
    cache_hash = hashlib.sha256(params_json.encode("utf-8")).hexdigest()
    cache_key = f"search:v1:{cache_hash}"

    # Vérification du cache Redis
    try:
        cached_data = ext.redis_client.get(cache_key)

        if cached_data:
            result = json.loads(cached_data)
            result["cached"] = True
            _save_search_history(request.args, result["total"], True)
            log.info("Résultat récupéré depuis Redis : %s", cache_key)
            return jsonify(result)

    except (RedisError, json.JSONDecodeError) as exc:
        log.warning("Lecture du cache Redis impossible : %s", exc)

    # Cache absent : interrogation d'Elasticsearch
    try:
        response = ext.es_client.search(
            index=INDEX,
            query=query,
            from_=(page - 1) * per_page,
            size=per_page,
            sort=sort,
        )

        hits = response["hits"]
        items = []

        for hit in hits["hits"]:
            item = dict(hit["_source"])
            item["_id"] = hit["_id"]
            item["_index"] = hit["_index"]
            items.append(item)

        total = hits["total"]["value"]

        result = {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
            "sort": sort_by,
            "order": order,
            "items": items,
            "cached": False,
        }

        # Enregistrement du résultat dans Redis pendant 60 secondes
        try:
            ext.redis_client.setex(
                cache_key,
                CACHE_TTL,
                json.dumps(result, ensure_ascii=False),
            )
            log.info("Résultat enregistré dans Redis : %s", cache_key)

        except RedisError as exc:
            log.warning("Écriture du cache Redis impossible : %s", exc)

        _save_search_history(request.args, total, False)
        return jsonify(result)

    except (ApiError, TransportError):
        return jsonify({
            "error": "Erreur lors de la recherche Elasticsearch."
        }), 503


@bp.get("/search/history")
@limiter.limit("30 per minute")
def get_search_history():
    try:
        limit = _positive_int("limit", 20, 100)

        if limit is None:
            return jsonify({
                "error": "Le paramètre limit doit être compris entre 1 et 100."
            }), 400

        records = ext.search_history().find(
            {},
            {"_id": 1, "searched_at": 1, "parameters": 1,
             "result_count": 1, "cached": 1}
        ).sort("searched_at", -1).limit(limit)

        history = []
        for record in records:
            history.append({
                "id": str(record["_id"]),
                "searched_at": record["searched_at"].isoformat(),
                "parameters": record["parameters"],
                "result_count": record["result_count"],
                "cached": record["cached"],
            })

        return jsonify({
            "total": len(history),
            "items": history,
        })

    except PyMongoError as exc:
        log.error("Consultation de l'historique impossible : %s", exc)
        return jsonify({
            "error": "Erreur lors de la consultation de l'historique."
        }), 503
