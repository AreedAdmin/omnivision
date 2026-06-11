"""Post-call structured extraction (plan/04, plan/08).

After a supplier call ends, Claude Opus 4.8 turns the transcript into a
validated PoCallExtraction, which gates the PO status write:
  - confidence high/medium → status updated automatically
  - confidence low / needs_human → PO flagged 'needs_review' for a person
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Literal, Optional

import anthropic
from loguru import logger
from pydantic import BaseModel

import db
from config import settings

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


class PoCallExtraction(BaseModel):
    reached_supplier: bool
    status: Literal["confirmed_on_time", "delayed", "shipped", "unknown", "needs_human"]
    eta_date: Optional[str]          # ISO date (YYYY-MM-DD) if stated, else null
    delay_reason: Optional[str]
    supplier_quotes: list[str]       # 1-3 short verbatim quotes supporting the status
    confidence: Literal["high", "medium", "low"]
    summary: str                     # one sentence for the PO event log


_EXTRACTION_PROMPT = """You are reviewing the transcript of an automated phone call \
our warehouse assistant made to a supplier to chase an overdue purchase order.

Purchase order context:
- PO number: {po_number}
- Product: {product_name} x {qty}
- Originally expected: {expected_date}
- Today's date: {today}

Extract the call outcome. Rules:
- status "confirmed_on_time": supplier says it will arrive by the expected date.
- status "shipped": supplier says it has already shipped / is in transit with no new ETA needed.
- status "delayed": supplier confirms a delay (capture eta_date as an ISO date if any \
date or weekday was stated — resolve weekdays like "Friday" relative to today's date).
- status "unknown": call happened but no clear answer was obtained.
- status "needs_human": supplier asked for a human, was confused, or the call went off-track.
- reached_supplier is false if nobody meaningfully engaged about the PO.
- confidence "high" only when the supplier explicitly confirmed the details back.
- supplier_quotes: copy 1-3 short verbatim supplier lines that support your extraction.
- summary: one plain sentence, e.g. "Supplier confirmed delay due to raw-material \
shortage, new ETA Friday 19 June."

Transcript:
{transcript}"""


def _run_extraction_sync(po: dict, transcript_text: str) -> PoCallExtraction:
    response = _client.messages.parse(
        model=settings.extraction_model,
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": _EXTRACTION_PROMPT.format(
                po_number=po["po_number"],
                product_name=(po.get("products") or {}).get("name", "unknown"),
                qty=po["qty"],
                expected_date=po["expected_date"],
                today=datetime.now(timezone.utc).date().isoformat(),
                transcript=transcript_text,
            ),
        }],
        output_format=PoCallExtraction,
    )
    return response.parsed_output


async def finalize_call(call_id: str, po_id: str, transcript_turns: list[dict]) -> None:
    """Run after the telephony pipeline ends. Never raises — logs instead."""
    try:
        if not transcript_turns:
            await asyncio.to_thread(db.update_call, call_id, outcome="incomplete",
                                    ended_at=datetime.now(timezone.utc).isoformat())
            await asyncio.to_thread(db.add_po_event, po_id, "call_failed",
                                    {"reason": "no transcript captured"})
            await asyncio.to_thread(db.set_po_status, po_id, "overdue")
            return

        po = await asyncio.to_thread(db.get_po_full, po_id)
        transcript_text = "\n".join(
            f"{t['speaker'].upper()}: {t['text']}" for t in transcript_turns)

        extraction = await asyncio.to_thread(_run_extraction_sync, po, transcript_text)
        logger.info("call {} extraction: {}", call_id, extraction.model_dump())

        await asyncio.to_thread(
            db.update_call, call_id,
            outcome="completed",
            ended_at=datetime.now(timezone.utc).isoformat(),
            extraction=extraction.model_dump(),
        )

        auto_write = (extraction.reached_supplier
                      and extraction.confidence in ("high", "medium")
                      and extraction.status in ("confirmed_on_time", "delayed", "shipped"))
        if auto_write:
            await asyncio.to_thread(
                db.set_po_status, po_id, extraction.status,
                extraction.eta_date, extraction.delay_reason)
            await asyncio.to_thread(db.add_po_event, po_id, "status_changed", {
                "status": extraction.status, "eta_date": extraction.eta_date,
                "delay_reason": extraction.delay_reason,
                "confidence": extraction.confidence,
                "summary": extraction.summary, "call_id": call_id,
            })
        else:
            await asyncio.to_thread(db.set_po_status, po_id, "needs_review")
            await asyncio.to_thread(db.add_po_event, po_id, "flagged_review", {
                "status": extraction.status, "confidence": extraction.confidence,
                "summary": extraction.summary, "call_id": call_id,
            })

        await asyncio.to_thread(db.add_po_event, po_id, "call_completed",
                                {"call_id": call_id, "summary": extraction.summary})
    except Exception:
        logger.exception("post-call finalization failed for call {}", call_id)
        try:
            await asyncio.to_thread(db.set_po_status, po_id, "needs_review")
            await asyncio.to_thread(db.add_po_event, po_id, "flagged_review",
                                    {"reason": "extraction error", "call_id": call_id})
        except Exception:
            logger.exception("could not flag PO for review")
