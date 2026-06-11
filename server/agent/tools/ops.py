"""Ops-worker (floor) tool handlers.

Handlers follow Pipecat's function-calling contract:
    async def handler(params: FunctionCallParams) -> None
    -> await params.result_callback(<json-serializable result>)

All DB calls run via asyncio.to_thread so they never block the audio loop.
"""

from __future__ import annotations

import asyncio

from pipecat.services.llm_service import FunctionCallParams

import db

# Disposition routing rules (plan/05): config, not a table.
DISPOSITION_RULES = {
    ("expired", "food"): {"to_zone": "disposal",
                          "spoken": "Expired food goes to disposal zone D1."},
    ("expired", "non-food"): {"to_zone": "returns_cage",
                              "spoken": "Expired non-food goes to the returns cage, R2."},
    ("damaged", "food"): {"to_zone": "returns_cage",
                          "spoken": "Damaged items go to the returns cage, R2 — tag them as damaged."},
    ("damaged", "non-food"): {"to_zone": "returns_cage",
                              "spoken": "Damaged items go to the returns cage, R2 — tag them as damaged."},
}


async def _resolve_product(query: str) -> dict:
    """Resolve a spoken product query → single product, or a disambiguation payload."""
    products = await asyncio.to_thread(db.find_products, query)
    if not products:
        return {"ok": False, "error": "no_match",
                "message": f"No product matched '{query}'. Ask for the SKU on the label."}
    if len(products) > 1:
        return {"ok": False, "error": "ambiguous",
                "matches": [{"name": p["name"], "sku": p["sku"]} for p in products[:4]],
                "message": "Multiple products matched — ask which one they mean."}
    return {"ok": True, "product": products[0]}


async def _resolve_location(aisle: int, bin_: int, shelf: int) -> dict:
    loc = await asyncio.to_thread(db.get_location, aisle, bin_, shelf)
    if not loc:
        return {"ok": False, "error": "no_location",
                "message": f"Aisle {aisle} bin {bin_} shelf {shelf} is not a known location."}
    return {"ok": True, "location": loc}


def build_handlers(session_ref: str) -> dict:
    """Return {tool_name: handler} bound to this voice session."""

    async def locate_product(params: FunctionCallParams):
        query = params.arguments.get("product_query", "")
        products = await asyncio.to_thread(db.find_products, query)
        if not products:
            await params.result_callback(
                {"found": False, "message": f"No product matched '{query}'."})
            return
        matches = []
        for p in products[:3]:
            locs = await asyncio.to_thread(db.product_locations, p["id"])
            matches.append({"product": p["name"], "sku": p["sku"], "locations": locs})
        await params.result_callback({"found": True, "matches": matches})

    async def get_location_count(params: FunctionCallParams):
        """Pre-check before a variance write: what does the system say is here?"""
        a = params.arguments
        prod = await _resolve_product(a.get("product_query", ""))
        if not prod["ok"]:
            await params.result_callback(prod)
            return
        loc = await _resolve_location(a.get("aisle"), a.get("bin"), a.get("shelf"))
        if not loc["ok"]:
            await params.result_callback(loc)
            return
        qty = await asyncio.to_thread(
            db.inventory_at, prod["product"]["id"], loc["location"]["id"])
        await params.result_callback({
            "ok": True, "product": prod["product"]["name"], "system_qty": qty})

    async def log_variance(params: FunctionCallParams):
        a = params.arguments
        prod = await _resolve_product(a.get("product_query", ""))
        if not prod["ok"]:
            await params.result_callback(prod)
            return
        loc = await _resolve_location(a.get("aisle"), a.get("bin"), a.get("shelf"))
        if not loc["ok"]:
            await params.result_callback(loc)
            return
        system_qty = await asyncio.to_thread(
            db.inventory_at, prod["product"]["id"], loc["location"]["id"])
        result = await asyncio.to_thread(
            db.log_variance, prod["product"]["id"], loc["location"]["id"],
            system_qty, int(a.get("counted_qty")), session_ref)
        result["ok"] = True
        result["product"] = prod["product"]["name"]
        await params.result_callback(result)

    async def get_disposition_rule(params: FunctionCallParams):
        a = params.arguments
        prod = await _resolve_product(a.get("product_query", ""))
        if not prod["ok"]:
            await params.result_callback(prod)
            return
        reason = a.get("reason", "expired")
        rule = DISPOSITION_RULES.get((reason, prod["product"]["category"]))
        if not rule:
            await params.result_callback(
                {"ok": False, "message": f"No disposition rule for {reason}."})
            return
        await params.result_callback(
            {"ok": True, "product": prod["product"]["name"], "reason": reason, **rule})

    async def log_disposition(params: FunctionCallParams):
        a = params.arguments
        prod = await _resolve_product(a.get("product_query", ""))
        if not prod["ok"]:
            await params.result_callback(prod)
            return
        reason = a.get("reason", "expired")
        rule = DISPOSITION_RULES.get((reason, prod["product"]["category"]),
                                     {"to_zone": "returns_cage"})
        from_location_id = None
        if all(a.get(k) is not None for k in ("aisle", "bin", "shelf")):
            loc = await _resolve_location(a["aisle"], a["bin"], a["shelf"])
            if loc["ok"]:
                from_location_id = loc["location"]["id"]
        else:
            locs = await asyncio.to_thread(db.product_locations, prod["product"]["id"])
            if locs:
                first = await asyncio.to_thread(
                    db.get_location, locs[0]["aisle"], locs[0]["bin"], locs[0]["shelf"])
                from_location_id = first["id"] if first else None
        result = await asyncio.to_thread(
            db.log_disposition, prod["product"]["id"], int(a.get("qty")),
            reason, from_location_id, rule["to_zone"], session_ref)
        result["ok"] = True
        result["product"] = prod["product"]["name"]
        await params.result_callback(result)

    async def adjust_stock(params: FunctionCallParams):
        a = params.arguments
        prod = await _resolve_product(a.get("product_query", ""))
        if not prod["ok"]:
            await params.result_callback(prod)
            return
        loc = await _resolve_location(a.get("aisle"), a.get("bin"), a.get("shelf"))
        if not loc["ok"]:
            await params.result_callback(loc)
            return
        result = await asyncio.to_thread(
            db.adjust_stock, prod["product"]["id"], loc["location"]["id"],
            int(a.get("new_qty")), a.get("reason", "voice adjustment"), session_ref)
        result["ok"] = True
        result["product"] = prod["product"]["name"]
        await params.result_callback(result)

    return {
        "locate_product": locate_product,
        "get_location_count": get_location_count,
        "log_variance": log_variance,
        "get_disposition_rule": get_disposition_rule,
        "log_disposition": log_disposition,
        "adjust_stock": adjust_stock,
    }
