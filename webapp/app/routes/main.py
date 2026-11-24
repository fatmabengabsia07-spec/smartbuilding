from flask import Blueprint, jsonify

from app import extensions as ext
from app.security import limiter

bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    """Page d'accueil (texte)
    ---
    tags: [Système]
    produces: [text/plain]
    responses:
      200:
        description: Message d'accueil
    
    """
    return "Hello World - Smart Building"


@bp.get("/health")
@limiter.exempt
def health():
    """État de la webapp et des services (Elasticsearch, MongoDB, Redis)
    Utilisée par le healthcheck Docker (exclue de la limitation de débit).
    ---
    tags: [Système]
    responses:
      200:
        description: Tous les services répondent
        schema:
          $ref: '#/definitions/Health'
      503:
        description: Au moins un service est indisponible (statut degraded)
        schema:
          $ref: '#/definitions/Health'
    
    """
    checks = ext.check_all()
    healthy = all(ok for ok, _ in checks.values())
    body = {
        "status": "healthy" if healthy else "degraded",
        "checks": {name: {"ok": ok, "detail": detail} for name, (ok, detail) in checks.items()},
    }
    return jsonify(body), (200 if healthy else 503)
