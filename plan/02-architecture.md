# 02 — System Architecture

> **⚠️ PLAN CHANGE — Channel B runs locally.** No Twilio number available:
> the supplier call is a **browser-to-browser simulated call** (`/ws/call`,
> `pipelines/localcall.py`) — the teammate playing the supplier answers in the
> dashboard and speaks into the mic. The pipeline shape, call persona,
> transcripts, and post-call extraction are identical to the telephony design
> below; Twilio (`CALL_MODE=twilio`, `pipelines/telephony.py`) remains in the
> codebase as the production deployment path. Twilio/ngrok references below
> describe that roadmap mode.

## The shape: one brain, two voice channels

```
                         ┌──────────────────────────────────────────────┐
                         │                AGENT CORE                    │
                         │  (FastAPI service, Python)                   │
                         │                                              │
   CHANNEL A: in-app     │  ┌──────────────┐    ┌────────────────────┐  │
┌──────────────┐  WS     │  │ Persona       │    │ Tool Registry      │  │
│ Browser mic  │────────▶│  │ context       │───▶│  ops_* tools       │  │
│ (ops worker, │◀────────│  │ + system      │    │  mgr_* tools       │  │
│  manager)    │  audio  │  │ prompts       │    │  po_* tools        │  │
└──────────────┘         │  └──────────────┘    └─────────┬──────────┘  │
                         │        │                        │            │
   CHANNEL B: telephony  │        ▼                        ▼            │
┌──────────────┐         │  ┌──────────────┐    ┌────────────────────┐  │
│ Supplier's   │  Twilio │  │ Claude        │    │ Supabase           │  │
│ phone        │◀───────▶│  │ sonnet-4-6   │    │ (inventory, POs,   │  │
└──────────────┘  Media  │  │ (live turns) │    │  sales, calls...)  │  │
                  Streams│  │ opus-4-8     │    └────────────────────┘  │
                         │  │ (extraction) │                            │
                         │  └──────────────┘                            │
                         └──────────────────────────────────────────────┘
                                      ▲
                                      │ reads/writes
                         ┌────────────┴────────────┐
                         │  Dashboard (React)      │
                         │  floor / manager /      │
                         │  inbound PO board       │
                         └─────────────────────────┘
```

Both channels run the **same Pipecat pipeline shape**:

```
audio in ──▶ AssemblyAI Universal-Streaming (STT + end-of-turn)
         ──▶ Claude (persona context + tools)
         ──▶ Cartesia TTS (streaming)
         ──▶ audio out
```

Only the **transport** differs (browser WebSocket vs Twilio Media Streams) and the **persona context** injected (which tools + which system prompt). That's the "backbone" claim made real in code.

## Components

| Component | Tech | Responsibility |
|---|---|---|
| Voice orchestration | **Pipecat** (Python) | Pipeline wiring, turn-taking, barge-in, transport adapters for both channels |
| STT | **AssemblyAI Universal-Streaming** | Real-time transcription; end-of-turn detection drives turn-taking; also transcribes the supplier side of phone calls |
| Telephony | **Twilio** Programmable Voice + Media Streams | Outbound dialing; bidirectional audio over WebSocket to our server |
| Live reasoning | **Claude Sonnet 4.6** (`claude-sonnet-4-6`) | Per-turn dialogue + tool calls. Chosen over Opus for latency: voice turns must complete in ~1s |
| Offline reasoning | **Claude Opus 4.8** (`claude-opus-4-8`) | Post-call structured extraction (`output_config.format` JSON schema), complex analytics. Not latency-bound → use the most capable model |
| TTS | **Cartesia** (primary; ElevenLabs fallback) | Streaming low-latency synthesis |
| Data | **Supabase** (Postgres) | System of record: inventory, locations, POs, suppliers, calls, transcripts, sales. Realtime subscriptions push PO-status changes to the dashboard |
| API/agent server | **FastAPI** (Python) | Hosts Pipecat pipelines, agent loop, Twilio webhooks, REST for dashboard |
| Frontend | **Vite + React + TS** | Persona-switched dashboard; push-to-talk; PO board with live call status |

## Model selection rationale

Default for any Claude work is `claude-opus-4-8` — we deviate **only** where latency forces it:

