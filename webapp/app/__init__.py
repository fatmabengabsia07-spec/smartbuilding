from flask import Flask


def create_app():
    app = Flask(__name__)

    @app.route("/")
    def hello():
        return "Hello World - Smart Building"

    @app.route("/health")
    def health():
        return {"status": "ok"}

    return app
