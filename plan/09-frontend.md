# 09 — Frontend (Dashboard)

One lightweight web app, three persona views behind a switcher. The dashboard's job in the demo: make the invisible visible — live transcripts, DB writes appearing in real time, PO cards flipping status. Keep it minimal and polished; it's a stage prop and a control surface, not a product UI.

## Tech

- **Vite + React + TypeScript** (fast to scaffold, no SSR needed).
- **Supabase JS client** with Realtime subscriptions (`purchase_orders`, `calls`, `variance_logs`).
- Audio: `getUserMedia` + AudioWorklet (16 kHz PCM16 downsampling) over a WS to the server; playback via AudioContext. Wrap in one `useVoiceSession(persona)` hook.
- Styling: Tailwind. Dark, control-room aesthetic; large type (must read from the back of a demo room).

## Layout

```
┌──────────────────────────────────────────────────────────┐
│  OMNIVISION          [ Floor ] [ Manager ] [ Inbound ]   │  ← persona tabs
├──────────────────────────────────────────────────────────┤
│                                                          │
│   (persona view)                                         │
│                                                          │
├──────────────────────────────────────────────────────────┤
│  ● mic status     live transcript ticker                 │  ← voice bar (Floor/Manager)
└──────────────────────────────────────────────────────────┘
```

## View 1 — Floor (ops worker)

- **Big push-to-talk button** (hold to speak; spacebar works too). States: idle / listening (pulse) / thinking / speaking.
- **Live transcript pane**: user partials (AssemblyAI interim results) render as they stream — strong demo visual; agent replies appear as text alongside the audio.
- **Action feed**: each committed write (variance, disposition, adjustment) appears instantly as a card — *"Variance logged: basmati rice @ A4-B12-S2, −4, flagged"* — via Realtime. This is the proof that voice → database actually happened.

## View 2 — Manager

- Same voice bar + transcript pane.
- **Answer panel**: when a tool returns tabular data (low-stock report, top movers), render the table while the agent speaks the top lines — voice + screen complement (07's "two others — on your screen").
- Small KPI strip (total SKUs, open POs, flagged variances) — static queries, cosmetic, `[NICE]`.

## View 3 — Inbound (PO board) — the demo centerpiece

- **PO table**: po_number, supplier, product, qty, expected date, days overdue (red badge), status chip, **Chase button** on overdue rows.
- Clicking **Chase** →
  1. Row enters `chasing` state: animated "📞 Calling Atlas Trading…" chip.
  2. **Live call panel** slides in: two-column transcript (Agent / Supplier) streaming in real time as the call happens — the audience reads the conversation live.
  3. Call ends → extraction result card: status, ETA, reason, confidence — then the row's status chip **flips live** (Realtime) to "Delayed — ETA Fri 19 Jun".
  4. Row expands to show the **PO timeline** (`po_events`): created → chase_started → call_completed → status_changed, with transcript link.
- `needs_review` state renders an amber chip + "Review transcript" affordance.

## Server interface (what the dashboard needs from FastAPI)

| Endpoint | Use |
|---|---|
| `WS /ws/voice?persona=ops\|manager` | Channel A bidirectional audio + transcript/agent-reply JSON frames |
| `POST /calls/initiate {po_id}` | Chase button |
| `GET /pos`, `GET /pos/:id/events`, `GET /calls/:id/transcript` | Board + timeline + transcript views (or read directly from Supabase with anon key — prefer direct Supabase reads to keep the server surface small) |
| Supabase Realtime | status flips, action feed, live call transcript rows (`call_transcripts` inserts) |

Note: live call transcript can ride entirely on Realtime (`call_transcripts` insert subscription) — no extra WS needed for the inbound view. Channel A's WS is only for views 1–2 audio.

## Build order

1. PO board reading seeded data (static) — 1h.
2. Chase button → call initiation → status chip flip via Realtime — with the telephony pipeline, this completes the hero demo.
3. Push-to-talk + transcript pane (channel A) — floor/manager beats.
4. Action feed, timeline expansion, KPI strip — polish, `[NICE]`.
