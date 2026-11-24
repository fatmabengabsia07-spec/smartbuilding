"""Configuration de la documentation OpenAPI/Swagger (Flasgger).

Interface : /apidocs/      Spécification JSON : /apispec.json
Les descriptions propres à chaque route sont dans les docstrings des routes ;
ce fichier contient uniquement les éléments partagés (infos, tags, modèles, paramètres).
"""

SWAGGER_CONFIG = {
    "headers": [],
    "specs": [
        {
            "endpoint": "apispec",
            "route": "/apispec.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/apidocs/",
}

SWAGGER_TEMPLATE = {
    "swagger": "2.0",
    "info": {
        "title": "Smart Building - API de monitoring et d'analyse de logs",
        "description": (
            "API REST de la plateforme Smart Building (Flask, Elasticsearch, "
            "MongoDB, Redis, Logstash). Elle permet de déposer des fichiers de logs "
            "(CSV/JSON), de rechercher les logs indexés, de consulter les statistiques "
            "et de suivre l'ingestion des fichiers."
        ),
        "version": "1.0.0",
        "contact": {"name": "Équipe projet Smart Building - ITBS"},
    },
    "basePath": "/",
    "schemes": ["http"],
    "consumes": ["application/json"],
    "produces": ["application/json"],
    "tags": [
        {"name": "Système", "description": "Accueil et état de santé des services"},
        {"name": "Logs", "description": "Consultation des logs et statistiques (Elasticsearch)"},
        {"name": "Fichiers", "description": "Fiches des fichiers envoyés (MongoDB)"},
        {"name": "Upload", "description": "Dépôt, validation et confirmation d'ingestion"},
        {"name": "Recherche", "description": "Recherche avec cache Redis et historique"},
    ],
    # Paramètres réutilisables : référencés avec $ref: '#/parameters/<nom>'
    "parameters": {
        "q": {
            "name": "q", "in": "query", "type": "string", "required": False,
            "description": "Texte libre (message, sensor_id, sensor_type, zone), tolérant aux fautes de frappe",
        },
        "sensor_id": {
            "name": "sensor_id", "in": "query", "type": "string", "required": False,
            "description": "Identifiant exact du capteur", "x-example": "TEMP_001",
        },
        "sensor_type": {
            "name": "sensor_type", "in": "query", "type": "string", "required": False,
            "enum": ["temperature", "humidity", "co2", "luminosity", "energy", "occupancy"],
            "description": "Type de mesure",
        },
        "zone": {
            "name": "zone", "in": "query", "type": "string", "required": False,
            "description": "Zone du bâtiment", "x-example": "Hall",
        },
        "level": {
            "name": "level", "in": "query", "type": "string", "required": False,
            "enum": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            "description": "Niveau du log",
        },
        "date_from": {
            "name": "from", "in": "query", "type": "string", "required": False,
            "description": "Date de début incluse (ISO 8601)", "x-example": "2026-11-01T00:00:00Z",
        },
        "date_to": {
            "name": "to", "in": "query", "type": "string", "required": False,
            "description": "Date de fin incluse (ISO 8601)", "x-example": "2026-11-30T23:59:59Z",
        },
        "page": {
            "name": "page", "in": "query", "type": "integer", "required": False,
            "default": 1, "minimum": 1, "description": "Numéro de page",
        },
        "per_page": {
            "name": "per_page", "in": "query", "type": "integer", "required": False,
            "default": 20, "minimum": 1, "maximum": 100, "description": "Résultats par page",
        },
        "sort": {
            "name": "sort", "in": "query", "type": "string", "required": False,
            "enum": ["date", "value", "level", "sensor"], "default": "date",
            "description": "Champ de tri",
        },
        "order": {
            "name": "order", "in": "query", "type": "string", "required": False,
            "enum": ["asc", "desc"], "default": "desc", "description": "Sens du tri",
        },
    },
    "definitions": {
        "Error": {
            "type": "object",
            "properties": {"error": {"type": "string", "example": "Paramètres invalides."}},
        },
        "Log": {
            "type": "object",
            "properties": {
                "_id": {"type": "string", "example": "AZ1x..."},
                "_index": {"type": "string", "example": "smartbuilding-logs-2026.11.10"},
                "event_id": {"type": "string"},
                "@timestamp": {"type": "string", "format": "date-time", "example": "2026-11-10T09:21:00.000Z"},
                "level": {"type": "string", "example": "INFO"},
                "sensor_id": {"type": "string", "example": "TEMP_001"},
                "sensor_type": {"type": "string", "example": "temperature"},
                "zone": {"type": "string", "example": "Hall"},
                "value": {"type": "number", "format": "float", "example": 21.5},
                "unit": {"type": "string", "example": "C"},
                "message": {"type": "string", "example": "Mesure 21"},
                "source": {"type": "string"},
                "file_id": {"type": "string", "example": "f_20261110_e8dd92"},
                "tags": {"type": "array", "items": {"type": "string"}, "example": ["csv"]},
            },
        },
        "LogPage": {
            "type": "object",
            "properties": {
                "total": {"type": "integer", "example": 1250},
                "page": {"type": "integer", "example": 1},
                "per_page": {"type": "integer", "example": 20},
                "total_pages": {"type": "integer", "example": 63},
                "sort": {"type": "string", "example": "date"},
                "order": {"type": "string", "example": "desc"},
                "items": {"type": "array", "items": {"$ref": "#/definitions/Log"}},
            },
        },
        "SearchPage": {
            "allOf": [
                {"$ref": "#/definitions/LogPage"},
                {"type": "object", "properties": {
                    "cached": {"type": "boolean", "description": "true si le résultat vient du cache Redis (60 s)"}}},
            ]
        },
        "Bucket": {
            "type": "object",
            "properties": {"name": {"type": "string", "example": "Hall"},
                           "count": {"type": "integer", "example": 320}},
        },
        "Stats": {
            "type": "object",
            "properties": {
                "total_logs": {"type": "integer", "example": 1250},
                "unique_sensors": {"type": "integer", "example": 12},
                "alerts": {"type": "integer", "description": "Logs WARNING, ERROR ou CRITICAL", "example": 48},
                "average_value": {"type": "number", "example": 23.7},
                "by_sensor_type": {"type": "array", "items": {"$ref": "#/definitions/Bucket"}},
                "by_zone": {"type": "array", "items": {"$ref": "#/definitions/Bucket"}},
                "by_level": {"type": "array", "items": {"$ref": "#/definitions/Bucket"}},
            },
        },
        "FileRecord": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "example": "f_20261110_1bd09c"},
                "original_name": {"type": "string", "example": "smart_building_logs.json"},
                "stored_name": {"type": "string", "example": "f_20261110_1bd09c__smart_building_logs.json"},
                "type": {"type": "string", "enum": ["csv", "json"]},
                "size_bytes": {"type": "integer", "example": 153581},
                "status": {"type": "string",
                           "enum": ["uploaded", "validating", "queued", "ingesting", "indexed", "error"]},
                "expected_rows": {"type": "integer", "example": 500},
                "logs_count": {"type": "integer", "example": 0},
                "uploaded_by": {"type": "string", "example": "anonymous"},
                "uploaded_at": {"type": "string", "format": "date-time"},
                "error_message": {"type": "string", "x-nullable": True},
            },
        },
        "FilePage": {
            "type": "object",
            "properties": {
                "total": {"type": "integer"}, "page": {"type": "integer"}, "per_page": {"type": "integer"},
                "items": {"type": "array", "items": {"$ref": "#/definitions/FileRecord"}},
            },
        },
        "UploadPreview": {
            "type": "object",
            "properties": {
                "file_id": {"type": "string", "example": "f_20261110_e8dd92"},
                "original_name": {"type": "string"},
                "type": {"type": "string", "enum": ["csv", "json"]},
                "size_bytes": {"type": "integer"},
                "status": {"type": "string", "example": "uploaded"},
                "rows": {"type": "integer", "description": "Nombre de lignes valides"},
                "preview": {
                    "type": "object",
                    "properties": {
                        "columns": {"type": "array", "items": {"type": "string"}},
                        "rows": {"type": "array", "items": {"type": "object"},
                                 "description": "10 premières lignes"},
                    },
                },
            },
        },
        "ConfirmResult": {
            "type": "object",
            "properties": {"file_id": {"type": "string"}, "status": {"type": "string", "example": "queued"}},
        },
        "SearchHistoryItem": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "searched_at": {"type": "string", "format": "date-time"},
                "parameters": {"type": "object", "example": {"q": "temperature", "zone": "Hall"}},
                "result_count": {"type": "integer"},
                "cached": {"type": "boolean"},
            },
        },
        "SearchHistory": {
            "type": "object",
            "properties": {
                "total": {"type": "integer"},
                "items": {"type": "array", "items": {"$ref": "#/definitions/SearchHistoryItem"}},
            },
        },
        "Health": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["healthy", "degraded"]},
                "checks": {
                    "type": "object",
                    "example": {
                        "mongodb": {"ok": True, "detail": "4 ms"},
                        "redis": {"ok": True, "detail": "1 ms"},
                        "elasticsearch": {"ok": True, "detail": "12 ms"},
                    },
                },
            },
        },
    },
}
