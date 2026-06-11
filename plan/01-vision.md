# 01 — Vision & Product

## Problem

Warehouse operations run on three chronic information gaps:

1. **Floor data is incomplete and late.** Workers with full hands and busy eyes skip data entry. Variances, expired stock, and damage go unlogged or get logged hours later at a terminal — so the WMS lies.
2. **Managers can't self-serve answers.** Stock levels, sale rates, and reorder questions go through a dashboard nobody on the floor opens, or through an analyst with a backlog.
3. **Chasing suppliers is manual labor.** "Where's PO 8841?" means a person phoning a supplier, sitting on hold, transcribing the answer into the system. It's hours per week of pure expediting overhead — a real, named procurement pain (PO expediting / order-status follow-up).

## The product

**Omnivision: a voice agent backbone for the warehouse.** One reasoning agent, connected to live warehouse data (inventory, locations, POs, sales) and able to **take actions**, accessed entirely by voice. The agent doesn't just transcribe and store — it answers, decides, and acts, then speaks back.

### Persona 1 — Operations worker (floor mode)

Hands-free WMS operation. Example utterances (from real workflows):

- *"I have calculated a variance in stock at aisle 4, bin 12, shelf 2 — counted 8, system says 12."* → agent logs the variance, flags the discrepancy, confirms back.
- *"Where is product X stored?"* → agent answers with aisle/bin/shelf locations and quantities.
- *"I've found 6 expired units of product Y — where do I take them?"* → agent looks up the disposition rule, tells the worker where to route them, logs the disposition, decrements stock.

Why voice: hands are full, eyes are on the task, terminals are far away. The agent **answers and acts** — which is what Vocollect-style pick-by-voice can't do (it directs predefined pick paths; it doesn't reason over open questions).

### Persona 2 — Manager (talk-to-data mode)

Conversational analytics over the same live data:

- *"How much stock do I have of product X?"*
- *"What's my sale rate of product X this month?"*
- *"Which products are below reorder point?"* → follow-ups keep context: *"and which of those have an open PO already?"*

Why voice: removes the BI-dashboard friction barrier; the answer is spoken and shown. The follow-up dialogue (context retention) is the wow.

### Persona 3 — Inbound team (supplier-calling agent) — the showpiece

The agent works **for** the inbound team and **places outbound phone calls to suppliers**:

- Inbound clicks "chase" on an overdue PO (or asks by voice: *"chase PO 8841"*).
- The agent dials the supplier, identifies itself, asks for the order status, handles the supplier's spoken answers, confirms, and hangs up.
- Post-call: the full conversation is transcribed and logged, structured fields are extracted (`status, eta, reason, confidence`), and the **PO status updates automatically** on the board.

Why this model (and not "give suppliers access"): we don't control suppliers — adoption friction kills any supplier-facing tool. The pain is *ours*: the phoning, holding, transcribing. So the agent does the calling. This is the purest "voice agent" of the three — the entire product *is* a two-way spoken conversation with a third party.

## Positioning — "why wouldn't they buy Vocollect?"

| | Voice-directed warehousing (Vocollect/Zebra) | Omnivision |
|---|---|---|
| Interaction model | Directs predefined workflows (pick paths, confirmations) | Answers open questions, reasons over data + rules, takes actions |
| Voice-out content | Beeps and scripted prompts | Reasoned answers, decisions, guidance |
| Off-floor reach | None | Manager analytics + autonomous supplier calls |
| Integration | Deep ERP, heavy hardware, enterprise sales | Software-only, any mic / any phone |

Omnivision is **the answer-and-action layer** that incumbents don't have, plus an autonomous telephony arm no WMS offers.

## Hackathon judging narrative

1. **AssemblyAI is the star, twice.** Universal-Streaming powers both channels: in-app real-time STT with end-of-turn detection (floor + manager) *and* phone-call transcription for the supplier agent. Post-call, transcripts feed structured extraction.
2. **The platform story is live, not slideware.** The demo shows the *same brain* serving a floor worker, then a manager, then autonomously calling a supplier — one codebase, persona-scoped tools.
3. **Clear who-pays-and-what-it-saves.** Floor: complete, real-time ops data. Manager: zero-friction answers. Inbound: hours of expediting labor per week eliminated, with an audit trail of every supplier conversation.

## Scope honesty (what we are NOT building this weekend)

- No real WMS/ERP integration — Supabase is the system of record, seeded with realistic data.
- No noise-hardened hardware story — demo is quiet-room; we *acknowledge* floor-noise as roadmap (AssemblyAI handles noisy audio well; dedicated mics are a deployment detail).
- No supplier-side variability — the demo supplier is a scripted teammate. Voicemail/IVR handling is documented as roadmap, with basic no-answer handling only.
- Auth/roles are a dropdown persona switcher, not real auth.
