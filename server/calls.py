"""Supplier-call initiation.

LOCAL MODE (default — plan change, no Twilio number available):
  initiate_chase() creates the calls row + context and returns a ctx_id; the
  dashboard then opens WS /ws/call?ctx_id=... and the "supplier" (teammate)
  answers in the browser. Audio, persona, transcript, extraction are identical
  to real telephony.

TWILIO MODE (deployment roadmap, kept working): set CALL_MODE=twilio with
  TWILIO_* and PUBLIC_HOST configured to dial a real phone instead.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import date

from loguru import logger

import db
from config import settings

CALL_MODE = os.environ.get("CALL_MODE", "local").strip().lower()

# ctx_id → call context (single-process, hackathon-fine)
CALL_CONTEXTS: dict[str, dict] = {}


async def initiate_chase(po_id: str) -> dict:
    po = await asyncio.to_thread(db.get_po_full, po_id)
    if not po:
        raise ValueError(f"PO {po_id} not found")
    supplier = po.get("suppliers") or {}

    call_row = await asyncio.to_thread(db.create_call, po_id, supplier["id"])

    days_overdue = max(0, (date.today() - date.fromisoformat(po["expected_date"])).days)
    ctx_id = uuid.uuid4().hex
    CALL_CONTEXTS[ctx_id] = {
        "call_id": call_row["id"],
        "po_id": po_id,
        "po_number": po["po_number"],
        "qty": po["qty"],
        "product_name": (po.get("products") or {}).get("name", "the ordered product"),
        "expected_date": po["expected_date"],
        "days_overdue": days_overdue,
        "supplier_name": supplier.get("name", "the supplier"),
        "supplier_contact": supplier.get("contact_name"),
    }

    if CALL_MODE == "twilio":
        await _dial_twilio(ctx_id, call_row["id"], supplier)
    # local mode: nothing to dial — the dashboard connects the audio

    await asyncio.to_thread(db.set_po_status, po_id, "chasing")
    await asyncio.to_thread(db.add_po_event, po_id, "chase_started", {
        "call_id": call_row["id"], "supplier": supplier.get("name"),
        "mode": CALL_MODE,
    })
    logger.info("chase started ({}): PO {} → {} (call {})",
                CALL_MODE, po["po_number"], supplier.get("name"), call_row["id"])
    return {"call_id": call_row["id"], "ctx_id": ctx_id, "mode": CALL_MODE,
            "po_number": po["po_number"], "supplier": supplier.get("name")}


# ───────────────────────── Twilio path (roadmap) ─────────────────────────────

async def _dial_twilio(ctx_id: str, call_id: str, supplier: dict) -> None:
    from twilio.rest import Client as TwilioClient

    if not supplier.get("phone"):
        raise ValueError("supplier has no phone number")
    twiml = (
        f'<Response><Connect>'
        f'<Stream url="wss://{settings.public_host}/ws/twilio">'
        f'<Parameter name="ctx_id" value="{ctx_id}"/>'
        f'</Stream></Connect></Response>'
    )

    def _dial():
        client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        return client.calls.create(
            to=supplier["phone"],
            from_=settings.twilio_phone_number,
            twiml=twiml,
            status_callback=f"https://{settings.public_host}/calls/status",
            status_callback_event=["completed", "no-answer", "busy", "failed"],
        )

    call = await asyncio.to_thread(_dial)
    await asyncio.to_thread(db.update_call, call_id, twilio_sid=call.sid)


async def handle_status_callback(twilio_sid: str, call_status: str) -> None:
    """Twilio status webhook (twilio mode only): surface failed dial attempts."""
    failure_map = {"no-answer": "no_answer", "busy": "busy",
                   "failed": "failed", "canceled": "failed"}
    if call_status not in failure_map:
        return
    call = await asyncio.to_thread(db.find_call_by_twilio_sid, twilio_sid)
    if not call:
        logger.warning("status callback for unknown call sid {}", twilio_sid)
        return
    await asyncio.to_thread(db.update_call, call["id"],
                            outcome=failure_map[call_status])
    if call.get("po_id"):
        await asyncio.to_thread(db.set_po_status, call["po_id"], "overdue")
        await asyncio.to_thread(db.add_po_event, call["po_id"], "call_failed",
                                {"reason": call_status, "call_id": call["id"]})
