# 03 — Voice Pipeline (AssemblyAI + Pipecat + Twilio + TTS)

The audio plumbing for both channels. This is the highest-technical-risk layer — spike it first (TODO Phase 1) before building any persona logic.

## Pipeline shape (both channels)

```
Transport In ─▶ STT (AssemblyAI) ─▶ LLM (Claude) ─▶ TTS (Cartesia) ─▶ Transport Out
                      │                                                    ▲
                      └── end-of-turn events drive turn-taking ────────────┘
                          barge-in: user audio during TTS → cancel TTS + LLM
```

Pipecat provides the frame pipeline, transports, and service adapters for all three vendors. We write: transport selection, persona context injection, tool execution, and the post-call hook.

## AssemblyAI Universal-Streaming (the hero tech)

- **Service:** Pipecat's AssemblyAI STT service (`AssemblyAISTTService`), API key from env.
- **Audio in:** PCM16. Browser channel: 16 kHz mono. Telephony: Twilio's 8 kHz μ-law is transcoded by the Pipecat Twilio transport — verify in spike.
- **End-of-turn detection:** Universal-Streaming emits end-of-turn events — this is what makes the conversation feel natural and is worth calling out in the demo. Tune the silence threshold:
  - Floor/manager (channel A): slightly longer threshold (~700ms) — people pause mid-instruction while reading shelf labels.
  - Supplier calls (channel B): shorter (~500ms) — phone conversations are faster-paced; too slow feels like dead air to the supplier.
  - Too eager = agent interrupts the human. Too slow = awkward pauses. Budget an hour of tuning with real speech.
- **Interim transcripts:** stream partials to the dashboard for the live-caption effect (great demo visual; cheap to add since the events already flow through the pipeline).

## Channel A — in-app (browser ↔ server WebSocket)

- **Client:** `getUserMedia` → AudioWorklet downsamples to 16 kHz PCM16 → frames over WS (`/ws/voice?persona=ops|manager`). Push-to-talk (hold spacebar / hold button) rather than open mic — simpler, demo-safe, and natural for the floor use case.
- **Server:** FastAPI WS endpoint → Pipecat `WebsocketServerTransport` (or small custom transport) → pipeline.
- **Audio out:** TTS frames stream back over the same WS; client plays via AudioContext.
- **Persona param** selects system prompt + tool set at pipeline construction (see 04).

## Channel B — telephony (Twilio ↔ server)

### Outbound call initiation
```python
# calls.py — POST /calls/initiate {po_id}
call = twilio_client.calls.create(
    to=supplier.phone,
    from_=TWILIO_PHONE_NUMBER,
    twiml=f'<Response><Connect><Stream url="wss://{PUBLIC_HOST}/ws/twilio?call_ctx={ctx_id}"/></Connect></Response>',
    status_callback=f"https://{PUBLIC_HOST}/calls/status",  # no-answer / busy / completed
)
```
- `ctx_id` references a server-side context record (PO + supplier details) created before dialing — the WS handler loads it to preload the agent's system prompt. Don't put PO data in the URL itself.
- `status_callback` handles **no-answer / busy / failed**: mark the chase attempt failed in `po_events`, surface on dashboard ("No answer — retry?"). Voicemail detection is out of scope (roadmap); the scripted demo never hits it.

### Media Streams session
- Twilio connects to `wss://.../ws/twilio` and exchanges JSON frames (`start`, `media` with base64 μ-law payloads, `stop`).
- Pipecat's **Twilio/телephony transport** handles the frame protocol and μ-law↔PCM transcode in both directions. Spike checklist:
  1. Outbound call connects and we receive `media` frames.
  2. AssemblyAI produces a live transcript of the callee.
  3. TTS audio is heard by the callee (correct 8 kHz μ-law re-encode).
  4. Barge-in: callee speaking over TTS cancels playback.
- **ngrok** provides the public WSS host; pin the URL in env.

## TTS

- **Cartesia** primary (lowest first-byte latency in class, streaming); **ElevenLabs** as drop-in fallback (Pipecat adapter exists for both — switching is config).
- Pick one professional, neutral voice for the agent across all personas (consistent identity = better demo).
- Stream sentence-by-sentence: Pipecat sentence-aggregates LLM output so TTS starts on the first sentence, not the full reply.
- **Filler strategy for tool turns:** before executing a DB tool, emit a short utterance ("One sec, checking…") so the line is never silent > ~1.5s. Implement as: agent's tool-call turns are preceded by a canned filler frame pushed straight to TTS.

## Turn-taking & barge-in

- Pipecat interruption support: incoming user speech during agent playback cancels TTS + in-flight LLM generation. Enable on both channels; **demo it on the phone call** if a judge asks (it's a differentiator).
- Guard: don't allow barge-in to cancel a *tool execution mid-write* — tools must be atomic; cancellation only stops speech/generation, never a committed DB write.

## Error handling & resilience

| Failure | Handling |
|---|---|
| AssemblyAI WS drop | Pipecat auto-reconnect; if >3s, agent says "Sorry, I lost you for a second — could you repeat that?" |
| Claude timeout/5xx | One retry (SDK default); on failure speak a graceful "I'm having trouble right now" and (channel B) end call politely, log attempt as failed |
| TTS failure | Fallback provider (config flip); worst case channel A shows text answer on dashboard |
| Twilio call drop mid-conversation | `stop` frame ends pipeline; partial transcript still persisted; extraction runs with `confidence` reflecting incompleteness; PO event logged as "call incomplete" |
| Silence > 10s on phone | Agent prompts once ("Are you still there?"), then closes call gracefully |

## Latency instrumentation

Log per-turn timestamps from day one: `t_speech_end` (AAI end-of-turn) → `t_llm_first_token` → `t_tts_first_byte` → `t_audio_out`. One log line per turn. This is how we tune to the ≤1.5s budget in 02 instead of guessing.
