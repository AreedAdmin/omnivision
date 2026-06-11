"""Supabase data layer.

All functions are synchronous (supabase-py sync client). Voice-pipeline tool
handlers wrap them in asyncio.to_thread so DB I/O never blocks the audio loop.
Dataset is seed-sized, so the few in-Python aggregations here are fine.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from loguru import logger
from supabase import create_client
from supabase.lib.client_options import SyncClientOptions

from config import settings

_sb = create_client(
    settings.supabase_url,
    settings.supabase_key,
    options=SyncClientOptions(schema=settings.supabase_schema),
)


def _t(table: str):
    return _sb.table(table)


# ─────────────────────────── products & locations ───────────────────────────

def find_products(query: str) -> list[dict]:
    """Fuzzy product lookup by name or SKU."""
    q = (query or "").strip().replace(",", " ")
    if not q:
        return []
    res = _t("products").select("*").or_(f"name.ilike.%{q}%,sku.ilike.%{q}%").execute()
    if res.data:
        return res.data
    # token fallback: match any meaningful word
    seen: dict[str, dict] = {}
    for w in [w for w in q.split() if len(w) > 2]:
        res = _t("products").select("*").ilike("name", f"%{w}%").execute()
        for row in res.data or []:
            seen[row["id"]] = row
    return list(seen.values())


def get_location(aisle: int, bin_: int, shelf: int) -> Optional[dict]:
    res = (_t("locations").select("*")
           .eq("aisle", aisle).eq("bin", bin_).eq("shelf", shelf)
           .limit(1).execute())
    return res.data[0] if res.data else None


def get_zone_location(zone: str) -> Optional[dict]:
    res = _t("locations").select("*").eq("zone", zone).limit(1).execute()
    return res.data[0] if res.data else None


def product_locations(product_id: str) -> list[dict]:
    res = (_t("inventory")
           .select("qty, locations(aisle, bin, shelf, zone)")
           .eq("product_id", product_id).gt("qty", 0).execute())
    out = []
    for r in res.data or []:
        loc = r.get("locations") or {}
        out.append({"aisle": loc.get("aisle"), "bin": loc.get("bin"),
                    "shelf": loc.get("shelf"), "qty": r["qty"]})
    return out


def inventory_at(product_id: str, location_id: str) -> int:
    res = (_t("inventory").select("qty")
           .eq("product_id", product_id).eq("location_id", location_id)
           .limit(1).execute())
    return res.data[0]["qty"] if res.data else 0


def _set_inventory(product_id: str, location_id: str, qty: int) -> None:
    existing = (_t("inventory").select("id")
                .eq("product_id", product_id).eq("location_id", location_id)
                .limit(1).execute())
    if existing.data:
        _t("inventory").update({"qty": max(0, qty)}).eq("id", existing.data[0]["id"]).execute()
    else:
        _t("inventory").insert({"product_id": product_id, "location_id": location_id,
                                "qty": max(0, qty)}).execute()


def record_movement(product_id: str, location_id: Optional[str], delta: int,
                    reason: str, source: str, session_ref: Optional[str]) -> None:
    _t("stock_movements").insert({
        "product_id": product_id, "location_id": location_id, "delta": delta,
        "reason": reason, "source": source, "session_ref": session_ref,
    }).execute()


# ─────────────────────────────── floor ops ──────────────────────────────────

VARIANCE_FLAG_THRESHOLD = 3


def log_variance(product_id: str, location_id: str, system_qty: int,
                 counted_qty: int, session_ref: Optional[str]) -> dict:
    delta = counted_qty - system_qty
    flagged = abs(delta) >= VARIANCE_FLAG_THRESHOLD
    _t("variance_logs").insert({
        "product_id": product_id, "location_id": location_id,
        "system_qty": system_qty, "counted_qty": counted_qty,
        "flagged": flagged, "session_ref": session_ref,
    }).execute()
    return {"system_qty": system_qty, "counted_qty": counted_qty,
            "delta": delta, "flagged": flagged}


def log_disposition(product_id: str, qty: int, reason: str, from_location_id: Optional[str],
                    to_zone: str, session_ref: Optional[str]) -> dict:
    _t("dispositions").insert({
        "product_id": product_id, "qty": qty, "reason": reason,
        "from_location": from_location_id, "to_zone": to_zone,
        "session_ref": session_ref,
    }).execute()
    if from_location_id:
        current = inventory_at(product_id, from_location_id)
        _set_inventory(product_id, from_location_id, current - qty)
        record_movement(product_id, from_location_id, -qty, "disposition",
                        "voice_ops", session_ref)
    return {"logged": True, "qty": qty, "reason": reason, "to_zone": to_zone}


def adjust_stock(product_id: str, location_id: str, new_qty: int,
                 reason: str, session_ref: Optional[str]) -> dict:
    old_qty = inventory_at(product_id, location_id)
    _set_inventory(product_id, location_id, new_qty)
    record_movement(product_id, location_id, new_qty - old_qty, "adjustment",
                    "voice_ops", session_ref)
    return {"old_qty": old_qty, "new_qty": new_qty}


# ─────────────────────────── manager analytics ──────────────────────────────

def stock_level(product_id: str) -> dict:
    locs = product_locations(product_id)
    prod = _t("products").select("name, reorder_point").eq("id", product_id).limit(1).execute()
    p = prod.data[0] if prod.data else {}
    return {"product": p.get("name"), "total": sum(l["qty"] for l in locs),
            "reorder_point": p.get("reorder_point"), "locations": locs}


def sale_rate(product_id: str, period_days: int = 30) -> dict:
    now = datetime.now(timezone.utc)
    cur_start = now - timedelta(days=period_days)
    prev_start = now - timedelta(days=2 * period_days)

    res = (_t("sales").select("qty, sold_at")
           .eq("product_id", product_id)
           .gte("sold_at", prev_start.isoformat()).execute())
    cur = prev = 0
    for row in res.data or []:
        sold_at = datetime.fromisoformat(row["sold_at"].replace("Z", "+00:00"))
        if sold_at >= cur_start:
            cur += row["qty"]
        else:
            prev += row["qty"]
    per_day = cur / period_days if period_days else 0
    trend_pct = round(((cur - prev) / prev) * 100) if prev else None
    return {"period_days": period_days, "units_sold": cur,
            "units_per_day": round(per_day, 1), "trend_pct_vs_prior_period": trend_pct}


def low_stock_report() -> list[dict]:
    products = _t("products").select("id, name, reorder_point").execute().data or []
    inv = _t("inventory").select("product_id, qty").execute().data or []
    totals: dict[str, int] = {}
    for row in inv:
        totals[row["product_id"]] = totals.get(row["product_id"], 0) + row["qty"]

    open_pos = (_t("purchase_orders")
                .select("product_id, po_number, expected_date, status, suppliers(name)")
                .not_.in_("status", ["received"]).execute().data or [])
    pos_by_product: dict[str, dict] = {}
    for po in open_pos:
        pos_by_product.setdefault(po["product_id"], po)

    out = []
    for p in products:
        total = totals.get(p["id"], 0)
        if total < p["reorder_point"]:
            entry: dict[str, Any] = {"product": p["name"], "on_hand": total,
                                     "reorder_point": p["reorder_point"], "open_po": None}
            po = pos_by_product.get(p["id"])
            if po:
                days_overdue = (date.today() - date.fromisoformat(po["expected_date"])).days
                entry["open_po"] = {
                    "po_number": po["po_number"],
                    "supplier": (po.get("suppliers") or {}).get("name"),
                    "status": po["status"],
                    "days_overdue": max(0, days_overdue),
                }
            out.append(entry)
    return out


def open_pos_report(only_overdue: bool = False) -> list[dict]:
    res = (_t("purchase_orders")
           .select("po_number, qty, expected_date, status, eta_date, delay_reason,"
                   " suppliers(name), products(name)")
           .not_.in_("status", ["received"]).order("expected_date").execute())
    out = []
    for po in res.data or []:
        days_overdue = (date.today() - date.fromisoformat(po["expected_date"])).days
        if only_overdue and days_overdue <= 0:
            continue
        out.append({
            "po_number": po["po_number"],
            "supplier": (po.get("suppliers") or {}).get("name"),
            "product": (po.get("products") or {}).get("name"),
            "qty": po["qty"], "expected_date": po["expected_date"],
            "status": po["status"], "days_overdue": max(0, days_overdue),
            "eta_date": po.get("eta_date"), "delay_reason": po.get("delay_reason"),
        })
    return out


def top_movers(period_days: int = 7, n: int = 5) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()
    res = _t("sales").select("product_id, qty").gte("sold_at", since).execute()
    totals: dict[str, int] = {}
    for row in res.data or []:
        totals[row["product_id"]] = totals.get(row["product_id"], 0) + row["qty"]
    products = {p["id"]: p["name"] for p in
                (_t("products").select("id, name").execute().data or [])}
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [{"product": products.get(pid, "unknown"), "units_sold": qty}
            for pid, qty in ranked]


# ─────────────────────────── purchasing / calls ─────────────────────────────

def get_po_full(po_id: str) -> Optional[dict]:
    res = (_t("purchase_orders")
           .select("*, suppliers(id, name, phone, contact_name), products(id, name)")
           .eq("id", po_id).limit(1).execute())
    return res.data[0] if res.data else None


def set_po_status(po_id: str, status: str, eta_date: Optional[str] = None,
                  delay_reason: Optional[str] = None) -> None:
    update: dict[str, Any] = {"status": status,
                              "updated_at": datetime.now(timezone.utc).isoformat()}
    if eta_date:
        update["eta_date"] = eta_date
    if delay_reason:
        update["delay_reason"] = delay_reason
    _t("purchase_orders").update(update).eq("id", po_id).execute()


def add_po_event(po_id: str, event: str, detail: Optional[dict] = None) -> None:
    _t("po_events").insert({"po_id": po_id, "event": event, "detail": detail or {}}).execute()


def create_call(po_id: str, supplier_id: str) -> dict:
    res = _t("calls").insert({"po_id": po_id, "supplier_id": supplier_id}).execute()
    return res.data[0]


def update_call(call_id: str, **fields: Any) -> None:
    _t("calls").update(fields).eq("id", call_id).execute()


def find_call_by_twilio_sid(twilio_sid: str) -> Optional[dict]:
    res = _t("calls").select("*").eq("twilio_sid", twilio_sid).limit(1).execute()
    return res.data[0] if res.data else None


def insert_transcript_turn(call_id: str, turn_no: int, speaker: str, text: str) -> None:
    try:
        _t("call_transcripts").insert({
            "call_id": call_id, "turn_no": turn_no, "speaker": speaker, "text": text,
        }).execute()
    except Exception:  # transcript persistence must never kill a live call
        logger.exception("failed to persist transcript turn")


# ─────────────────────── lookups for the telephony app + dashboard ───────────

def get_po_by_number(po_number: str) -> Optional[dict]:
    res = (_t("purchase_orders")
           .select("*, suppliers(id, name, phone, contact_name), products(id, name)")
           .eq("po_number", po_number).limit(1).execute())
    return res.data[0] if res.data else None


def get_call(call_id: str) -> Optional[dict]:
    res = _t("calls").select("*").eq("id", call_id).limit(1).execute()
    return res.data[0] if res.data else None


def latest_call_for_po(po_id: str) -> Optional[dict]:
    res = (_t("calls").select("*").eq("po_id", po_id)
           .order("started_at", desc=True).limit(1).execute())
    return res.data[0] if res.data else None


def transcript_turns(call_id: str) -> list[dict]:
    res = (_t("call_transcripts").select("turn_no, speaker, text")
           .eq("call_id", call_id).order("turn_no").execute())
    return res.data or []


def dashboard_state() -> list[dict]:
    """Everything the dashboard needs in one shot: PO cards + latest call + transcript."""
    pos = (_t("purchase_orders")
           .select("id, po_number, qty, expected_date, status, eta_date, delay_reason,"
                   " suppliers(name), products(name)")
           .order("po_number").execute().data or [])
    out = []
    for po in pos:
        call = latest_call_for_po(po["id"])
        turns = transcript_turns(call["id"]) if call else []
        out.append({
            "po_number": po["po_number"],
            "product": (po.get("products") or {}).get("name"),
            "supplier": (po.get("suppliers") or {}).get("name"),
            "qty": po["qty"],
            "expected_date": po["expected_date"],
            "status": po["status"],
            "eta_date": po.get("eta_date"),
            "delay_reason": po.get("delay_reason"),
            "call": {
                "outcome": call.get("outcome"),
                "extraction": call.get("extraction"),
                "transcript": turns,
            } if call else None,
        })
    return out


def calls_for_po(po_id: str) -> list[dict]:
    """All calls for a PO (newest first), each with its transcript turns."""
    calls = (_t("calls").select("*").eq("po_id", po_id)
             .order("started_at", desc=True).execute().data or [])
    for c in calls:
        c["transcript"] = transcript_turns(c["id"])
    return calls


def events_for_po(po_id: str) -> list[dict]:
    """Full audit/status-change log for a PO (newest first)."""
    return (_t("po_events").select("event, detail, created_at")
            .eq("po_id", po_id).order("created_at", desc=True).execute().data or [])


def get_po_detail(po_number: str) -> Optional[dict]:
    """Everything the PO detail drawer needs: order fields + calls + status log."""
    po = get_po_by_number(po_number)
    if not po:
        return None
    supplier = po.get("suppliers") or {}
    return {
        "po_number": po["po_number"],
        "product": (po.get("products") or {}).get("name"),
        "supplier": supplier.get("name"),
        "supplier_contact": supplier.get("contact_name"),
        "supplier_phone": supplier.get("phone"),
        "qty": po["qty"],
        "expected_date": po["expected_date"],
        "status": po["status"],
        "eta_date": po.get("eta_date"),
        "delay_reason": po.get("delay_reason"),
        "created_at": po.get("created_at"),
        "updated_at": po.get("updated_at"),
        "calls": calls_for_po(po["id"]),
        "events": events_for_po(po["id"]),
    }
