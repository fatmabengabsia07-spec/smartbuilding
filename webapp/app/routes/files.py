from flask import Blueprint, jsonify, request

from app import extensions as ext

bp = Blueprint("files", __name__, url_prefix="/api/v1")


def _serialize(doc):
    doc = {k: v for k, v in doc.items() if k != "_id"}
    for key, value in doc.items():
        if hasattr(value, "isoformat"):
            doc[key] = value.isoformat()
    return doc


@bp.get("/files")
def list_files():
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(max(int(request.args.get("per_page", 20)), 1), 100)
    query = {}
    if request.args.get("status"):
        query["status"] = request.args["status"]
    files = ext.files()
    total = files.count_documents(query)
    docs = files.find(query).sort("uploaded_at", -1).skip((page - 1) * per_page).limit(per_page)
    return jsonify({"total": total, "page": page, "per_page": per_page,
                    "items": [_serialize(d) for d in docs]})


@bp.get("/files/<file_id>")
def get_file(file_id):
    doc = ext.files().find_one({"file_id": file_id})
    if not doc:
        return jsonify({"error": "Fichier inconnu."}), 404
    return jsonify(_serialize(doc))
