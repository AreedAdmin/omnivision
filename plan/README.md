# Omnivision — Plan & Architecture Docs

**Omnivision** is a voice agent backbone for warehouse operations, built for the AssemblyAI hackathon. One shared agent brain — reasoning over live warehouse data — serves three teams through voice:

1. **Operations workers** run the WMS hands-free from the floor: *"I've counted a variance at aisle 4, bin 12, shelf 2 — system says 12, I count 8."*
2. **Managers** talk to their data: *"How much stock do I have of product X? What's its sale rate this month?"*
3. **Inbound team** delegates supplier chasing to the agent: it **places real outbound phone calls** to suppliers, asks where the order is, logs the conversation, and updates PO statuses automatically.

The differentiator vs. incumbent voice-directed warehousing (Vocollect, Zebra): those systems *direct predefined workflows*. Omnivision *answers questions, reasons, and takes actions* — and it talks back with answers worth hearing, not beeps.

## Reading order

| Doc | What it covers |
|---|---|
| [01-vision.md](01-vision.md) | Problem, personas, positioning, judging narrative |
| [02-architecture.md](02-architecture.md) | System design: one brain, two voice channels, full stack |
| [03-voice-pipeline.md](03-voice-pipeline.md) | AssemblyAI streaming, Pipecat, Twilio, TTS — the audio plumbing |
| [04-agent-core.md](04-agent-core.md) | Claude reasoning layer, tool registry, prompts, guardrails |
| [05-data-model.md](05-data-model.md) | Supabase schema + seed data |
| [06-persona-ops-worker.md](06-persona-ops-worker.md) | Floor worker workflows |
| [07-persona-manager.md](07-persona-manager.md) | Manager analytics Q&A |
| [08-persona-inbound.md](08-persona-inbound.md) | Supplier-calling agent (the showpiece) |
| [09-frontend.md](09-frontend.md) | Dashboard spec |
| [10-demo-plan.md](10-demo-plan.md) | Demo script, risk register, judge Q&A prep |
| [TODO.md](TODO.md) | Master build checklist, phased |

## Stack at a glance

| Layer | Choice |
|---|---|
| STT | **AssemblyAI Universal-Streaming** (real-time + end-of-turn detection) — the hero tech |
| Orchestration | **Pipecat** (voice pipeline framework) |
| Telephony | **Twilio** Programmable Voice + Media Streams (outbound supplier calls) |
| Reasoning | **Claude** — `claude-sonnet-4-6` live turns, `claude-opus-4-8` extraction/analytics |
| TTS | **Cartesia** (primary) or ElevenLabs (fallback) — streaming, low latency |
| Data | **Supabase** (Postgres) |
| Frontend | Web dashboard (Vite + React), three persona views |

## Build philosophy

- **One brain, persona-scoped tools.** The personas are the same system with different tool sets and role context — that's what makes "backbone" true in the code, not just the pitch.
- **Demo-critical first.** Every task in [TODO.md](TODO.md) is tagged `[DEMO]` or `[NICE]`. If it's not on the 3-minute demo path, it waits.
- **Never crash on stage.** Scripted supplier teammate, pre-recorded fallback video, rehearsed phone path. See [10-demo-plan.md](10-demo-plan.md).
