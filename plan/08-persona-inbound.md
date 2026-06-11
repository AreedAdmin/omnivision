# 08 — Persona: Inbound Team (Supplier-Calling Agent)

> **⚠️ PLAN CHANGE — LOCAL MODE.** No Twilio number is available, so the call now
> runs **locally**: "Chase" rings a simulated call in the browser, the teammate
> playing the supplier clicks **Answer as supplier** and speaks into the mic —
> their voice is the supplier side. Everything else below is unchanged: same
> call persona, same single-intent dialogue, same transcript persistence, same
> Opus extraction → confidence-gated PO update. Half-duplex audio (mic muted
> while the agent speaks) prevents the agent hearing itself on speakers.
> The Twilio path is kept in code (`CALL_MODE=twilio`) as the deployment story;
> references to Twilio below describe that roadmap mode.

The showpiece: the agent autonomously calls a supplier, holds a real two-way conversation about an overdue PO, then logs everything and updates the order. Channel B (local simulated call; telephony in deployment).

## End-to-end flow

```
 Dashboard "Chase PO-8841"  (or voice: "chase PO 8841")
        │
        ▼
 POST /calls/initiate {po_id}
        │  1. load PO + supplier from Supabase
        │  2. create calls row (status: dialing) + call context record
        │  3. twilio.calls.create(to=supplier.phone, twiml=<Connect><Stream wss://...>)
        ▼
 Supplier answers → Twilio opens Media Streams WS to our server
        │
        ▼
 Pipecat telephony pipeline starts
        │   system prompt = INBOUND_PROMPT interpolated with PO context (04)
        │   AssemblyAI ◀── supplier audio (μ-law→PCM via transport)
        │   Sonnet 4.6 ──▶ dialogue turns ──▶ Cartesia ──▶ supplier hears agent
        │   every finalized turn → call_transcripts row (speaker, text, turn_no)
        ▼
 Agent reaches goal → confirms back → "thank you, goodbye" → hangup
        │
        ▼
 Post-call hook
        │   1. mark calls row completed (ended_at, outcome)
        │   2. Opus 4.8 structured extraction over full transcript (04)
        │   3. confidence high/med → update_po_status() → purchase_orders + po_events
        │      confidence low → status 'needs_review' flag + dashboard surfaces transcript
        ▼
 Supabase Realtime → dashboard PO card flips live: "Delayed — ETA Friday — raw-material shortage"
```

## Dialogue policy (what the agent says on the call)

Single-intent, five phases — encoded in the system prompt, not hardcoded states (Sonnet handles the flow naturally; the prompt pins the rails):

1. **Open:** "Hi, this is the automated assistant calling from {company} about purchase order {po_number} — do you have a quick moment?"
   - Transparency matters: it identifies as an automated assistant immediately (ethics + judges will ask).
2. **Ask:** "We were expecting {qty} units of {product} on {expected_date} — could you tell me the current status?"
3. **Clarify (as needed):** ETA if delayed; reason if offered or one gentle ask: "Is there a reason for the delay I can pass along?" — never pushy, never repeated.
4. **Confirm back:** "So that's shipping {eta}, delayed due to {reason} — is that right?"
5. **Close:** thanks + goodbye → end call.

Deflections (in prompt): asked anything off-PO → "I'm only able to check on this order's status today." Asked for a human → give callback number, thank, close. Confused/hostile party → apologize, close politely. **The agent never negotiates, never places orders, never discusses prices.**

## Call lifecycle edge cases

| Case | Handling |
|---|---|
| No answer / busy / failed | Twilio `status_callback` → `calls.outcome` set, `po_events: call_failed`, dashboard shows "No answer — Retry" |
| Voicemail | Out of scope (roadmap: AMD detection). Scripted demo never hits it; if it happens in testing, the silence-timeout closes the call |
| Supplier hangs up mid-call | `stop` frame → partial transcript persisted → extraction runs → almost certainly `low` confidence → needs_review |
| Long hold / silence | 10s silence → "Are you still there?" once → close gracefully |
| Two POs same supplier | Scope: one call = one PO. Batch-chasing is roadmap |

## Statuses & transitions

`open → overdue` (cron/derived: past expected_date) → `chasing` (call initiated) → one of:
- `confirmed_on_time` / `delayed` (+eta, +reason) / `shipped` — auto, confidence ≥ medium
- `needs_review` — low confidence or `needs_human` extraction
- back to `overdue` with failed-call event — no answer

Every transition appends `po_events` — the dashboard timeline renders this as the PO's audit trail, with the call transcript linked. **That audit trail is a selling point**: every supplier conversation is logged verbatim, searchable, attributable.

## Demo safety engineering (this beat must not crash)

1. **Scripted supplier.** A teammate plays Atlas Trading on a known phone, quiet room, script in hand:
   > Agent: greeting + PO-8841 status?
   > Teammate: "Let me check… yes, that order got held up — we had a raw-material shortage. It's shipping this Friday."
   > Agent: confirm-back. Teammate: "That's right." Agent: closes.
   - The script gives Opus a clean extraction: `{status: delayed, eta: <Friday>, reason: raw-material shortage, confidence: high}`.
2. **Phone path rehearsed end-to-end ≥5 times** including the venue's actual network (hotspot fallback ready; ngrok URL pinned and tested that morning).
3. **Fallback video** of a full successful run recorded the night before — if anything fails live, narrate over the video without apology.
4. **Latency theater:** while the call runs, the dashboard shows the **live transcript streaming** (AssemblyAI partials) — the audience watches the conversation as text in real time, which is both a wow visual and cover during any pause.
5. Speakerphone or audio-out from the teammate's phone so the room hears both sides.

## Why judges will believe the business case

- PO expediting is a named, universal procurement cost: hours/week of skilled staff time on "where's my order" calls.
- The output isn't just a note — it's a **structured status change + verbatim audit trail**, automatically.
- Extension story is obvious and honest: batch chasing every overdue PO nightly, voicemail handling, supplier scorecards from call history (all `po_events`/`calls` data we're already writing).
