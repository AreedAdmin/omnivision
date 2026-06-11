"""Warehouse voice agent — browser-mic version (no telephony, no phone number).

Same showpiece as the Twilio version, but the "supplier call" is captured through
the laptop mic instead of PSTN — so it needs no Twilio account, no phone number,
and no ngrok. Reuses the exact same schema, model, db.py and agent/extraction.py.

Flow:
  Dashboard "Chase" → POST /api/chase/{po_number}
    → create call row, set PO 'chasing', return the agent's scripted question
  Browser speaks the question (Web Speech API) and records your answer (MediaRecorder)
  → POST /api/answer/{call_id}  (the recorded audio blob)
    → AssemblyAI transcribes → Claude (Opus 4.8) extracts → PO row updates → board flips

Run:  cd server && uvicorn app_browser:app --port 8000
Open: http://localhost:8000
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

import assemblyai as aai
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from loguru import logger

import db
from agent.extraction import finalize_call
from config import settings

aai.settings.api_key = settings.assemblyai_api_key

app = FastAPI(title="Warehouse Voice Agent (browser-mic)")

_DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard" / "browser.html"


def _spoken_po(po_number: str) -> str:
    return " ".join(list(po_number.replace("-", "")))


def _build_question(po: dict) -> str:
    product = (po.get("products") or {}).get("name", "this order")
    return (
        f"Hi, this is the automated procurement assistant from {settings.company_name}, "
        f"calling about purchase order {_spoken_po(po['po_number'])}. "
        f"It covers {po['qty']} units of {product}, and it is currently overdue. "
        f"Could you please tell me the current status and the new expected delivery date?"
    )


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse(_DASHBOARD.read_text())


@app.get("/api/pos")
async def api_pos() -> JSONResponse:
    state = await asyncio.to_thread(db.dashboard_state)
    return JSONResponse(state)


@app.get("/api/po/{po_number}")
async def api_po_detail(po_number: str) -> JSONResponse:
    detail = await asyncio.to_thread(db.get_po_detail, po_number)
    if not detail:
        return JSONResponse({"error": f"PO {po_number} not found"}, status_code=404)
    return JSONResponse(detail)


@app.post("/api/chase/{po_number}")
async def chase(po_number: str) -> JSONResponse:
    po = await asyncio.to_thread(db.get_po_by_number, po_number)
    if not po:
        return JSONResponse({"error": f"PO {po_number} not found"}, status_code=404)

    call = await asyncio.to_thread(db.create_call, po["id"], (po.get("suppliers") or {}).get("id"))
    call_id = call["id"]
    question = _build_question(po)

    await asyncio.to_thread(db.insert_transcript_turn, call_id, 1, "agent", question)
    await asyncio.to_thread(db.set_po_status, po["id"], "chasing")
    await asyncio.to_thread(db.add_po_event, po["id"], "chase_started", {"call_id": call_id})

    logger.info("chase started for {} call={}", po_number, call_id)
    return JSONResponse({
        "call_id": call_id,
        "question": question,
        "supplier": (po.get("suppliers") or {}).get("name"),
        "po_number": po["po_number"],
    })


@app.post("/api/answer/{call_id}")
async def answer(call_id: str, audio: UploadFile = File(...)) -> JSONResponse:
    """Receive the recorded mic answer → AssemblyAI → Claude → PO update."""
    call = await asyncio.to_thread(db.get_call, call_id)
    if not call:
        return JSONResponse({"error": "call not found"}, status_code=404)

    audio_bytes = await audio.read()
    try:
        transcript_text = await asyncio.to_thread(_transcribe, audio_bytes)
        logger.info("call {} transcript: {!r}", call_id, transcript_text)

        await asyncio.to_thread(db.update_call, call_id, transcript=transcript_text)
        await asyncio.to_thread(db.insert_transcript_turn, call_id, 2, "supplier", transcript_text)

        turns = await asyncio.to_thread(db.transcript_turns, call_id)
        await finalize_call(call_id, call["po_id"], [
            {"speaker": t["speaker"], "text": t["text"]} for t in turns
        ])
    except Exception:
        logger.exception("answer processing failed for call {}", call_id)
        await asyncio.to_thread(db.update_call, call_id, outcome="failed")
        await asyncio.to_thread(db.set_po_status, call["po_id"], "needs_review")
        return JSONResponse({"error": "processing failed"}, status_code=500)

    return JSONResponse({"transcript": transcript_text})


def _transcribe(audio_bytes: bytes) -> str:
    path = f"/tmp/answer_{datetime.now(timezone.utc).timestamp()}.webm"
    with open(path, "wb") as f:
        f.write(audio_bytes)
    try:
        transcript = aai.Transcriber().transcribe(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"AssemblyAI error: {transcript.error}")
    return (transcript.text or "").strip() or "(no speech detected)"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app_browser:app", host="0.0.0.0", port=settings.port, reload=False)
