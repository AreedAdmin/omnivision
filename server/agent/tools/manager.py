"""Manager (talk-to-data) tool handlers — curated analytics, no text-to-SQL.

Every number the agent speaks comes from one of these tools (plan/07)."""

from __future__ import annotations

import asyncio

from pipecat.services.llm_service import FunctionCallParams

import db


async def _resolve_product(query: str) -> dict:
    products = await asyncio.to_thread(db.find_products, query)
    if not products:
        return {"ok": False, "message": f"No product matched '{query}'."}
    if len(products) > 1:
        return {"ok": False,
                "matches": [{"name": p["name"], "sku": p["sku"]} for p in products[:4]],
                "message": "Multiple products matched — ask which one."}
    return {"ok": True, "product": products[0]}


def build_handlers(session_ref: str) -> dict:

    async def get_stock_level(params: FunctionCallParams):
        prod = await _resolve_product(params.arguments.get("product_query", ""))
        if not prod["ok"]:
            await params.result_callback(prod)
            return
        result = await asyncio.to_thread(db.stock_level, prod["product"]["id"])
        result["ok"] = True
        await params.result_callback(result)

    async def get_sale_rate(params: FunctionCallParams):
        a = params.arguments
        prod = await _resolve_product(a.get("product_query", ""))
        if not prod["ok"]:
            await params.result_callback(prod)
            return
        result = await asyncio.to_thread(
            db.sale_rate, prod["product"]["id"], int(a.get("period_days", 30)))
        result["ok"] = True
        result["product"] = prod["product"]["name"]
        await params.result_callback(result)

    async def low_stock_report(params: FunctionCallParams):
        rows = await asyncio.to_thread(db.low_stock_report)
        await params.result_callback({"ok": True, "low_stock": rows})

    async def open_pos_report(params: FunctionCallParams):
        only_overdue = params.arguments.get("only_overdue", False)
        rows = await asyncio.to_thread(db.open_pos_report, bool(only_overdue))
        await params.result_callback({"ok": True, "purchase_orders": rows})

    async def top_movers(params: FunctionCallParams):
        a = params.arguments
        rows = await asyncio.to_thread(
            db.top_movers, int(a.get("period_days", 7)), int(a.get("n", 5)))
        await params.result_callback({"ok": True, "top_movers": rows})

    return {
        "get_stock_level": get_stock_level,
        "get_sale_rate": get_sale_rate,
        "low_stock_report": low_stock_report,
        "open_pos_report": open_pos_report,
        "top_movers": top_movers,
    }
