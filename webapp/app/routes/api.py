import logging

from flask import Blueprint, jsonify, request
from elasticsearch import ApiError, TransportError

from app import extensions as ext

bp = Blueprint("api", __name__, url_prefix="/api/v1")
log = logging.getLogger(__name__)

INDEX = "smartbuilding-logs-*"

FILTER_FIELDS = {
    "sensor_id": "sensor_id",
    "sensor_type": "sensor_type",
    "zone": "zone",
    "level": "level",
}


def _build_filters():
    filters = []

    for param, field in FILTER_FIELDS.items():
        value = request.args.get(param)
        if value:
            filters.append({"term": {field: value}})

    date_range = {}
    if request.args.get("from"):
        date_range["gte"] = request.args["from"]
    if request.args.get("to"):
        date_range["lte"] = request.args["to"]

    if date_range:
        filters.append({"range": {"@timestamp": date_range}})

    return filters


def _build_query():
    must = []
    q = request.args.get("q", "").strip()

    if q:
        must.append({
            "multi_match": {
                "query": q,
                "fields": ["message", "sensor_id", "sensor_type", "zone"],
                "fuzziness": "AUTO"
            }
        })

    filters = _build_filters()

    return {"bool": {"must": must, "filter": filters}}


def _serialize_hit(hit):
    item = dict(hit["_source"])
    item["_id"] = hit["_id"]
    item["_index"] = hit["_index"]
    return item


@bp.get("/logs")
def list_logs():
    try:
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 20))

        if page < 1 or per_page < 1 or per_page > 100:
            return jsonify({
                "error": "page doit être positif et per_page compris entre 1 et 100."
            }), 400

        sort_fields = {
            "date": "@timestamp",
            "value": "value",
            "level": "level",
            "sensor": "sensor_id"
        }

        sort_by = request.args.get("sort", "date")
        order = request.args.get("order", "desc").lower()

        if sort_by not in sort_fields:
            return jsonify({"error": "Champ de tri invalide."}), 400

        if order not in ("asc", "desc"):
            return jsonify({"error": "Ordre de tri invalide."}), 400

        response = ext.es_client.search(
            index=INDEX,
            query=_build_query(),
            from_=(page - 1) * per_page,
            size=per_page,
            sort=[{sort_fields[sort_by]: {"order": order}}]
        )

        hits = response["hits"]
        total = hits["total"]["value"]

        return jsonify({
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": (total + per_page - 1) // per_page,
            "sort": sort_by,
            "order": order,
            "items": [_serialize_hit(hit) for hit in hits["hits"]]
        })

    except (ValueError, TypeError):
        return jsonify({"error": "Paramètres de pagination invalides."}), 400
    except (ApiError, TransportError) as exc:
        log.exception("Erreur API Elasticsearch : %s", exc)
        return jsonify({"error": "Service Elasticsearch indisponible."}), 503


@bp.get("/stats")
def get_stats():
    try:
        response = ext.es_client.search(
            index=INDEX,
            query=_build_query(),
            size=0,
            aggs={
                "unique_sensors": {
                    "cardinality": {"field": "sensor_id"}
                },
                "by_sensor_type": {
                    "terms": {"field": "sensor_type", "size": 20}
                },
                "by_zone": {
                    "terms": {"field": "zone", "size": 20}
                },
                "by_level": {
                    "terms": {"field": "level", "size": 20}
                },
                "average_value": {
                    "avg": {"field": "value"}
                }
            }
        )

        total = response["hits"]["total"]["value"]
        aggs = response["aggregations"]

        def buckets(name):
            return [
                {"name": item["key"], "count": item["doc_count"]}
                for item in aggs[name]["buckets"]
            ]

        return jsonify({
            "total_logs": total,
            "unique_sensors": aggs["unique_sensors"]["value"],
            "alerts": sum(
                item["doc_count"]
                for item in aggs["by_level"]["buckets"]
                if item["key"].upper() in ("WARNING", "CRITICAL", "ERROR")
            ),
            "average_value": aggs["average_value"]["value"],
            "by_sensor_type": buckets("by_sensor_type"),
            "by_zone": buckets("by_zone"),
            "by_level": buckets("by_level")
        })

    except (ApiError, TransportError) as exc:
        log.exception("Erreur statistiques Elasticsearch : %s", exc)
        return jsonify({"error": "Service Elasticsearch indisponible."}), 503
