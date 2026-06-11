# TODO — Omnivision Master Checklist

Tags: `[DEMO]` = on the 3-minute demo path, build first. `[NICE]` = cut without mercy if behind.
Rule: **Phase 1 (voice spike) before any persona logic** — it's the highest-risk layer.

> **Status note:** the full codebase has been scaffolded (server, dashboard, SQL).
> Items marked `[x]` are written; unchecked items are the *runtime verification*
> steps that need real keys/devices — they are the actual remaining work.

## Phase 0 — Setup (~2h)

- [ ] `[DEMO]` Create accounts/keys: AssemblyAI, Anthropic, Twilio (+ buy a phone number), Cartesia, Supabase keys → fill `.env` + `dashboard/.env`
- [x] `[DEMO]` Repo scaffold per layout in [02-architecture.md](02-architecture.md): `server/` (FastAPI + Pipecat), `dashboard/` (Vite+React+TS), `supabase/`
- [x] `[DEMO]` `.env` + config loading; `.env.example` committed, real keys gitignored
- [ ] `[DEMO]` Run `supabase/schema.sql` in the SQL editor + **expose the `assemblyai` schema** (Settings → API → Exposed schemas)
- [ ] `[DEMO]` Run `supabase/seed.sql`; set Atlas Trading's phone to the teammate's number (`UPDATE-ME-SUPPLIER-PHONE`)
- [x] `[DEMO]` Realtime publication for `purchase_orders`, `calls`, `call_transcripts`, `variance_logs` (in schema.sql)
- [ ] `[DEMO]` ngrok up; public WSS reachable; `PUBLIC_HOST` set
- [x] `[NICE]` Demo reset = re-run `seed.sql` (idempotent truncate + insert)

## Phase 1 — Voice pipeline spike (~4h) — de-risk before anything else

All pipeline code is written ([pipelines/inapp.py], [pipelines/telephony.py]); this
phase is now **runtime verification with real keys** — pipecat import paths are the
likeliest breakage if the installed version differs (see README version note).

- [ ] `[DEMO]` `make setup` succeeds; `/health` returns no missing settings
- [ ] `[DEMO]` **Channel A:** Floor tab → hold-to-talk → live transcript appears → spoken answer heard
- [ ] `[DEMO]` **Channel B:** outbound Twilio call to own phone → media frames arrive, μ-law transcode OK, AssemblyAI transcribes callee, TTS audible to callee
- [ ] `[DEMO]` Barge-in verified on both channels
- [ ] `[DEMO]` End-of-turn thresholds tuned with real speech (code defaults: 560ms ch-A, 400ms ch-B)
- [ ] `[NICE]` Per-turn latency log line (`t_speech_end → t_llm_first_token → t_tts_first_byte`)

## Phase 2 — Agent core (~4h)

- [x] `[DEMO]` Persona registry: `{system_prompt, tools[]}` per persona; pipeline selects by WS param (`agent/personas.py`)
- [x] `[DEMO]` Tool calling via Pipecat function registration (`llm.register_function`)
- [x] `[DEMO]` Supabase client + query helpers (`db.py`, schema-aware)
- [x] `[DEMO]` Voice-output discipline in shared preamble (short sentences, natural numbers, no markdown)
- [ ] `[NICE]` Filler utterance before tool execution ("one sec, checking…") — add if tool turns feel silent
- [x] `[DEMO]` Confirm-before-write pattern: `get_location_count` pre-check → read-back → yes → `log_variance`
- [x] `[NICE]` Provenance fields on all writes (`source`, `session_ref`)

## Phase 3 — Ops worker persona (~3h)

- [x] `[DEMO]` `locate_product` (fuzzy name/SKU match) — `agent/tools/ops.py`
- [x] `[DEMO]` `log_variance` + `get_location_count` pre-check (flag threshold 3) — **demo beat 1**
- [ ] `[DEMO]` Walkthrough W1 + W2 from [06-persona-ops-worker.md](06-persona-ops-worker.md) verified end-to-end by voice
- [x] `[NICE]` `get_disposition_rule` + `log_disposition` (W3 — backup beat)
- [x] `[NICE]` `adjust_stock` (W4)
- [ ] `[NICE]` Magnitude sanity check on counted qty ("eight or eighty?")

## Phase 4 — Manager persona (~2h)

