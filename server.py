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
from urllib.parse import urlencode
from xml.sax.saxutils import escape
import dotenv
from tools import hip2, wallet_txt

dotenv.load_dotenv()

app = Flask(__name__)

DATABASE = os.getenv("DATABASE_PATH", "fireexplorer.db")
HSD_API_BASE = os.getenv("HSD_API_BASE", "https://hsd.hns.au/api/v1")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")


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


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def _safe_hns_value(value) -> str:
    try:
        return f"{float(value) / 1e6:,.2f} HNS"
    except Exception:
        return "Unknown"


def _format_int(value, fallback: str = "?") -> str:
    try:
        return f"{int(value):,}"
    except Exception:
        return fallback


def _ellipsize_middle(text: str, max_length: int = 48) -> str:
    if len(text) <= max_length:
        return text
    if max_length < 7:
        return _truncate(text, max_length)
    left = (max_length - 1) // 2
    right = max_length - left - 1
    return f"{text[:left]}…{text[-right:]}"


def _fetch_explorer_json(endpoint: str):
    try:
        req = requests.get(f"{HSD_API_BASE}/{endpoint}", timeout=4)
        if req.status_code == 200:
            return req.json(), None
        return None, f"HTTP {req.status_code}"
    except Exception as e:
        return None, str(e)


def _get_public_base_url() -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    return request.url_root.rstrip("/")


def _build_og_context(
    search_type: str | None = None, search_value: str | None = None
) -> dict:
    default_title = "Fire Explorer"
    default_description = "A hot new Handshake Blockchain Explorer"

    if not search_type or not search_value:
        return {
            "title": default_title,
            "description": default_description,
            "image_query": {"title": default_title, "subtitle": default_description},
        }

    type_labels = {
        "block": "Block",
        "header": "Header",
        "tx": "Transaction",
        "address": "Address",
        "name": "Name",
    }
    label = type_labels.get(search_type, "Search")

    fallback_title = f"{label} {search_value} | Fire Explorer"
    fallback_description = f"View Handshake {label.lower()} details for {search_value}"

    og = {
        "title": _truncate(fallback_title, 100),
        "description": _truncate(fallback_description, 200),
        "image_query": {
            "type": label,
            "value": search_value,
            "title": fallback_title,
            "subtitle": fallback_description,
        },
    }

    if search_type == "block":
        block, err = _fetch_explorer_json(f"block/{search_value}")
        if not err and block:
            tx_count = len(block.get("txs", []))
            height = block.get("height", "?")
            timestamp = block.get("time")
            time_str = (
                datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M UTC")
                if timestamp
                else "Unknown time"
            )
            height_fmt = _format_int(height)
            tx_count_fmt = _format_int(tx_count, "0")
            subtitle = f"Height {height_fmt} • {tx_count_fmt} txs • {time_str}"
            og["title"] = _truncate(f"Block {height_fmt} | Fire Explorer", 100)
            og["description"] = _truncate(subtitle, 200)
            og["image_query"]["subtitle"] = subtitle

    elif search_type == "header":
        header, err = _fetch_explorer_json(f"header/{search_value}")
        if not err and header:
            height = header.get("height", "?")
            bits = header.get("bits", "?")
            subtitle = f"Height {height} • Bits {bits}"
            og["title"] = _truncate(f"Header {height} | Fire Explorer", 100)
            og["description"] = _truncate(subtitle, 200)
            og["image_query"]["subtitle"] = subtitle

    elif search_type == "tx":
        tx, err = _fetch_explorer_json(f"tx/{search_value}")
        if not err and tx:
            inputs = len(tx.get("inputs", []))
            outputs = len(tx.get("outputs", []))
            fee = _safe_hns_value(tx.get("fee"))
            subtitle = f"{inputs} inputs • {outputs} outputs • Fee {fee}"
            og["title"] = _truncate("Transaction | Fire Explorer", 100)
            og["description"] = _truncate(subtitle, 200)
            og["image_query"]["subtitle"] = subtitle

    elif search_type == "address":
        txs, err = _fetch_explorer_json(f"tx/address/{search_value}")
        if not err and isinstance(txs, list):
            subtitle = f"{len(txs)} related transactions found"
            og["title"] = _truncate("Address | Fire Explorer", 100)
            og["description"] = _truncate(subtitle, 200)
            og["image_query"]["subtitle"] = subtitle

    elif search_type == "name":
        name, err = _fetch_explorer_json(f"name/{search_value}")
        if not err and name:
            info = name.get("info", name)
            state = info.get("state", "Unknown")
            owner = info.get("owner", {}).get("hash", "Unknown")
            subtitle = f"State: {state} • Owner: {_truncate(owner, 26)}"
            og["title"] = _truncate(f"Name {search_value} | Fire Explorer", 100)
            og["description"] = _truncate(subtitle, 200)
            og["image_query"]["subtitle"] = subtitle

    og["image_query"]["title"] = og["title"]
    return og


