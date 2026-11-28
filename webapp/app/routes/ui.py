"""Pages HTML de l'interface. Les données viennent de l'API REST, appelée en JavaScript."""
from flask import Blueprint, render_template

bp = Blueprint("ui", __name__)


@bp.get("/upload")
def upload_page():
    return render_template("upload.html", active="upload")


@bp.get("/recherche")
def search_page():
    return render_template("search.html", active="search")


@bp.get("/resultats")
def results_page():
    return render_template("results.html", active="search")


@bp.get("/kibana")
def kibana_page():
    return render_template("kibana.html", active="kibana")
