# Omnivision — Warehouse Voice Agent (AssemblyAI Hackathon)

One voice agent brain serving three warehouse teams: **floor workers** run the WMS
by voice, **managers** talk to their data, and the **inbound team** lets the agent
*phone suppliers* to chase overdue POs — conversation logged, status updated
automatically.

Full architecture and build plan: [`plan/`](plan/README.md).

## Stack

AssemblyAI Universal-Streaming (STT) · Pipecat (voice pipeline) · Twilio Media
Streams (telephony) · Claude (`claude-sonnet-4-6` live / `claude-opus-4-8`
extraction) · Cartesia (TTS) · Supabase (Postgres) · FastAPI · Vite + React.

## Setup

### 0. Env
```bash
cp .env.example .env                       # fill in keys (see plan/TODO.md Phase 0)
cp dashboard/.env.example dashboard/.env   # fill in VITE_SUPABASE_PUBLISHABLE_KEY
```

### 1. Database (Supabase SQL editor)
1. Run `supabase/schema.sql`
2. **Manual:** Dashboard → Settings → API → *Exposed schemas* → add `assemblyai`
3. Run `supabase/seed.sql` (re-run any time to reset demo data)
4. In `seed.sql`, replace the `UPDATE-ME-SUPPLIER-PHONE` placeholder with your
   demo "supplier" teammate's real number (E.164), or run:
   `update assemblyai.suppliers set phone = '+9715XXXXXXX' where name = 'Atlas Trading Co';`

### 2. Install
```bash
make setup          # python venv + pip install, npm install
```

### 3. Run
```bash
make server         # FastAPI + Pipecat on :8000
make dashboard      # Vite on :5173
make tunnel         # ngrok for Twilio (Phase 5 only) → put host into .env PUBLIC_HOST
```

Open http://localhost:5173 — Floor / Manager tabs work without Twilio; the
Inbound tab's **Chase** button needs `TWILIO_*` + `PUBLIC_HOST` set and the
tunnel running.

## Smoke tests (Phase 1 spike — do these first)

1. `curl localhost:8000/health` → `{"ok": true, "missing_settings": []}`
2. Floor tab → hold the button → "where do we keep olive oil?" → spoken answer
   + transcript on screen.
3. With Twilio configured: Inbound tab → Chase `PO-8841` → your teammate's phone
   rings → conversation streams live → PO chip flips after hangup.

## Repo layout

```
plan/         architecture & build docs (start at plan/README.md)
supabase/     schema.sql + seed.sql (demo-choreographed data)
server/       FastAPI + Pipecat voice pipelines + agent core
dashboard/    React dashboard (Floor / Manager / Inbound views)
```

## Version note

`pipecat-ai` evolves quickly. If imports shift in a newer release, the touch
points are confined to: `server/pipelines/*.py`, `server/serializers.py`,
`server/processors.py` (service/transport/frame imports). Everything else is
plain FastAPI/Supabase/Anthropic and stable.