def _render_index(search_type: str | None = None, search_value: str | None = None):
    current_datetime = datetime.now().strftime("%d %b %Y %I:%M %p")
    og_context = _build_og_context(search_type, search_value)
    image_query = og_context["image_query"]
    public_base_url = _get_public_base_url()
    og_image_url = public_base_url + "/og-image?" + urlencode(image_query)
    og_url = public_base_url + request.full_path
    if og_url.endswith("?"):
        og_url = og_url[:-1]

    twitter_domain = request.host
    if PUBLIC_BASE_URL and "//" in PUBLIC_BASE_URL:
        twitter_domain = PUBLIC_BASE_URL.split("//", 1)[1]

    return render_template(
        "index.html",
        datetime=current_datetime,
        meta_title=og_context["title"],
        meta_description=og_context["description"],
        og_url=og_url,
        og_image=og_image_url,
        twitter_domain=twitter_domain,
    )


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
    return _render_index()


@app.route("/tx/<path:tx_hash>")
def tx_route(tx_hash):
    return _render_index("tx", tx_hash)


@app.route("/block/<path:block_id>")
def block_route(block_id):
    return _render_index("block", block_id)


@app.route("/header/<path:block_id>")
def header_route(block_id):
    return _render_index("header", block_id)


@app.route("/address/<path:address>")
def address_route(address):
    return _render_index("address", address)


@app.route("/name/<path:name>")
def name_route(name):
    return _render_index("name", name)


@app.route("/coin/<path:coin_hash>/<int:index>")
def coin_route(coin_hash, index):
    return _render_index("coin", f"{coin_hash}:{index}")


@app.route("/og-image")
def og_image():
    title = _truncate(request.args.get("title", "Fire Explorer"), 90)
    subtitle = _truncate(
        request.args.get("subtitle", "A hot new Handshake Blockchain Explorer"),
        140,
    )
    search_type = _truncate(request.args.get("type", "Explorer"), 24)
    search_value = request.args.get("value", "")

    normalized_type = search_type.strip().lower()
    value_max_length = 44
    if normalized_type in {"transaction", "tx"}:
        value_max_length = 30

    display_value = _ellipsize_middle(search_value, value_max_length)
    value_font_size = "30"
    if len(display_value) > 34:
        value_font_size = "26"
    is_default_card = not search_value.strip() and normalized_type in {
        "explorer",
        "search",
        "",
    }

    type_text = escape(search_type)
    value_text = escape(display_value)
    title_text = escape(title)
    subtitle_text = escape(subtitle)

    if is_default_card:
        svg = f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1200\" height=\"630\" viewBox=\"0 0 1200 630\">
    <defs>
        <linearGradient id=\"bg\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\">
            <stop offset=\"0%\" stop-color=\"#0b1220\" />
            <stop offset=\"100%\" stop-color=\"#1f2937\" />
        </linearGradient>
        <linearGradient id=\"accent\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"0\">
            <stop offset=\"0%\" stop-color=\"#ef4444\" />
            <stop offset=\"100%\" stop-color=\"#f97316\" />
        </linearGradient>
    </defs>
    <rect width=\"1200\" height=\"630\" fill=\"url(#bg)\" />
    <circle cx=\"1100\" cy=\"80\" r=\"180\" fill=\"#ef4444\" opacity=\"0.16\" />
    <circle cx=\"120\" cy=\"610\" r=\"240\" fill=\"#f97316\" opacity=\"0.14\" />
    <rect x=\"86\" y=\"74\" width=\"1028\" height=\"482\" rx=\"28\" fill=\"#0f172a\" stroke=\"#374151\" />
    <rect x=\"130\" y=\"126\" width=\"176\" height=\"42\" rx=\"21\" fill=\"url(#accent)\" />
    <text x=\"218\" y=\"153\" text-anchor=\"middle\" fill=\"#ffffff\" font-size=\"19\" font-family=\"Inter, Arial, sans-serif\" font-weight=\"700\">Handshake</text>
    <text x=\"130\" y=\"246\" fill=\"#ffffff\" font-size=\"82\" font-family=\"Inter, Arial, sans-serif\" font-weight=\"800\">{title_text}</text>
    <text x=\"130\" y=\"302\" fill=\"#d1d5db\" font-size=\"32\" font-family=\"Inter, Arial, sans-serif\">{subtitle_text}</text>
    <line x1=\"130\" y1=\"338\" x2=\"1070\" y2=\"338\" stroke=\"#374151\" />
    <text x=\"130\" y=\"402\" fill=\"#f9fafb\" font-size=\"34\" font-family=\"Inter, Arial, sans-serif\" font-weight=\"600\">Blocks • Transactions • Addresses • Names</text>
    <text x=\"130\" y=\"452\" fill=\"#9ca3af\" font-size=\"28\" font-family=\"Inter, Arial, sans-serif\">Real-time status, searchable history, and rich on-chain data.</text>
    <text x=\"86\" y=\"608\" fill=\"#9ca3af\" font-size=\"24\" font-family=\"Inter, Arial, sans-serif\">explorer.hns.au</text>
