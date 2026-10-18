# Repository Guidelines

## Project Overview

Flask image uploader backed by Cloudflare R2 (S3-compatible). Handles image conversion, watermarking, thumbnail generation, and variant uploads for the public and private buckets (names from `PUBLIC_BUCKET` / `PRIVATE_BUCKET`). Batch migration of existing R2 images handled offline via `migrate_images.py`.

- Runtime: Python 3.11, Flask + Gunicorn (gevent workers)
- Image processing: Pillow + Wand (ImageMagick), `webp` CLI
- Storage: Cloudflare R2 via `boto3`

## Architecture & Data Flow

```
Client --Bearer auth--> Flask (app.py) --boto3--> R2 (public/private buckets)
                          |
                          +-- Pillow/Wand: resize, watermark, convert (jpg/webp), EXIF strip
                          +-- Thumbnail generation: 320px / 640px variants
```

- **Upload flow** (`POST /upload`): auth check -> validate extension -> random 7-char filename -> `upload_watermark()` (watermark + resize) -> `generate_thumbnails()` -> `convert_webp()` -> `upload_to_r2_cloudflare()` to both buckets (public gets watermarked + variants; private gets original).
- **Bucket routing**: `PUBLIC_BUCKET` = full processing pipeline; `PRIVATE_BUCKET` = store original only; other buckets = dedup suffix (4 chars) and passthrough.
- **Other endpoints**: `POST /upload_original`, `POST /upload_custom`, `POST /delete`, `DELETE /delete/<key>`, `POST /fetch`, `POST /list`, `GET /check_file_exists`, `GET /image/<path>`, `GET /`.
- **Migration** (`migrate_images.py`): lists master files (excludes `*-320.*`/`*-640.*` thumbnails), checks missing variants, generates thumbnails locally in `migration_temp/`, uploads to R2. Resumable via `migration_state.json`, batched (`BATCH_SIZE=50`, `RATE_LIMIT_DELAY=0.1s`), with retries.

## Key Directories

| Path | Purpose |
|------|---------|
| `app.py` | Main Flask app — all routes and image processing logic (~1100 lines, monolithic) |
| `migrate_images.py` | Offline R2 migration — thumbnail backfill with state tracking |
| `strip_metadata.py` / `strip_temp/` | EXIF/metadata stripping utility |
| `optimize_thumbnails.py` / `optimization_temp/` | Thumbnail optimization |
| `get_jpg_quality.py` | JPEG quality detection helper |
| `uploads/` / `output/` | Local temp dirs (gitignored via `*.jpg` etc.) |
| `migration_temp/` | Migration temp downloads (gitignored) |
| `Dockerfile` / `gunicorn.py` | Container + server config |

No `src/`, `tests/`, or `scripts/` directories — flat layout.

## Development Commands

```bash
# Local dev (Flask debug)
python app.py                          # runs on default Flask port with debug=True
# Production (Gunicorn)
gunicorn --config gunicorn.py app:app  # 4 gevent workers on 0.0.0.0:5002
# Docker
docker build -t img-uploader . && docker run -p 5002:5002 --env-file .env img-uploader

# Migration (dry-run first)
python migrate_images.py --dry-run
python migrate_images.py --dry-run --limit 10
python migrate_images.py               # live run
python migrate_images.py --resume      # resume from migration_state.json

# Metadata/optimization helpers
python strip_metadata.py
python optimize_thumbnails.py
bash run_strip_metadata.sh
bash run_optimization.sh
bash run_migration.sh
bash download_backups.sh

# Type checking
pyright                                # checks app.py, migrate_images.py, get_jpg_quality.py, wsgi.py

# Linting (ruff — rule set pinned in ruff.toml, must stay green)
ruff check .                              # gate
ruff check --fix .                        # autofix before committing
ruff format .                             # opt-in, not enforced
```

No `package.json`, `Makefile`, or test runner. Install deps: `pip install -r requirements.txt` (requires `libmagickwand-dev` + `webp` system packages).

## Code Conventions & Common Patterns

