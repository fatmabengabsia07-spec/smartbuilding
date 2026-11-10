import os


class Config:
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    MONGO_DB = os.getenv("MONGO_DB", "smartbuilding")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")

    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024

    LOGS_DIR = os.getenv("LOGS_DIR", "/app/data/logs")
    STAGING_DIR = os.getenv("STAGING_DIR", "/tmp/smartbuilding_staging")

    INGEST_QUEUE = "queue:ingest"
    INGEST_TIMEOUT_S = int(os.getenv("INGEST_TIMEOUT_S", "180"))
