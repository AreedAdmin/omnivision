# Scripted-call demo — run guide (≈45 min)

The demo-safe version of the supplier-chase showpiece. Real Twilio call → your
phone, real AssemblyAI transcription, real Claude Opus 4.8 extraction, live
dashboard that flips the PO status. Swaps the full real-time Pipecat pipeline
(see `plan/`) for a scripted `<Say>` question + `<Record>` answer — the only
version that reliably stands up in an hour.

Files: `server/app_scripted.py` (FastAPI), `dashboard/scripted.html` (board),
reusing the existing `server/db.py` + `server/agent/extraction.py`.

---

## 0. What's already done

- Supabase **Personal** project, schema **`assemblyai`**, tables created.
- Seeded: supplier **Atlas Trading Co.**, hero PO **PO-8841** (overdue), plus PO-9012.
- ⚠️ The supplier phone is a placeholder `+10000000000` — **you must set it to your phone** (step 4).

## 1. Get the keys (~15 min)

| Key | Where |
|---|---|
| **Twilio** Account SID + Auth Token | twilio.com/console (sign up; free trial is fine) |
| **Twilio number** (voice) | Console → Phone Numbers → Buy a number (free on trial) |
| **AssemblyAI** API key | assemblyai.com dashboard |
| **Anthropic** API key | you have one |
| **Supabase** service_role key | Personal project → Settings → API → `service_role` (secret) |

**Trial Twilio caveats:** you can only call **verified** numbers — verify your own phone
in Console → Verified Caller IDs. Trial calls also play a ~10s "trial account" preamble.
To kill the preamble, add a card (pay-as-you-go, ~$1/mo + ~1¢/min) — optional for a self-demo.

## 2. ⚠️ Expose the `assemblyai` schema (10 sec, REQUIRED)

The backend reads via Supabase's REST API, which only serves *exposed* schemas.

Personal project → **Settings → API → Exposed schemas** → add **`assemblyai`** → Save.

(Without this, every DB call 404s with `PGRST106 schema must be one of …`.)

## 3. Configure env (~3 min)

```bash
cp server/.env.example .env        # NOTE: .env goes at the REPO ROOT
```
Fill in every blank in `.env` (`SUPABASE_SERVICE_ROLE_KEY`, the three API keys,
`TWILIO_*`, leave `PUBLIC_HOST` for step 6).

## 4. Point the supplier at your phone

Supabase → **SQL Editor**, run (E.164 — include country code):

```sql
update assemblyai.suppliers set phone = '+447XXXXXXXXX'
where name = 'Atlas Trading Co.';
```

## 5. Install + 6. ngrok + 7. run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r server/requirements-scripted.txt

# in a second terminal:
ngrok http 8000        # copy the https host, e.g. ab12cd34.ngrok-free.app
# put it in .env:  PUBLIC_HOST=ab12cd34.ngrok-free.app

cd server && uvicorn app_scripted:app --port 8000
```

## 8. Demo

1. Open **http://localhost:8000** → you see the PO board (PO-8841 = red "Overdue").
2. Click **Chase** on PO-8841 → chip turns amber "Chasing…", **your phone rings**.
3. Answer and read the supplier script:
   > "Atlas Trading. Yes — that order got held up, we had a raw-material shortage.
   >  It's shipping this Friday."
4. Hang up (or let it auto-hangup). Within a few seconds:
   - AssemblyAI transcribes your answer → appears under the card.
   - Claude extracts `{status: delayed, eta_date: …, delay_reason: …}`.
   - The card **flips to "Delayed"** with the new ETA. 🎉

## The pipeline (what to say in the pitch)

```
Chase → Twilio call → agent asks (Say) → records answer (Record)
   → AssemblyAI transcribes the recording
   → Claude Opus 4.8 structured extraction (confidence-gated)
   → Supabase PO row updates (or → needs_review if low confidence)
   → dashboard flips live
```

## Troubleshooting

- **Phone never rings** → trial: verify your number in Twilio Console; check `TWILIO_PHONE_NUMBER` is your *bought* number, and the supplier `phone` is *your* number.
- **Card flips to "Needs review"** → extraction confidence was low or AssemblyAI got no speech. Speak clearly, answer after the beep.
- **500 / `PGRST106`** → schema not exposed (step 2).
- **`dial failed`** alert on the dashboard → bad Twilio creds or `PUBLIC_HOST`.
- **Watch logs** → the `uvicorn` terminal logs the transcript and extraction for every call.

## Not in this version (post-hackathon, see `plan/`)

Real-time barge-in, both-speaker live captions, the floor/manager voice personas —
all need the streaming Pipecat pipeline in `plan/03-voice-pipeline.md`.