</svg>"""
    else:
        svg = f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1200\" height=\"630\" viewBox=\"0 0 1200 630\">
    <defs>
        <linearGradient id=\"bg\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\">
            <stop offset=\"0%\" stop-color=\"#111827\" />
            <stop offset=\"100%\" stop-color=\"#1f2937\" />
        </linearGradient>
        <linearGradient id=\"accent\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"0\">
            <stop offset=\"0%\" stop-color=\"#ef4444\" />
            <stop offset=\"100%\" stop-color=\"#f97316\" />
        </linearGradient>
        <clipPath id=\"valueClip\">
            <rect x=\"96\" y=\"496\" width=\"1008\" height=\"52\" rx=\"4\" />
        </clipPath>
    </defs>
    <rect width=\"1200\" height=\"630\" fill=\"url(#bg)\" />
    <circle cx=\"1040\" cy=\"120\" r=\"180\" fill=\"#ef4444\" opacity=\"0.14\" />
    <circle cx=\"160\" cy=\"580\" r=\"220\" fill=\"#f97316\" opacity=\"0.12\" />
    <rect x=\"72\" y=\"64\" width=\"240\" height=\"44\" rx=\"22\" fill=\"url(#accent)\" />
    <text x=\"192\" y=\"92\" text-anchor=\"middle\" fill=\"#ffffff\" font-size=\"20\" font-family=\"Inter, Arial, sans-serif\" font-weight=\"700\">{type_text}</text>
    <text x=\"72\" y=\"188\" fill=\"#ffffff\" font-size=\"62\" font-family=\"Inter, Arial, sans-serif\" font-weight=\"700\">{title_text}</text>
    <text x=\"72\" y=\"252\" fill=\"#d1d5db\" font-size=\"33\" font-family=\"Inter, Arial, sans-serif\">{subtitle_text}</text>
    <rect x=\"72\" y=\"472\" width=\"1056\" height=\"96\" rx=\"16\" fill=\"#0b1220\" stroke=\"#374151\" />
    <text x=\"96\" y=\"530\" clip-path=\"url(#valueClip)\" fill=\"#f9fafb\" font-size=\"{value_font_size}\" font-family=\"'JetBrains Mono', 'Consolas', monospace\">{value_text}</text>
    <text x=\"72\" y=\"610\" fill=\"#9ca3af\" font-size=\"24\" font-family=\"Inter, Arial, sans-serif\">explorer.hns.au</text>
</svg>"""

    response = make_response(svg)
    response.headers["Content-Type"] = "image/svg+xml; charset=utf-8"
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


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
    # Count number of names in database
    db = get_db()
    cur = db.execute("SELECT COUNT(*) as count FROM names")
    row = cur.fetchone()
    name_count = row["count"] if row else 0

    return jsonify(
        {
            "status": "ok",
            "service": "FireExplorer",
            "version": "1.0.0",
            "names_cached": name_count,
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

    if isinstance(data, list):
        covenants = data
        results = []

        # Collect all namehashes needed
        namehashes = set()
        for cov in covenants:
            items = cov.get("items", [])
            if items:
                namehashes.add(items[0])

        # Batch DB lookup
        db = get_db()
        known_names = {}
        if namehashes:
            placeholders = ",".join("?" for _ in namehashes)
            cur = db.execute(
                f"SELECT namehash, name FROM names WHERE namehash IN ({placeholders})",
                list(namehashes),
            )
            for row in cur:
                known_names[row["namehash"]] = row["name"]

        # Identify missing namehashes
        missing_hashes = [nh for nh in namehashes if nh not in known_names]

        # Fetch missing from HSD
        session = requests.Session()
        for nh in missing_hashes:
            try:
                req = session.get(f"https://hsd.hns.au/api/v1/namehash/{nh}")
                if req.status_code == 200:
                    name = req.json().get("result")
                    if name:
                        known_names[nh] = name
                        # Update DB
                        db.execute(
                            "INSERT OR REPLACE INTO names (namehash, name) VALUES (?, ?)",
                            (nh, name),
                        )
            except Exception as e:
                print(f"Error fetching namehash {nh}: {e}")

        db.commit()

        # Build results
        for cov in covenants:
            action = cov.get("action")
            items = cov.get("items", [])

            if not action:
                results.append({"covenant": cov, "display": "Unknown"})
                continue

            display = f"{action}"
            if items:
                nh = items[0]
                if nh in known_names:
                    name = known_names[nh]
                    display += f' <a href="/name/{name}">{name}</a>'

            results.append({"covenant": cov, "display": display})

        return jsonify(results)

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
