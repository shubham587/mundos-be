# MedCampaign Backend – Production Guide (FastAPI + MongoDB)

This document is an end‑to‑end, production‑ready guide to install, configure, and run the MedCampaign backend. It explains what the system does, how it is structured, how to operate it safely, and how to integrate Gmail, booking, and dashboards.

If you need a shorter overview, see `Readme.md`. This file goes deeper and is the one to use for real deployments.

---

## 1) What this backend does

- Outreach (Recovery / Recall): Contacts patients via email (or call in certain cases), logs the touch, summarizes the conversation, and schedules the next follow‑up.
- Email reply automation: Listens to Gmail (Pub/Sub push). For each patient reply, detects one of four intents and responds accordingly:
  - booking_request, service_denial, irrelevant_confused, question
- Booking flow: Exposes availability and books appointments; marks campaigns as booking completed.
- Dashboard: Live KPIs (active, engaged, handoffs), conversion rates (month, lifetime, 90‑day), charts for historical performance and appointments trend.

### High‑level data model
- Patients
- Campaigns (type, status, channel, follow_up_details, engagement_summary)
- Appointments (date, duration, status, service, doctor)
- Interactions (conversation log: incoming/outgoing)

---

## 2) Architecture at a glance

```mermaid
flowchart LR
  subgraph Client
    Web[Admin UI / Booking UI]
    Gmail[Gmail]
  end

  Web -->|HTTPS| API[(FastAPI app)]
  Gmail -->|Pub/Sub Push| API

  API -->|Async/Sync| DB[(MongoDB)]

  subgraph API Modules
    A1[Admin APIs]
    A2[Public Booking]
    A3[Email Reply Agent]
    A4[Outreach Agent]
    A5[Gmail Watch/Push]
  end

  API -.includes .-> A1
  API -.includes .-> A2
  API -.includes .-> A3
  API -.includes .-> A4
  API -.includes .-> A5
```

### Outreach agent (simple flow)
```mermaid
flowchart TD
  A[Agent started] --> B[Prepare message]
  B --> C{How to reach?}
  C -- sms --> D[Call patient]
  C -- Email --> E[Send email]
  D --> F[Log interaction]
  E --> F
  F --> G[Summarize]
  G --> H[Update campaign]
  H --> I[Plan next follow‑up]
  I --> J[Done]
```

### Email reply agent (simple flow)
```mermaid
flowchart TD
  A[Incoming email] --> B[Get context]
  B --> C[Understand message]
  C --> D[Save note]
  D --> E{Intent}
  E -- Booking request --> F[Prepare booking reply]
  E -- Says no --> G[Polite thank‑you]
  E -- Confused --> H[Short clarification]
  E -- Question --> I[Look up answer]
  E -- Other --> L[Short summary]
  I --> J{Answer found?}
  J -- Yes --> K[Prepare answer]
  J -- No --> M[Offer human help]
  F --> N[Send email]
  G --> N
  H --> N
  K --> N
  M --> N
  L --> N
  N --> O[Save outbound note]
  O --> P[Update campaign & next step]
  P --> Q[Done]
```

---

## 3) Repository layout (what lives where)

- `main.py` — App factory, CORS, health, Gmail watch and push endpoints, agent endpoints
- `api/v1/endpoints/` — Public booking, Admin dashboard/campaigns/appointments, Auth, Webhooks
- `agent/` — Outreach agent graph and nodes, SMTP+LLM services, simple Mongo helpers
- `email_reply_agent/reply_handler/` — Reply agent graph/nodes, KB prompts, Gmail sender, DB helpers
- `services/gmail/` — Gmail client and Pub/Sub push processor
- `db/database.py` — Motor client factory (async)
- `models/` — Pydantic models for collections
- `schemas/` — Request/response schemas
- `scripts/` — Seeding and utilities (optional demo data)

---

## 4) Requirements

- Python 3.12
- MongoDB (Atlas or self‑hosted, TLS recommended)
- Optional integrations: Gmail API (OAuth/Service Account + Pub/Sub), SMTP, Twilio/SMS/voice provider

---

## 5) Installation & environment

### 5.1 Create venv and install
```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5.2 Configure .env (use `sample.env`)
Core
```
ENVIRONMENT=production
ALLOWED_ORIGINS=https://your-admin.example,https://your-booking.example
MONGO_URI=mongodb+srv://user:pass@cluster/
MONGO_DB_NAME=medcampaign
JWT_SECRET_KEY=change-me
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
TZ=UTC
```

Branding and email (optional)
```
CLINIC_NAME=Your Clinic Name
CLINIC_PHONE=+1-555-123-4567
CONSULTING_DOCTOR=Dr. Smith
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=user@example.com
SMTP_PASSWORD=secret
SMTP_FROM_EMAIL=user@example.com
SMTP_FROM_NAME=Your Clinic
```

Gmail / Google (if enabling auto‑reply)
```
GOOGLE_CLIENT_SECRETS_FILE=/secure/google/confidential.json
GOOGLE_TOKEN_FILE=/secure/google/token.json
GMAIL_TOPIC_NAME=projects/<project>/topics/<topic>
GMAIL_LABEL_IDS=INBOX
GMAIL_LABEL_FILTER_ACTION=include
GMAIL_PROCESS_REPLIES_ONLY=false
PUBSUB_VERIFICATION_TOKEN=some-random-token
```

Twilio/SMS (optional demo endpoint)
```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_PHONE_NUMBER=+15551234567
```

> Keep secret files off git. Set absolute paths in env (e.g., `/secure/google/...`).

---

## 6) Running the service

### 6.1 Development
```bash
ENVIRONMENT=development uvicorn main:create_app --factory --host 0.0.0.0 --port 8000 --reload
```

### 6.2 Production
```bash
ENVIRONMENT=production uvicorn main:create_app --factory \
  --host 0.0.0.0 --port $PORT \
  --workers $(python -c "import os;print(max(1,os.cpu_count() or 1))") \
  --proxy-headers