- **Live voice turns → `claude-sonnet-4-6`.** A spoken turn budget is ~1.0–1.5s total (STT finalize + LLM first token + TTS first byte). Sonnet 4.6 is the best speed/intelligence balance; Opus first-token latency would make the phone conversation feel broken. If Sonnet is still too slow on long tool turns, fall back to `claude-haiku-4-5` for the supplier channel only (its dialogue is narrow and scripted).
- **Post-call extraction, analytics aggregation → `claude-opus-4-8`** with structured outputs (`output_config: {format: {type: "json_schema", ...}}`). Latency is irrelevant; correctness of the DB write is everything.
- Use **streaming** for all live-turn requests; use `client.messages.parse()` / structured outputs for extraction.

## Latency budget (per spoken turn, target ≤ 1.5s perceived)

| Stage | Budget | Notes |
|---|---|---|
| End-of-turn detection | 300–500 ms | AssemblyAI end-of-turn; tunable — see 03 |
| Claude first token (Sonnet, streaming) | 400–700 ms | Keep system prompt lean; tools few per persona |
| TTS first audio byte (streaming) | 150–300 ms | Cartesia streams; start speaking on first sentence |
| Transport overhead | ~100 ms | WS both directions |

Tool-calling turns (DB lookups) add one round trip — mask with a spoken filler ("Let me check that…") emitted before the tool call resolves.

## Key data flows

### A. Floor worker logs a variance
1. Push-to-talk in dashboard → browser streams mic audio over WS to Pipecat.
2. AssemblyAI streams transcript; end-of-turn fires.
3. Sonnet (ops persona) calls `log_variance(product, location, counted_qty)` → tool reads system qty, writes `variance_logs`, returns delta.
4. Agent speaks confirmation: *"Logged — counted 8 against system 12 at aisle 4 bin 12 shelf 2, variance −4. Flagged for review."*

### B. Manager asks an analytics question
Same pipeline, manager persona → `get_stock_level`, `get_sale_rate`, `low_stock_report` tools → spoken + on-screen answer. Conversation state retained for follow-ups.

### C. Agent chases a supplier (the showpiece)
1. Dashboard "Chase" on PO 8841 → POST `/calls/initiate` → Twilio REST API dials supplier number with a Media Streams `<Connect><Stream>` TwiML.
2. Twilio opens WS to our server; Pipecat telephony pipeline starts with **PO context preloaded** into the system prompt.
3. Two-way conversation: AssemblyAI transcribes supplier; Sonnet drives a single-intent dialogue (get status/ETA/reason); Cartesia speaks down the line.
4. Agent closes the call; full transcript persisted to `call_transcripts`.
5. **Opus 4.8 extraction**: transcript → `{status, eta, reason, confidence}` via JSON-schema structured output.
6. `purchase_orders.status` updated + `po_events` appended; Supabase Realtime pushes the change → dashboard PO card flips live.

## Audio format gotchas (resolve in Phase 1 spike)

- **Twilio Media Streams = 8 kHz μ-law.** AssemblyAI streaming wants PCM16. Pipecat's Twilio transport handles the transcode — **verify early**, day one of the telephony spike.
- Browser channel: capture at 16 kHz PCM16 mono; downsample in an AudioWorklet before sending.
- TTS output back to Twilio must be re-encoded to 8 kHz μ-law (again, Pipecat transport handles; verify).

## Configuration & secrets

All via env vars (never committed): `ASSEMBLYAI_API_KEY`, `ANTHROPIC_API_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `CARTESIA_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (server) / `SUPABASE_ANON_KEY` (dashboard). Server needs a public WSS endpoint for Twilio → use **ngrok** during the hackathon.

## Repo layout (target)

```
omnivision/
├── plan/                  # these docs
├── server/
│   ├── main.py            # FastAPI app: WS endpoints, Twilio webhooks, REST
│   ├── pipelines/
│   │   ├── inapp.py       # Channel A pipeline (browser WS)
│   │   └── telephony.py   # Channel B pipeline (Twilio)
│   ├── agent/
│   │   ├── personas.py    # system prompts + tool scoping per persona
│   │   ├── tools/         # ops.py, manager.py, inbound.py (tool impls)
│   │   └── extraction.py  # Opus post-call structured extraction
│   ├── db.py              # Supabase client + queries
│   └── calls.py           # Twilio outbound call initiation
├── dashboard/             # Vite + React
└── supabase/
    ├── schema.sql
    └── seed.sql
```
