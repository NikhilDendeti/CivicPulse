# CivicPulse

**Transparent civic grievance and infrastructure triage for Hyderabad.**
Built for the Forge Gen AI Buildathon, Theme 1: Civic Pulse, Digital Governance & Public Information.

A citizen photographs or describes a civic problem (pothole, water leak, garbage, broken streetlight, drainage overflow) by voice in Telugu or English. AI classifies the issue and scores how dangerous it is, a routing agent finds the responsible department and emails a structured complaint, and the department acknowledges it from a no-login link. Every case gets a public status page and feeds an open accountability dashboard.

> **Vision:** any citizen can report a civic problem in seconds, and anyone can see what happened next.

## Why

- Complaints are scattered across portals, phone lines and social media, with no clear owner.
- Authorities see complaints in arrival order, not in order of danger.
- Citizens cannot see whether anything was acknowledged or fixed, and nobody can compare wards or departments.
- Many people can speak or photograph a problem but cannot write a formal complaint in English.

## Features

| Area | What it does |
|---|---|
| Reporting | Photo, short voice note and/or text; GPS with a draggable map pin; on-device image compression; offline upload queue; English and Telugu UI |
| AI analysis | Vision model classifies the issue and returns structured JSON: category, severity, confidence, plain-language rationale |
| Severity | Model score plus deterministic context from OpenStreetMap (nearby schools/hospitals, road class) and live rainfall (Open-Meteo); every adjustment is listed |
| Guardrails | Low confidence triggers a clarifying question; still unsure, irrelevant, flagged or AI-unavailable reports go to a human moderator instead of a guess |
| Authenticity | EXIF stripped, perceptual-hash reuse detection, photo/GPS mismatch checks |
| Duplicates | Same category within 60 m and similar description or near-identical image are merged and the affected-citizen count rises |
| Routing agent | An LLM with tools (`find_authorities`, `send_dispatch`, `flag_for_moderator`) picks the authority and records its reason; a rule-based fallback is used if the model is unavailable |
| Dispatch | Structured complaint emailed with retry and backoff; falls back to the escalation parent if delivery fails; auto-escalates if not acknowledged in time |
| Officer loop | Tokenised, login-free page to acknowledge, mark in progress or resolve (with an optional proof photo) |
| Accountability | Public map, per-report timeline, ward and department metrics (median time to acknowledge/resolve, reopen rate, aging backlog), CSV open-data export |
| Moderation | Django admin queue with Approve and route, Re-run analysis and Reject; corrections are logged as feedback |

## Architecture

```
React PWA (camera, mic, GPS, offline queue)
        |  REST (multipart / JSON)
Django + DRF API  ---------------  Public dashboard / status pages
        |
   Pipeline (Celery worker, or a background thread without Redis)
        |-- Sarvam: speech-to-text + translation (Telugu/English)
        |-- OpenAI: vision classification -> structured JSON
        |-- OSM Nominatim / Overpass, Open-Meteo: address, ward, severity context
        |-- Confidence gate -> clarifying question | moderator | continue
        |-- Duplicate check (radius + embeddings / image hash)
        '-- Routing agent (OpenAI tool calls) -> email dispatch -> ack link -> escalation
```

Report states: `submitted -> analysing -> (needs_info | needs_review | analysed) -> merged | routed -> sent -> acknowledged -> in_progress -> resolved -> (disputed -> reopened)`

### Code map

| Concern | Location |
|---|---|
| Upload handling, EXIF strip, hashing | `backend/apps/reports/media.py`, `views.py` |
| External clients (OpenAI, Sarvam, OSM, weather) | `backend/apps/pipeline/clients.py` |
| Vision analysis + prompt (`analysis-v1`) | `backend/apps/pipeline/analysis.py` |
| Severity context | `backend/apps/pipeline/severity.py` |
| Workflow, confidence gate, escalation | `backend/apps/pipeline/tasks.py` |
| Duplicate detection | `backend/apps/pipeline/duplicates.py` |
| Routing agent | `backend/apps/pipeline/routing.py` |
| Complaint email, retry, fallback | `backend/apps/dispatch/services.py` |
| Officer acknowledge page | `backend/apps/dispatch/views.py`, `templates/` |
| Dashboard API and CSV | `backend/apps/dashboard/views.py` |
| Wards, authorities, geometry | `backend/apps/authorities/` |
| Frontend pages and offline queue | `frontend/src/pages/`, `frontend/src/lib/offlineQueue.ts` |

