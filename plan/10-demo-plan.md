# 10 — Demo Plan

3-minute demo, one continuous narrative on seeded data. Order matters: each beat hands off to the next, ending on the showpiece.

## The script (beat by beat)

**[0:00–0:20] Setup line.**
> "Warehouses run on three broken information loops: floor data nobody logs, dashboards nobody opens, and supplier calls nobody wants to make. Omnivision is one voice agent that fixes all three — same brain, three jobs. Watch."

**[0:20–1:00] Beat 1 — Floor worker (persona: Floor).**
- Hold push-to-talk: *"Where do we keep basmati rice?"* → agent answers locations. (Warm-up; proves voice loop works.)
- *"I'm at aisle four, bin twelve, shelf two — I count eight."* → agent reads back "system says twelve… variance minus four — shall I log it?" → *"Yes."* → **action feed card appears live.**
- Narration: "Hands full, eyes on the shelf — the WMS just got updated by talking."

**[1:00–1:35] Beat 2 — Manager (switch persona tab — "same brain, new role").**
- *"Anything below reorder point?"* → "...sunflower oil already has an open PO — but it's six days overdue from Atlas Trading."
- *"What's the sale rate on basmati rice?"* → answer → *"So when do I run out?"* → agent computes days-of-cover from context. Narration: "That's reasoning over its own previous answers — not a lookup."

**[1:35–2:40] Beat 3 — The showpiece (Inbound tab). _(LOCAL MODE — plan change: no Twilio number)_**
- "PO-8841, six days overdue. Nobody enjoys this call. So our agent makes it."
- Click **Chase** → the call panel "rings" on screen → teammate ("Atlas Trading") clicks **Answer as supplier** and speaks into the mic — the room hears both sides through the speakers (agent voice = TTS out loud, supplier = teammate live).
- Narration while it rings: "In production this dials the supplier's real phone over Twilio — same agent, same conversation; today it's our supplier on the line locally."
- The room hears the two-way conversation **and reads the live transcript streaming on screen** (AssemblyAI real-time, both speakers).
- Agent confirms back, says goodbye, ends the call itself.
- Beat of silence → **the PO card flips live**: *"Delayed — ETA Friday — raw-material shortage"* + timeline entry + transcript link.
- Narration: "Conversation held, logged verbatim, order status updated, audit trail written. Zero human minutes."
- Staging: teammate at the demo laptop's mic (half-duplex prevents echo), or on a second laptop on the same network for more theater.

**[2:40–3:00] Close.**
> "One agent brain, two voice channels, three teams — built on AssemblyAI streaming end to end: it transcribed me on the floor, the manager's questions, and both sides of a live phone call. The backbone pattern means the next persona is a system prompt away."

## Supplier script (teammate card)

```
RING → answer: "Atlas Trading, good afternoon."
[agent greets + asks PO-8841 status]
"Let me check… yes — that order got held up, we had a raw-material
 shortage. It's shipping this Friday."
[agent confirms back]
"That's right."
[agent thanks + goodbye] → "No problem, bye."
```
Rules for the teammate: quiet room, speak at normal pace, don't improvise, don't talk over the agent (unless we deliberately demo barge-in in Q&A), keep phone on speaker only if the venue mic setup needs it.

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| ~~Venue network blocks ngrok / Twilio~~ | — | **Eliminated by local mode** — everything runs on localhost except the AssemblyAI/Anthropic/Cartesia/Supabase APIs |
| Live call beat fails (mic, API hiccup) | Low | **Fallback video** of full successful run, recorded night before; narrate over it without apology |
| Agent hears its own voice via speakers | Low | Half-duplex gate in the call hook (mic muted while agent audio plays); rehearse speaker volume |
| Judge asks "but is it a real phone call?" | Med | Honest answer: telephony mode is in the codebase (`CALL_MODE=twilio`, Twilio Media Streams) — local mode is a venue constraint (no number), not an architecture gap. Show `pipelines/telephony.py` if pressed |
| STT mishears scripted lines | Low | Scripted phrases rehearsed; seed data matches script numbers; re-ask path ("eight or eighty?") exists |
| Latency feels draggy on stage | Med | Filler utterances on tool turns; latency instrumentation tuned in rehearsal; keep system prompts lean |
| Demo data drifted from rehearsals | Med | `make reset-demo` restores exact seed state; run before every rehearsal and before stage |
| Teammate unavailable / mic dies | Low | Second teammate briefed; backup phone |
| Persona-switch beat confuses judges | Low | Explicit narration line "same brain, new role" |

**Rehearsal gate: the full 3-minute script must run clean ≥3 consecutive times before demo day. The phone beat ≥5 times total, including once on the venue network.**

## Judge Q&A prep

| Question | Answer |
|---|---|
| "Why wouldn't they just buy Vocollect/Zebra?" | Those direct predefined workflows — pick-by-voice. They can't answer open questions, reason over data, or call a supplier. We're the answer-and-action layer above directed work, software-only. |
| "What if the supplier talks over the agent?" | Barge-in is live — incoming speech cancels TTS mid-utterance. (Offer to show it.) |
| "Noisy warehouse floors?" | AssemblyAI is robust to noisy audio; deployment adds directional headset mics; push-to-talk is itself a noise gate. Quiet-room demo is a scope choice, not a limitation of the architecture. |
| "Hallucinated stock numbers?" | The model never invents figures — every spoken number comes from a tool result over Postgres; writes require verbal confirmation; supplier-call writes are confidence-gated with human review fallback, and every call has a verbatim transcript audit trail. |
| "What does the supplier consent/ethics story look like?" | Agent identifies itself as an automated assistant in its first sentence; full transcript retained; callback number offered on request. Call-recording consent rules vary by jurisdiction — production rollout gates recording/disclosure per region. |
| "How does this scale beyond the demo?" | Batch chasing (nightly job over all overdue POs), voicemail/AMD handling, supplier scorecards from call history, ERP connectors. The schema already captures everything needed (po_events, calls, transcripts). |
| "Why AssemblyAI specifically?" | One streaming STT serves both channels — browser mic and 8kHz telephony — with end-of-turn detection driving natural turn-taking, plus accurate transcripts feeding structured extraction. It's the perception layer of the whole product. |
| "Unit economics?" | Per chase call: a few cents of STT/TTS/LLM + Twilio minutes vs. 10–15 min of staff time per manual chase. Pays for itself on the first call. |

## Assets checklist (night before)

- [ ] Fallback video recorded (screen + room audio of full successful run)
- [ ] `make reset-demo` verified
- [ ] ngrok URL pinned + smoke-tested; hotspot fallback tested
- [ ] Teammate script card printed; backup teammate briefed
- [ ] Laptop audio out + venue speaker check for the phone call
- [ ] Roadmap slide (batch chasing, voicemail, ERP connectors, supplier scorecards)
