from flask import (
    Flask,
    make_response,
    render_template,
    send_from_directory,
    send_file,
)
import os
import requests
from datetime import datetime
import dotenv

dotenv.load_dotenv()

app = Flask(__name__)


def find(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)


# Assets routes
@app.route("/assets/<path:path>")
def send_assets(path):
    if path.endswith(".json"):
        return send_from_directory(
            "templates/assets", path, mimetype="application/json"
        )

    if os.path.isfile("templates/assets/" + path):
        return send_from_directory("templates/assets", path)

    # Try looking in one of the directories
    filename: str = path.split("/")[-1]
    if (
        filename.endswith(".png")
        or filename.endswith(".jpg")
        or filename.endswith(".jpeg")
        or filename.endswith(".svg")
    ):
        if os.path.isfile("templates/assets/img/" + filename):
            return send_from_directory("templates/assets/img", filename)
        if os.path.isfile("templates/assets/img/favicon/" + filename):
            return send_from_directory("templates/assets/img/favicon", filename)

    return render_template("404.html"), 404


# region Special routes
@app.route("/favicon.png")
def faviconPNG():
    return send_from_directory("templates/assets/img", "favicon.png")


@app.route("/.well-known/<path:path>")
def wellknown(path):
    # Try to proxy to https://nathan.woodburn.au/.well-known/
    req = requests.get(f"https://nathan.woodburn.au/.well-known/{path}")
    return make_response(
        req.content, 200, {"Content-Type": req.headers["Content-Type"]}
    )


# endregion


# region Main routes
@app.route("/")
def index():
    current_datetime = datetime.now().strftime("%d %b %Y %I:%M %p")
    return render_template("index.html", datetime=current_datetime)


@app.route("/tx/<path:tx_hash>")
def tx_route(tx_hash):
    current_datetime = datetime.now().strftime("%d %b %Y %I:%M %p")
    return render_template("index.html", datetime=current_datetime)


@app.route("/block/<path:block_id>")
def block_route(block_id):
    current_datetime = datetime.now().strftime("%d %b %Y %I:%M %p")
    return render_template("index.html", datetime=current_datetime)


@app.route("/header/<path:block_id>")
def header_route(block_id):
    current_datetime = datetime.now().strftime("%d %b %Y %I:%M %p")
    return render_template("index.html", datetime=current_datetime)


@app.route("/address/<path:address>")
def address_route(address):
    current_datetime = datetime.now().strftime("%d %b %Y %I:%M %p")
    return render_template("index.html", datetime=current_datetime)


@app.route("/name/<path:name>")
def name_route(name):
    current_datetime = datetime.now().strftime("%d %b %Y %I:%M %p")
    return render_template("index.html", datetime=current_datetime)


@app.route("/coin/<path:coin_hash>/<int:index>")
def coin_route(coin_hash, index):
    current_datetime = datetime.now().strftime("%d %b %Y %I:%M %p")
    return render_template("index.html", datetime=current_datetime)


@app.route("/<path:path>")
def catch_all(path: str):
    if os.path.isfile("templates/" + path):
        return render_template(path)

    # Try with .html
    if os.path.isfile("templates/" + path + ".html"):
        return render_template(path + ".html")

    if os.path.isfile("templates/" + path.strip("/") + ".html"):
        return render_template(path.strip("/") + ".html")

    # Try to find a file matching
    if path.count("/") < 1:
        # Try to find a file matching
        filename = find(path, "templates")
        if filename:
            return send_file(filename)

    return render_template("404.html"), 404


# endregion


# region Error Catching
# 404 catch all
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


# endregion
if __name__ == "__main__":
    app.run(debug=True, port=5000, host="127.0.0.1")