- [x] `[DEMO]` `get_stock_level`, `get_sale_rate`, `low_stock_report` tools — `agent/tools/manager.py`
- [ ] `[DEMO]` Session history threading verified → D2 follow-up chain works ("what's the sale rate on **it**" → "when do I run out?")
- [ ] `[DEMO]` D3 verified: low-stock report mentions overdue PO from Atlas Trading (seed guarantees the data)
- [x] `[DEMO]` Numbers-only-from-tools rule in prompt; off-tool questions get capability answer
- [x] `[NICE]` `open_pos_report`, `top_movers`
- [x] `[NICE]` Spoken-number formatting rules in prompt

## Phase 5 — Supplier-calling agent (~5h) — the showpiece

- [x] `[DEMO]` `POST /calls/initiate {po_id}`: load PO+supplier, `calls` row + context record, Twilio dial with Media Streams TwiML — `calls.py`
- [x] `[DEMO]` Telephony pipeline with INBOUND_PROMPT interpolated from PO context (toolless except `end_call`) — `pipelines/telephony.py`
- [x] `[DEMO]` Transcript persistence per finalized turn → `call_transcripts`
- [x] `[DEMO]` Agent ends call after goodbye (`end_call` tool → EndFrame → Twilio hangup)
- [x] `[DEMO]` Post-call hook: Opus 4.8 structured extraction (`PoCallExtraction`) — `agent/extraction.py`
- [x] `[DEMO]` Confidence-gated write → `purchase_orders` + `po_events`; low confidence → `needs_review`
- [x] `[DEMO]` `status_callback` handling: no-answer/busy/failed → `po_events: call_failed`, status back to overdue
- [ ] `[DEMO]` **Full dry-run: chase → teammate answers scripted → status flips in DB** (needs Twilio + ngrok live)
- [ ] `[NICE]` 10s-silence prompt + graceful close
- [ ] `[NICE]` Voice-triggered chase ("chase PO 8841") from manager/inbound persona

## Phase 6 — Dashboard (~4h)

- [x] `[DEMO]` Vite+React+TS + Supabase client; persona tab shell (plain CSS, not Tailwind — fewer deps)
- [x] `[DEMO]` Inbound PO board: table, overdue badges, status chips — `views/InboundView.tsx`
- [x] `[DEMO]` Chase button → `/calls/initiate`; chasing animation
- [x] `[DEMO]` Live call transcript panel (Realtime on `call_transcripts` inserts)
- [x] `[DEMO]` Status chip flips live via Realtime on `purchase_orders`
- [x] `[DEMO]` Push-to-talk (`useVoiceSession`): getUserMedia → AudioWorklet → 16kHz PCM16 → WS; playback via AudioContext
- [x] `[DEMO]` Live transcript pane for channel A (interim results streaming)
- [x] `[DEMO]` Floor action feed (Realtime on `variance_logs` + `dispositions`)
- [ ] `[NICE]` PO timeline expansion (`po_events`), transcript link, extraction result card
- [ ] `[NICE]` Manager answer panel (tables), KPI strip
- [x] `[NICE]` Dark control-room theme, large type, mic state animations

## Phase 7 — Demo prep (~3h + rehearsals)

- [ ] `[DEMO]` Script all three beats against seed data; verify every spoken number matches ([10-demo-plan.md](10-demo-plan.md))
- [ ] `[DEMO]` Teammate supplier script card; brief teammate; backup teammate briefed
- [ ] `[DEMO]` **Rehearsal gate:** full 3-min script clean ×3 consecutive; phone beat ×5 incl. venue/hotspot network
- [ ] `[DEMO]` Record fallback video (full successful run, screen + room audio)
- [ ] `[DEMO]` Morning-of checklist: ngrok pinned, `make reset-demo`, audio out test, phone charged
- [ ] `[NICE]` Roadmap slide (batch chasing, voicemail/AMD, ERP connectors, supplier scorecards)
- [ ] `[NICE]` Q&A drill from the prep table in [10-demo-plan.md](10-demo-plan.md)

## Dependency graph (critical path)

```
P0 ─▶ P1 (spike, both channels) ─▶ P2 (agent core) ─┬▶ P3 ops ──┐
                                                    ├▶ P4 mgr ──┼─▶ P7 demo prep
                                                    └▶ P5 call ─┤
P0 ─────────────────────────────▶ P6 dashboard ─────────────────┘
   (P6 board+chase needs P5 endpoints; P6 push-to-talk needs P1 channel A)
```

If time collapses, the cut order is: P3-W3/W4 → P4 extras → P6 polish → **never** P5 or the rehearsal gate.
