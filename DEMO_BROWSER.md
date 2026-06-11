# Browser-mic demo — run guide (≈20 min, no phone number)

No Twilio, no phone number, no ngrok. Click **Chase** → the browser speaks the
agent's question and records your answer through the **laptop mic** → AssemblyAI
transcribes → Claude Opus 4.8 extracts → the PO card flips live.

Files: `server/app_browser.py`, `dashboard/browser.html`, reusing
`server/db.py` + `server/agent/extraction.py`.

---

## 0. Already done
- Supabase **Personal** project, schema **`assemblyai`**, tables + seed (PO-8841 overdue, PO-9012).

## 1. Keys you need (only three — no Twilio)
| Key | Where |
|---|---|
| **AssemblyAI** API key | assemblyai.com dashboard |
| **Anthropic** API key | you have it |
| **Supabase** service_role key | Personal project → Settings → API → `service_role` (secret) |

## 2. ⚠️ Expose the `assemblyai` schema (10 sec, REQUIRED)
Personal project → **Settings → API → Exposed schemas** → add **`assemblyai`** → Save.
(Without this every DB call 404s with `PGRST106`.)

## 3. Env + install
```bash
cp server/.env.example .env          # .env at the REPO ROOT
# fill: SUPABASE_SERVICE_ROLE_KEY, ASSEMBLYAI_API_KEY, ANTHROPIC_API_KEY
# (Twilio / PUBLIC_HOST vars can stay blank — not used here)

python3 -m venv .venv && source .venv/bin/activate
pip install -r server/requirements-scripted.txt
```

## 4. Run
```bash
cd server && uvicorn app_browser:app --port 8000
```
Open **http://localhost:8000** in Chrome (mic + Web Speech work best there).
Serve over `localhost` (mic access is allowed on localhost without HTTPS).

## 5. Demo
1. PO board loads — PO-8841 is red "Overdue".
2. Click **Chase** → a call panel opens and the agent's question is spoken aloud.
3. Click **🎙 Record answer**, say the supplier line, click **⏹ Stop & send**:
   > "Atlas Trading. Yes — that order got held up, we had a raw-material shortage.
   >  It's shipping this Friday."
4. AssemblyAI transcribes → Claude extracts `{status: delayed, eta_date, delay_reason}`
   → panel closes → the card **flips to "Delayed"** with the new ETA. 🎉

## Pitch line
```
Chase → agent asks (browser TTS) → you answer (mic)
  → AssemblyAI transcription → Claude Opus 4.8 structured extraction (confidence-gated)
  → Supabase PO update (or needs_review) → dashboard flips live
```
Frame it as: "the agent places the call and holds the conversation; AssemblyAI is
the perception layer, Claude is the reasoning layer." The audio + transcription +
extraction are all real — only the PSTN leg is swapped for the mic.

## Troubleshooting
- **No question spoken** → Web Speech needs a user gesture; the Chase click provides it. Use Chrome.
- **Mic denied** → allow mic for `localhost:8000`.
- **Card → "Needs review"** → low extraction confidence or no speech captured; speak clearly, re-Chase.
- **`PGRST106` / 500** → schema not exposed (step 2).
- **Watch the `uvicorn` terminal** → it logs the transcript and extraction per call.

## Want the real phone version later?
`DEMO_SCRIPTED.md` + `server/app_scripted.py` are ready — just add a free trial
number (Twilio US region / SignalWire / Telnyx) and an ngrok host.