```

Ingress should be HTTPS at the edge (CDN/LB). Set HSTS and redirect HTTP→HTTPS.

Health: `GET /` → `{ "status": "ok" }`

---

## 7) Gmail integration (step‑by‑step)

1. Create OAuth app + credentials; authorize once to produce `token.json` (place at `GOOGLE_TOKEN_FILE`).
2. Create Pub/Sub topic and push subscription to your public endpoint:
   - `POST https://<your-domain>/pubsub/push?token=$PUBSUB_VERIFICATION_TOKEN`
3. Allow ingress from Google to that path; ensure HTTPS.
4. Start a Gmail watch once (or rely on the auto‑watch task):
   - `POST /gmail/watch/start`
5. Run only one watch‑enabled instance to avoid quota churn.

Troubleshooting
- 403 push: check `PUBSUB_VERIFICATION_TOKEN`, HTTPS, and service account perms.
- No replies processed: confirm watch is active and label settings match.

---

## 8) API surface (most used)

Agent & replies
- `POST /agent/trigger` — run outreach for a patient + campaign
- `POST /agent/reply` — process a reply payload (thread id + body)

Gmail
- `POST /gmail/watch/start` — start/refresh Gmail watch
- `POST /pubsub/push?token=...` — Pub/Sub push handler

Public booking
- `GET /api/v1/availability?month=MM&year=YYYY&date=YYYY-MM-DD` — availability
- `POST /api/v1/appointments/book` — create appointment
- `GET /api/v1/phone_booking_post?number=+1555...&name=John` — send booking link (demo)

Admin
- `GET /api/v1/admin/dashboard-stats` — KPIs + charts (month, lifetime, 90‑day)
- `GET /api/v1/admin/campaigns` — list
- `GET /api/v1/admin/campaigns/{id}` — details + conversation history
- `GET /api/v1/appointments` — list/search
- Auth: `POST /api/v1/auth/login`

---

## 9) Availability logic (how slots are computed)

- Base schedule: 09:00–20:30 in half‑hour slots.
- Timezone: determined by `TZ` (converted from UTC for stored timestamps).
- Overlaps: any appointment removes all overlapping slots for its duration (30/45 min).

---

## 10) Dashboard metrics (how we compute)

- KPIs: active recovery/recall, engaged leads, handoffs, recoveries (month), booked appointments (month)
- Rates: recovery vs recall — current month, lifetime, trailing 90‑day
- Charts: 12‑month performance series; campaign breakdown (active/recovered/failed/declined/handoffs); appointments trend

Implementation: `api/v1/endpoints/admin.py`

---

## 11) Operational tips

- Logs are JSON at INFO → stdout (configure collector to parse JSON).
- Indexes (create on MongoDB for performance):
  - `campaigns.status`, `campaigns.updated_at`, `campaigns.campaign_type`
  - `interactions.campaign_id`, `interactions.timestamp`
  - `appointments.appointment_date`, `appointments.patient_id`
- CORS: if `ALLOWED_ORIGINS=*`, credentials are disabled by spec; otherwise list exact domains.
- Single instance should own Gmail watch; others can run with it disabled (omit `GMAIL_TOPIC_NAME`).

---

## 12) Security considerations (MVP)

- Keep secrets out of code; use env and secure secret storage.
- Do not commit `confidential.json`, `token.json`, or any tokens.
- JWT key must be long and random; rotate periodically.
- Enforce HTTPS; set HSTS at the edge; run uvicorn with `--proxy-headers` behind proxies.

---

## 13) Manual test snippets

Health
```bash
curl -s http://localhost:8000/ | jq
```

Availability (single day)
```bash
curl -s "http://localhost:8000/api/v1/availability?month=08&year=2025&date=2025-08-12" | jq
```

Trigger agent
```bash
curl -s -X POST http://localhost:8000/agent/trigger \
  -H 'content-type: application/json' \
  -d '{"patient": {"name": "Alice", "email": "alice@example.com"}, "campaign": {"campaign_type": "RECOVERY", "status": "ATTEMPTING_RECOVERY", "follow_up_details": {"attempts_made": 0, "max_attempts": 3}}}'
```

Start Gmail watch
```bash
curl -s -X POST http://localhost:8000/gmail/watch/start | jq
```

---

## 14) Known limitations / next steps

- Some agent paths use synchronous MongoDB helpers; consider standardizing to async in hot paths.
- Phone/SMS call integration should be provided via a dedicated service that reads credentials from config with timeouts and retries.
- Seed scripts are for demos only; production data should be loaded via safe import jobs.

---

## 15) License

Internal; add a license notice if distributing outside the company.


