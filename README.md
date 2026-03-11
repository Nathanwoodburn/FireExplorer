# Fire Explorer

Fire Explorer is a Flask-based Handshake blockchain explorer UI and API.
It provides searchable views for blocks, transactions, addresses, and names, plus utility endpoints for namehash resolution, HIP-02 lookup, and covenant display rendering.

## Features

- Search Handshake data by block, header, transaction, address, and name.
- Route-based deep links such as `/tx/<hash>` and `/block/<height-or-hash>`.
- Dynamic Open Graph card generation at `/og-image` and `/og-image.png`.
- HIP-02 and WALLET DNS record resolution endpoint.
- SQLite namehash cache to reduce repeated upstream lookups.
- Single-container deployment flow with Docker.

## Tech Stack

- Python 3.13+
- Flask
- Gunicorn (started programmatically via `main.py`)
- SQLite (local cache DB)
- Pillow (OG image rendering)
- Requests and DNS tooling for Handshake integrations

## Project Layout

```text
.
|- main.py                 # Gunicorn entrypoint
|- server.py               # Flask app, routes, API, OG generation
|- tools.py                # HIP-02 and DNS helper functions
|- templates/              # HTML templates + static assets
|- pyproject.toml          # Project metadata and dependencies (uv)
|- requirements.txt        # Exported lock-style requirements
|- Dockerfile              # Container build and runtime setup
```

## Prerequisites

- Python 3.13 or newer
- `uv` (recommended) or `pip`
- OpenSSL CLI available in PATH (required for HIP-02 certificate checks in `tools.py`)

## Local Development

### Option 1: `uv` (recommended)

```bash
uv sync
uv run main.py
```

The app binds to `0.0.0.0:5000` when started through `main.py`.

### Option 2: `pip`

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
python main.py
```

### Flask debug mode

```bash
python server.py
```

This runs Flask's built-in development server at `127.0.0.1:5000`.

## Environment Variables

Configure via shell variables or a `.env` file.

- `WORKERS`
: Gunicorn worker count. Default: `1`.
- `THREADS`
: Gunicorn thread count per worker. Default: `2`.
- `DATABASE_PATH`
: SQLite file path for the namehash cache. Default: `fireexplorer.db`.
- `HSD_API_BASE`
: Upstream Handshake API base URL. Default: `https://hsd.hns.au/api/v1`.
- `PUBLIC_BASE_URL`
: Optional canonical public URL used for OG metadata generation.

## Docker

Build:

```bash
docker build -t fireexplorer .
```

Run:

```bash
docker run --rm -p 5000:5000 -v fireexplorer-data:/data fireexplorer
```

Container notes:

- The image runs `uv run main.py`.
- The default database path is set to `/data/fireexplorer.db`.
- A volume is declared at `/data` for persistence.

## HTTP Routes

### UI routes

- `/`
- `/block/<block_id>`
- `/header/<block_id>`
- `/tx/<tx_hash>`
- `/address/<address>`
- `/name/<name>`
- `/coin/<coin_hash>/<index>`
- `/og-image`
- `/og-image.png`

### API routes

- `GET /api/v1/status`
: Service health and local cache stats.
- `GET /api/v1/namehash/<namehash>`
: Resolves namehash to name (cached in SQLite).
- `GET /api/v1/hip02/<domain>`
: Resolves HIP-02, falls back to WALLET TXT-style record lookup.
- `POST /api/v1/covenant`
: Accepts one covenant object or an array and returns display-ready covenant labels, including cached name resolution.

## Development Tooling

Pre-commit config includes:

- `uv-lock`
- `uv-export`
- `ruff-check`
- `ruff-format`

Run hooks locally:

```bash
pre-commit run --all-files
```

## Notes

- Frontend requests blockchain data from `https://hsd.hns.au/api/v1/`.
- Namehash mappings are cached locally in SQLite to improve repeated lookups.
- HIP-02 resolution requires DNS-over-HTTPS access and OpenSSL availability.