## Tech stack

- **Frontend:** React 18, TypeScript, Vite, PWA (`vite-plugin-pwa`), Leaflet, i18next
- **Backend:** Django 5, Django REST Framework, Celery (optional), Shapely, Pillow, imagehash
- **AI:** OpenAI (vision, tool calling, embeddings), Sarvam (speech-to-text, translation)
- **Data:** OpenStreetMap (Nominatim, Overpass), Open-Meteo; SQLite for local dev, Postgres in production

## Getting started

Requirements: Python 3.12+, Node 20+.

```bash
# 1. Backend
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # macOS/Linux: .venv/bin/python
cp .env.example .env                                         # then fill in keys (see below)
.venv/Scripts/python manage.py migrate
.venv/Scripts/python manage.py load_authorities
.venv/Scripts/python manage.py createsuperuser
.venv/Scripts/python manage.py runserver

# 2. Frontend (second terminal)
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to :8000
```

Phones only allow camera, microphone and GPS over HTTPS, so test on a device through a deployed URL or an HTTPS tunnel.

Production-style stack (Postgres, Redis, Celery worker and beat): `docker compose up --build`.

### Configuration (`backend/.env`)

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Vision analysis, routing agent, embeddings. Without it, reports go to human review. |
| `SARVAM_API_KEY` | Voice-note transcription and translation. |
| `DISPATCH_MODE` | `sandbox` (default) sends every complaint to `SANDBOX_EMAIL`; `live` sends to verified authority channels only. |
| `SANDBOX_EMAIL` | Team inbox that receives complaints in sandbox mode. |
| `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | SMTP. If `EMAIL_HOST` is empty, emails print to the console. |
| `NOMINATIM_USER_AGENT` | Identify your app to OpenStreetMap (include a contact). |
| `DATABASE_URL`, `CELERY_BROKER_URL` | Postgres and Redis for deployment. |

See `backend/.env.example` for the complete list. Never commit `.env`.

## Tests

```bash
cd backend && .venv/Scripts/python -m pytest
cd frontend && npm run build
```

The backend suite is hermetic (no network, no API keys). It covers the full report-to-resolution flow, duplicate merging, low-confidence handling, AI-unavailable behaviour, delivery retry and fallback, live-mode safety, escalation and the dashboard.

## Real data policy

The buildathon forbids mock data, and this repository ships none: no seeded reports, no placeholder metrics, no invented contact addresses.

- **Reports** come only from live submissions. An empty database shows an honest empty dashboard.
- **Ward boundaries**: load real GHMC GeoJSON with `python manage.py load_wards <file> --name-field <prop> --source-url <url>` after checking its licence.
- **Authority directory**: edit `backend/data/authorities.json`, add only published complaint emails you have actually verified, and record how in `verification_note`. Unverified channels are never used in live mode.
- **Dispatch safety**: keep `DISPATCH_MODE=sandbox` while developing; switch to `live` only for a demo, after confirming the recipient.
- **Evaluation**: label real reports in a CSV (`ref_no,category,severity_level,authority_slug`) and run `python manage.py evaluate labels.csv`. Report the sample size and the failures.

## Privacy

Consent is required to submit. EXIF is stripped from stored images, public pages show coordinates rounded to about 100 m, the exact address and transcript are visible only to the reporting device, and unreviewed or rejected images are not shown publicly. The open-data export excludes tokens, contact details, free text and exact coordinates.

## Known limitations

- Face and licence-plate blurring is not implemented.
- Push and SMS notifications are not built; email and the status page are the channels.
- There is no officer login console; departments use the emailed bearer-token link, and moderators use Django admin.
- The officer link works for anyone who holds it.
- Overpass (OpenStreetMap) is a public server and sometimes times out; severity then records "lookup unavailable" rather than guessing.
- Geometry uses Shapely and haversine in Python, and embeddings are stored as JSON. This suits pilot scale; PostGIS and pgvector are the upgrade path.
- Telugu UI strings were machine-drafted and need native review; confirm the audio formats your phones record are accepted by Sarvam.
- AI severity is decision support and can be wrong. Confidence and rationale are always shown.

## Roadmap

More categories and cities, SMS and WhatsApp reporting, before/after resolution verification, face and plate blurring, officer login console, and Open311-style integrations where a city offers an API.
