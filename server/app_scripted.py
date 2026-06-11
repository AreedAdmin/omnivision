"""Warehouse voice agent — scripted-turn supplier chase (1-hour demo build).

This is the demo-safe alternative to the full real-time Pipecat pipeline that
main.py targets (which needs Pipecat + Cartesia + pipelines/ modules not yet
built). It keeps the same schema, model, and PO-8841 / Atlas Trading narrative.

Flow:
  Dashboard "Chase" → POST /api/chase/{po_number}
    → create call row, set PO 'chasing', dial Twilio to the supplier (your phone)
  Twilio answers → GET/POST /voice/twiml
    → agent SPEAKS the scripted question (<Say>), RECORDS the answer (<Record>)
  Recording ready → POST /voice/recording
    → download recording, AssemblyAI transcribes it, Claude (Opus 4.8) extracts
      {status, eta_date, delay_reason, confidence}, PO row updates → board flips

Run:  cd server && uvicorn app_scripted:app --port 8000
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

import assemblyai as aai
import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from loguru import logger
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import VoiceResponse

import db
from agent.extraction import finalize_call
from config import settings

aai.settings.api_key = settings.assemblyai_api_key
_twilio = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)

app = FastAPI(title="Warehouse Voice Agent (scripted)")

_DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard" / "scripted.html"


def _base_url() -> str:
    """https URL Twilio can reach (your ngrok host). PUBLIC_HOST may be bare or full."""
    host = settings.public_host.replace("https://", "").replace("http://", "").rstrip("/")
    return f"https://{host}"


def _spoken_po(po_number: str) -> str:
    # "PO-8841" -> "P O 8 8 4 1" so the TTS reads it clearly
    return " ".join(list(po_number.replace("-", "")))


def _build_question(po: dict) -> str:
    product = (po.get("products") or {}).get("name", "this order")
    return (
        f"Hi, this is the automated procurement assistant from {settings.company_name}, "
        f"calling about purchase order {_spoken_po(po['po_number'])}. "
        f"It covers {po['qty']} units of {product}, and it is currently overdue. "
        f"Could you please tell me the current status and the new expected delivery date?"
    )


# ─────────────────────────────── dashboard API ──────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(_DASHBOARD.read_text())


@app.get("/api/pos")
async def api_pos() -> JSONResponse:
    state = await asyncio.to_thread(db.dashboard_state)
    return JSONResponse(state)


@app.post("/api/chase/{po_number}")
async def chase(po_number: str) -> JSONResponse:
    po = await asyncio.to_thread(db.get_po_by_number, po_number)
    if not po:
        return JSONResponse({"error": f"PO {po_number} not found"}, status_code=404)
    supplier = po.get("suppliers") or {}
    if not supplier.get("phone"):
        return JSONResponse({"error": "supplier has no phone number"}, status_code=400)

    call = await asyncio.to_thread(db.create_call, po["id"], supplier["id"])
    call_id = call["id"]

    # show the agent's opening line on the dashboard immediately
    await asyncio.to_thread(db.insert_transcript_turn, call_id, 1, "agent", _build_question(po))
    await asyncio.to_thread(db.set_po_status, po["id"], "chasing")
    await asyncio.to_thread(db.add_po_event, po["id"], "chase_started", {"call_id": call_id})

    base = _base_url()
    try:
        tw_call = await asyncio.to_thread(
            lambda: _twilio.calls.create(
                to=supplier["phone"],
                from_=settings.twilio_phone_number,
                url=f"{base}/voice/twiml?call_id={call_id}",
                method="POST",
                status_callback=f"{base}/voice/status?call_id={call_id}",
                status_callback_event=["no-answer", "busy", "failed", "completed"],
                status_callback_method="POST",
            )
        )
    except Exception as exc:  # bad creds / number — surface it on the dashboard
        logger.exception("twilio dial failed")
        await asyncio.to_thread(db.update_call, call_id, outcome="failed")
        await asyncio.to_thread(db.set_po_status, po["id"], "overdue")
        return JSONResponse({"error": f"dial failed: {exc}"}, status_code=502)

    await asyncio.to_thread(db.update_call, call_id, twilio_sid=tw_call.sid)
    logger.info("chase started for {} call={} sid={}", po_number, call_id, tw_call.sid)
    return JSONResponse({"call_id": call_id, "twilio_sid": tw_call.sid})


# ─────────────────────────────── Twilio voice ───────────────────────────────

@app.api_route("/voice/twiml", methods=["GET", "POST"])
async def voice_twiml(call_id: str) -> Response:
    """Twilio fetches this when the supplier answers."""
    call = await asyncio.to_thread(db.get_call, call_id)
    po = await asyncio.to_thread(db.get_po_full, call["po_id"]) if call else None

    vr = VoiceResponse()
    if not po:
        vr.say("Sorry, there was a problem locating the order. Goodbye.")
        vr.hangup()
        return Response(content=str(vr), media_type="application/xml")

    base = _base_url()
    vr.say(_build_question(po), voice="Polly.Joanna")
    vr.say("Please answer after the tone, then stay on the line.", voice="Polly.Joanna")
    vr.record(
        max_length=30,
        timeout=4,
        play_beep=True,
        trim="trim-silence",
        action=f"{base}/voice/after-record?call_id={call_id}",
        method="POST",
        recording_status_callback=f"{base}/voice/recording?call_id={call_id}",
        recording_status_callback_event="completed",
        recording_status_callback_method="POST",
    )
    # if the recording timed out with no speech, Twilio falls through to here
    vr.say("Thank you. We will update our system. Goodbye.", voice="Polly.Joanna")
    vr.hangup()
    return Response(content=str(vr), media_type="application/xml")


@app.api_route("/voice/after-record", methods=["GET", "POST"])
async def after_record(call_id: str) -> Response:
    """Spoken right after the supplier finishes recording (scripted confirm-back)."""
    vr = VoiceResponse()
    vr.say(
        "Thank you. I've logged your update and our purchasing system is being "
        "updated now. Goodbye.",
        voice="Polly.Joanna",
    )
    vr.hangup()
    return Response(content=str(vr), media_type="application/xml")


@app.post("/voice/recording")
async def recording_cb(request: Request, call_id: str) -> Response:
    """Twilio posts here once the recording is ready. AssemblyAI + Claude run here."""
    form = await request.form()
    status = form.get("RecordingStatus")
    recording_url = form.get("RecordingUrl")
    if status != "completed" or not recording_url:
        return Response(status_code=204)

    call = await asyncio.to_thread(db.get_call, call_id)
    if not call:
        logger.warning("recording callback for unknown call {}", call_id)
        return Response(status_code=204)

    try:
        audio_path = await asyncio.to_thread(_download_recording, recording_url)
        transcript_text = await asyncio.to_thread(_transcribe, audio_path)
        logger.info("call {} transcript: {!r}", call_id, transcript_text)

        await asyncio.to_thread(
            db.update_call, call_id,
            recording_url=recording_url, transcript=transcript_text,
        )
        await asyncio.to_thread(db.insert_transcript_turn, call_id, 2, "supplier", transcript_text)

        turns = await asyncio.to_thread(db.transcript_turns, call_id)
        # finalize_call (reused from agent/extraction.py): Claude extraction + PO write
        await finalize_call(call_id, call["po_id"], [
            {"speaker": t["speaker"], "text": t["text"]} for t in turns
        ])
    except Exception:
        logger.exception("recording processing failed for call {}", call_id)
        await asyncio.to_thread(db.update_call, call_id, outcome="failed")
        await asyncio.to_thread(db.set_po_status, call["po_id"], "needs_review")

    return Response(status_code=204)


@app.post("/voice/status")
async def status_cb(request: Request, call_id: str) -> Response:
    """Call-level callback: catch no-answer / busy / failed."""
    form = await request.form()
    call_status = form.get("CallStatus")
    if call_status in ("no-answer", "busy", "failed", "canceled"):
        call = await asyncio.to_thread(db.get_call, call_id)
        if call:
            await asyncio.to_thread(db.update_call, call_id, outcome=call_status)
            await asyncio.to_thread(db.add_po_event, call["po_id"], "call_failed",
                                    {"reason": call_status})
            if not call.get("extraction"):  # only reset if we never got an answer
                await asyncio.to_thread(db.set_po_status, call["po_id"], "overdue")
    return Response(status_code=204)


# ───────────────────────────── audio helpers ────────────────────────────────

def _download_recording(recording_url: str) -> str:
    resp = requests.get(
        recording_url + ".mp3",
        auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        timeout=60,
    )
    resp.raise_for_status()
    path = f"/tmp/rec_{datetime.now(timezone.utc).timestamp()}.mp3"
    with open(path, "wb") as f:
        f.write(resp.content)
    return path


def _transcribe(audio_path: str) -> str:
    transcript = aai.Transcriber().transcribe(audio_path)
    try:
        os.remove(audio_path)
    except OSError:
        pass
    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI error: {transcript.error}")
    return (transcript.text or "").strip() or "(no speech detected)"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app_scripted:app", host="0.0.0.0", port=settings.port, reload=False)