- **Auth**: every endpoint checks `Authorization: Bearer <SECRET_KEY>` (`SECRET_KEY` env var, also `API_KEY` alias in code). Return `401` on failure.
- **Error handling**: `try/except` with `jsonify({"error": ...}), 500` — no centralized error handler. Print to stdout for errors.
- **Image processing**: Wand `limits` capped at `512MB` memory / `1GB` map (top of `app.py`). Resize guards at `1920px` (upload) / `800px` (migration).
- **Filename generation**: `generate_random_filename()` (7 chars) for public uploads; `generate_unique_filename()` / `generate_unique_document_filename()` (4-char suffix) for generic buckets.
- **R2 access**: `boto3.client("s3", endpoint_url=CF_ENDPOINT, ...)` per call — no shared client singleton.
- **No DI / no ORM / no state management** — plain functions, env-based config via `python-dotenv`.
- **Naming**: `snake_case` for functions/vars, `UPPER_SNAKE` for env-derived constants.
- **Formatting**: no enforced formatter; 4-space indent. `ruff format` is available but optional.

## Important Files

| File | Role |
|------|------|
| `app.py` | Entry point — all routes, image pipeline (`upload_watermark`, `add_watermark_and_convert`, `generate_thumbnails`, `convert_webp`, `resize_image`) |
| `requirements.txt` | Pinned prod deps (Flask 3.0.3, Pillow 11.0.0, Wand 0.6.13, boto3 1.35.49, gevent 24.10.3) |
| `gunicorn.py` | `bind 0.0.0.0:5002`, 4 gevent workers, 60s timeout |
| `pyrightconfig.json` | Type checking — includes `app.py`, `migrate_images.py`, `get_jpg_quality.py`, `wsgi.py` |
| `ruff.toml` | Lint rule set (pinned so `ruff check` is deterministic across machines) |
| `.env` / `.env.example` | `CF_ACCESS_KEY`, `CF_SECRET_KEY`, `CF_ENDPOINT`, `SECRET_KEY`, `PUBLIC_BUCKET`, `PRIVATE_BUCKET`, `ALLOW_HOSTS` |
| `Dockerfile` | `python:3.11-slim`, installs `libmagickwand-dev` + `webp`, runs gunicorn |
| `migrate_images.py` | `MigrationState`, `Logger`, `process_single_file()`, `get_master_files()` |
| `MIGRATION_README.md` | Migration usage docs |
| `.gitignore` | Ignores `*.webp/*.png/*.jpg/*.tif`, `.env`, `*.log`, `migration_temp/`, `migration_state.json`, `.venv/`, `.codegraph/`, `.omp/` |

## Runtime/Tooling Preferences

- **Python 3.11** (Docker base `python:3.11-slim`). No `pyproject.toml` / `setup.py` — flat `requirements.txt`.
- **Package manager**: `pip` with `requirements.txt`. System deps required: `libmagickwand-dev`, `webp`.
- **Server**: Gunicorn + gevent (not Flask dev server in prod). Port `5002`.
- **Env**: `python-dotenv` loads `.env`; `ALLOW_HOSTS` controls CORS origins (default `*`).
- **Type checking**: `pyright` (config in `pyrightconfig.json`, venv at `.venv`).
- **Linting**: `ruff` (rule set pinned in `ruff.toml`; `BLE001`, `S201`, `S603` ignored on purpose).
- **No Node / no Bun / no frontend tooling**.

## Testing & QA

- **No test suite exists** — no `tests/`, `test_*.py`, `pytest.ini`, or test deps in `requirements.txt`.
- **Manual verification**: use `migrate_images.py --dry-run --limit N` for migration; `curl` against endpoints with `Authorization: Bearer <SECRET_KEY>` for upload/fetch/list/delete.
- **Type checking** is the primary automated QA: `pyright` (run after changes to `app.py` / `migrate_images.py`).
- **Linting** is the second automated gate: `ruff check .` must pass (rule set in `ruff.toml`).
- **If adding tests**: `pip install pytest pytest-flask`, place in `tests/test_*.py`, run `pytest`. Add `pytest`/`coverage` to requirements or a dev requirements file.
- **ImageMagick limits**: test large images locally — `512MB` memory cap can OOM on high-res inputs; check `limits` in `app.py:25`.
