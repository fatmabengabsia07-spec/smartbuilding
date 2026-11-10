from flask import Blueprint, jsonify

from app import extensions as ext

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    return "Hello World - Smart Building"


@bp.get("/health")
def health():
    checks = ext.check_all()
    healthy = all(ok for ok, _ in checks.values())
    body = {
        "status": "healthy" if healthy else "degraded",
        "checks": {name: {"ok": ok, "detail": detail} for name, (ok, detail) in checks.items()},
    }
    return jsonify(body), (200 if healthy else 503)
