"""Omnivision server — FastAPI entrypoint.

Endpoints:
  GET  /health                       liveness + config check
  WS   /ws/voice?persona=ops|manager Channel A: in-app voice sessions
  WS   /ws/twilio                    Channel B: Twilio Media Streams
  POST /calls/initiate {po_id}       start a supplier chase call
  POST /calls/status                 Twilio status callback (no-answer/busy/failed)

Run:  cd server && uvicorn main:app --port 8000
"""

from __future__ import annotations

import json

from fastapi import FastAPI, Form, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

import calls as calls_module
from config import assert_core_settings, settings
from pipelines.inapp import run_inapp_session
from pipelines.localcall import run_local_call_session
from pipelines.telephony import run_telephony_session

app = FastAPI(title="Omnivision")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon setting — restrict for anything real
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    missing = assert_core_settings()
    if missing:
        logger.warning("missing env settings: {} — some features will fail", missing)
    logger.info("Omnivision server up. live={} extraction={}",
                settings.live_model, settings.extraction_model)


@app.get("/health")
async def health():
    return {"ok": True, "missing_settings": assert_core_settings()}


# ───────────────────────── Channel A: in-app voice ──────────────────────────

@app.websocket("/ws/voice")
async def voice_ws(websocket: WebSocket, persona: str = "ops"):
    if persona not in ("ops", "manager"):
        await websocket.close(code=4000)
        return
    await websocket.accept()
    try:
        await run_inapp_session(websocket, persona)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("in-app voice session crashed")
        try:
            await websocket.close()
        except Exception:
            pass


# ─────────────── Channel B (local mode): simulated supplier call ────────────
# The "supplier" (teammate) answers in a browser; their mic is the supplier
# side of the call. Same persona/transcript/extraction as real telephony.

@app.websocket("/ws/call")
async def local_call_ws(websocket: WebSocket, ctx_id: str = ""):
    ctx = calls_module.CALL_CONTEXTS.pop(ctx_id, None)
    if not ctx:
        await websocket.close(code=4004)
        return
    await websocket.accept()
    try:
        await run_local_call_session(websocket, ctx)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("local call session crashed")
        try:
            await websocket.close()
        except Exception:
            pass


# ─────────────── Channel B (twilio mode — deployment roadmap) ───────────────

@app.websocket("/ws/twilio")
async def twilio_ws(websocket: WebSocket):
    await websocket.accept()
    stream_sid = call_sid = None
    ctx_id = None
    try:
        # Twilio sends 'connected' then 'start' before media flows
        async for raw in websocket.iter_text():
            data = json.loads(raw)
            event = data.get("event")
            if event == "connected":
                continue
            if event == "start":
                start = data["start"]
                stream_sid = start["streamSid"]
                call_sid = start.get("callSid")
                ctx_id = (start.get("customParameters") or {}).get("ctx_id")
                break
            logger.warning("unexpected pre-start twilio event: {}", event)

        if not stream_sid or not ctx_id:
            logger.error("twilio ws missing stream_sid/ctx_id — closing")
            await websocket.close()
            return

        ctx = calls_module.CALL_CONTEXTS.pop(ctx_id, None)
        if not ctx:
            logger.error("unknown call ctx_id {} — closing", ctx_id)
            await websocket.close()
            return

        await run_telephony_session(websocket, stream_sid, call_sid, ctx)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("telephony session crashed")
        try:
            await websocket.close()
        except Exception:
            pass


class InitiateCallBody(BaseModel):
    po_id: str


@app.post("/calls/initiate")
async def initiate_call(body: InitiateCallBody):
    try:
        result = await calls_module.initiate_chase(body.po_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("failed to initiate chase")
        raise HTTPException(status_code=500, detail="failed to initiate call")


@app.post("/calls/status")
async def call_status(CallSid: str = Form(...), CallStatus: str = Form(...)):
    await calls_module.handle_status_callback(CallSid, CallStatus)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port)
