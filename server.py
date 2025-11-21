from flask import (
    Flask,
    make_response,
    render_template,
    send_from_directory,
    send_file,
    jsonify,
    g,
    request,
)
import os
import requests
import sqlite3
from datetime import datetime
import dotenv
from tools import hip2, wallet_txt

dotenv.load_dotenv()

app = Flask(__name__)

DATABASE = os.getenv("DATABASE_PATH", "fireexplorer.db")


def get_db():
    db = getattr(g, "_database", None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()


def init_db():
    with app.app_context():
        db = get_db()
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS names (
                namehash TEXT PRIMARY KEY,
                name TEXT NOT NULL
            )
        """
        )
        db.commit()


init_db()


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


# region API routes
@app.route("/api/v1/namehash/<namehash>")
def namehash_api(namehash):
    db = get_db()
    cur = db.execute("SELECT * FROM names WHERE namehash = ?", (namehash,))
    row = cur.fetchone()
    if row is None:
        # Get namehash from hsd.hns.au
        req = requests.get(f"https://hsd.hns.au/api/v1/namehash/{namehash}")
        if req.status_code == 200:
            name = req.json().get("result")
            if not name:
                return jsonify({"name": "Error", "namehash": namehash})
            # Insert into database
            db.execute(
                "INSERT OR REPLACE INTO names (namehash, name) VALUES (?, ?)",
                (namehash, name),
            )
            db.commit()
            return jsonify({"name": name, "namehash": namehash})
    return jsonify(dict(row))


@app.route("/api/v1/status")
def api_status():
    return jsonify(
        {
            "status": "ok",
            "service": "FireExplorer",
            "version": "1.0.0",
        }
    )


@app.route("/api/v1/hip02/<domain>")
def hip02(domain: str):
    hip2_record = hip2(domain)
    if hip2_record:
        return jsonify(
            {
                "success": True,
                "address": hip2_record,
                "method": "hip02",
                "name": domain,
            }
        )

    wallet_record = wallet_txt(domain)
    if wallet_record:
        return jsonify(
            {
                "success": True,
                "address": wallet_record,
                "method": "wallet_txt",
                "name": domain,
            }
        )
    return jsonify(
        {
            "success": False,
            "name": domain,
            "error": "No HIP02 or WALLET record found for this domain",
        }
    )


@app.route("/api/v1/covenant", methods=["POST"])
def covenant_api():
    data = request.get_json()
    # Get the covenant data
    action = data.get("action")
    items = data.get("items", [])

    if not action:
        return jsonify({"success": False, "data": data})

    display = f"{action}"
    if len(items) > 0:
        name_hash = items[0]
        # Lookup name from database
        db = get_db()
        cur = db.execute("SELECT * FROM names WHERE namehash = ?", (name_hash,))
        row = cur.fetchone()
        if row:
            name = row["name"]
            display += f' <a href="/name/{name}">{name}</a>'
        else:
            req = requests.get(f"https://hsd.hns.au/api/v1/namehash/{name_hash}")
            if req.status_code == 200:
                name = req.json().get("result")
                if name:
                    display += f" {name}"
                    # Insert into database
                    db.execute(
                        "INSERT OR REPLACE INTO names (namehash, name) VALUES (?, ?)",
                        (name_hash, name),
                    )
                    db.commit()

    return jsonify({"success": True, "data": data, "display": display})


# endregion


# region Error Catching
# 404 catch all
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


# endregion
if __name__ == "__main__":
    app.run(debug=True, port=5000, host="127.0.0.1")
