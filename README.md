# ReadRight API

FastAPI microservice for **ReadRight Module 2** — the audio + video reading assessment pipeline. A student records themselves reading a Phil-IRI passage; the service extracts WAV + MP4 from the upload, runs GO2 (ASR → miscue classification → WPM/scoring) and GO3 (computer-vision behavioral flags + prosody) in parallel, merges the results into a single `AssessmentResult`, and persists a session row to Supabase.

## Requirements

- Python 3.12
- ffmpeg (system binary)
- A Supabase project (service role key)

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# ffmpeg
sudo apt-get install ffmpeg   # Debian/Ubuntu
sudo pacman -S ffmpeg         # Arch
brew install ffmpeg           # macOS

cp .env.example .env
# then fill in API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY, etc.
```

## Running

```bash
# from the project root, not from app/
uvicorn app.main:app --reload
```

## Testing & type checking

```bash
.venv/bin/pytest
.venv/bin/pyright app/   # strict — must be 0 errors before committing
```

## Deployment

Docker + Caddy (auto-HTTPS) via `docker-compose.yml` — see the comments in that file and in `Caddyfile` for host setup, and `.github/workflows/deploy.yml` for the CI pipeline (test → build/push to GHCR → SSH deploy) and its required repo secrets.

Before first deploy, create these in the Supabase project (not done by code):
- A `sessions` table matching `SessionRecord` (`app/models/session.py`) — insert failure is non-fatal, so a missing table won't break `/analyze`, but session history silently won't persist.
- A **private** `recordings` storage bucket — same non-fatal treatment; a missing bucket just means the extracted audio silently never gets uploaded.

## API

### `POST /analyze`

Multipart form upload. Requires `X-API-Key` header (must match `API_KEY` in `.env`).

| Field | Type | Required |
|---|---|---|
| `file` | video/audio upload | yes |
| `passage_id` | form string | yes |
| `learner_id` | form string | no — omitting it skips the Supabase session insert |

Returns an `AssessmentResult`. On failure, returns `500` with `{"error", "code"}` where `code` is one of `EXTRACTION_FAILED`, `ANALYSIS_FAILED`, `CONSOLIDATION_FAILED`.

### `GET /health`

Liveness check, no auth required.

## Architecture

```
app/
  main.py                       # App factory + lifespan (WhisperX, MediaPipe, Supabase preload here)
  config.py                     # pydantic-settings Settings (API key, WhisperX, Supabase, CORS)
  dependencies.py               # FastAPI dependency providers — only place concretes are wired
  routers/
    analyze.py                  # AnalyzeController — POST /analyze, HTTP only
    health.py                   # HealthController — GET /health
  services/
    analysis_orchestrator.py    # AnalysisOrchestrator — async coordinator (GO2 ‖ GO3 → merge → DB)
    media_extractor.py          # MediaExtractor — ffmpeg subprocess, splits upload into wav + mp4
    go2/                        # ASR → Phil-IRI miscue classification → WPM/scoring
    go3/                        # MediaPipe CV flags + amplitude-based prosody
    db/                         # Supabase client + passage/session repositories
  models/                       # Pydantic models, TypedDicts, and Protocols (one file per domain)
  utils/result_consolidator.py  # Merges GO2 + GO3 dicts into AssessmentResult
tests/                          # pytest — test_rr020..rr032 cover each ticket
docs/                           # JOURNAL.md + hld/lld/uml Mermaid diagrams
```

Class-based controllers, Protocol interfaces, and singleton model loading at startup (never per-request) — see [CLAUDE.md](CLAUDE.md) for the full architecture guide and domain rules (miscue taxonomy, scoring formulas, orchestrator error codes).
