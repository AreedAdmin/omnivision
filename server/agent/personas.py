"""Persona registry: one brain, persona-scoped prompts + tools (plan/04).

build_persona(name, session_ref) → PersonaConfig(system, tools, handlers)
build_inbound_prompt(ctx)        → system prompt for a supplier call
"""

from __future__ import annotations

from dataclasses import dataclass

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema

from agent.tools import manager as manager_tools
from agent.tools import ops as ops_tools
from config import settings

# ───────────────────────────── shared preamble ──────────────────────────────

SHARED_PREAMBLE = f"""You are Omnivision, the voice agent for {settings.company_name}.
You are speaking aloud: keep replies to one or two short sentences.
Read numbers naturally ("twelve units", never "12x"). Never use markdown,
bullet points, tables, or emoji — plain spoken sentences only.
Ask exactly one question when you need clarification.
If you didn't catch something, ask the person to repeat just that part.
Only state quantities, locations, and figures that came from your tools —
never guess or invent a number."""

OPS_PROMPT = SHARED_PREAMBLE + """

You help warehouse floor workers operate the warehouse management system by voice.
You can look up product locations, log stock variances, log expired or damaged
stock dispositions, and adjust stock quantities.
Locations are always spoken and confirmed as: aisle N, bin N, shelf N.

Write protocol — follow it strictly:
1. For a variance: first call get_location_count to learn the system quantity,
   read it back ("system says twelve, you counted eight — variance minus four"),
   and ask "Shall I log that?". Only after a clear yes, call log_variance.
2. For dispositions and stock adjustments: state exactly what you will record
   and ask for confirmation before calling the write tool.
3. Never perform more than one write per confirmation.

When a worker reports expired or damaged stock, answer their routing question
FIRST (use get_disposition_rule), then offer to log it.
If a product or location doesn't match the database, say what you found instead
and ask them to re-check the label."""

MANAGER_PROMPT = SHARED_PREAMBLE + """

You answer business and operations questions for warehouse managers using the
live database. Answer with the number first, then one short sentence of context.
If a question is ambiguous (for example, which time period), pick the most
natural default, say which one you used, and answer — don't interrogate.
You keep conversation context: follow-up questions and pronouns refer to your
previous answers, and you may do simple arithmetic on numbers your tools
already returned (for example, days of stock cover = on-hand divided by daily
sale rate).
When a report has more than three items, speak the top three and say the rest
are on screen.
If asked something your tools can't answer, say what you CAN report on —
never improvise figures."""


def build_inbound_prompt(ctx: dict) -> str:
    """System prompt for an outbound supplier call. ctx comes from calls.py."""
    return f"""You are Omnivision, an automated voice assistant calling on behalf of
{settings.company_name}'s inbound team. You are on a live phone call with
{ctx['supplier_name']}. Speak in short, natural, polite sentences — one or two
per turn. Never use markdown or lists. This is a real phone conversation.

You are following up on purchase order {ctx['po_number']}:
{ctx['qty']} units of {ctx['product_name']}, expected {ctx['expected_date']},
now {ctx['days_overdue']} days overdue.

Your single goal: learn the order status, the expected delivery date, and the
reason for any delay.

Call flow:
1. Open by greeting, identifying yourself as an automated assistant calling
   for {settings.company_name}, and mentioning purchase order {ctx['po_number']}.
2. Ask for the current status of the order.
3. If delayed: ask for the expected delivery date, and gently ask the reason
   once — never push.
4. When you have what you need, confirm it back in one sentence
   ("So that's shipping Friday, delayed by a raw-material shortage — correct?").
5. After they confirm, thank them, say goodbye, and call the end_call tool.

Strict rules:
- Stay on this one order only. If asked anything else say: "I'm only able to
  check on this order's status today."
- Never negotiate, never discuss prices, never place or change orders.
- If the person is confused, busy, or asks for a human: give them the callback
  number {settings.callback_number}, thank them, say goodbye, and call end_call.
- If you already confirmed the details, do not re-ask — close the call."""


# ─────────────────────────────── tool schemas ────────────────────────────────

_LOC_PROPS = {
    "aisle": {"type": "integer", "description": "Aisle number"},
    "bin": {"type": "integer", "description": "Bin number"},
    "shelf": {"type": "integer", "description": "Shelf number"},
}

OPS_SCHEMAS = [
    FunctionSchema(
        name="locate_product",
        description="Find where a product is stored. Call whenever a worker asks "
                    "where a product is, or before discussing a product's stock.",
        properties={"product_query": {"type": "string",
                    "description": "Product name or SKU as spoken by the worker"}},
        required=["product_query"],
    ),
    FunctionSchema(
        name="get_location_count",
        description="Read the system quantity of a product at one aisle/bin/shelf. "
                    "Call this FIRST when a worker reports a count or variance, so "
                    "you can read back the system quantity before logging anything.",
        properties={"product_query": {"type": "string"}, **_LOC_PROPS},
        required=["product_query", "aisle", "bin", "shelf"],
    ),
    FunctionSchema(
        name="log_variance",
        description="Record a stock variance after the worker confirmed ('yes'). "
                    "Writes the variance to the database.",
        properties={"product_query": {"type": "string"}, **_LOC_PROPS,
                    "counted_qty": {"type": "integer",
                                    "description": "Quantity the worker physically counted"}},
        required=["product_query", "aisle", "bin", "shelf", "counted_qty"],
    ),
    FunctionSchema(
        name="get_disposition_rule",
        description="Look up where expired or damaged stock must be taken. Call when "
                    "a worker reports expired/damaged items and asks where to take them.",
        properties={"product_query": {"type": "string"},
                    "reason": {"type": "string", "enum": ["expired", "damaged"]}},
        required=["product_query", "reason"],
    ),
    FunctionSchema(
        name="log_disposition",
        description="Record an expired/damaged disposition and decrement stock, after "
                    "the worker confirmed. aisle/bin/shelf optional if unknown.",
        properties={"product_query": {"type": "string"},
                    "qty": {"type": "integer"},
                    "reason": {"type": "string", "enum": ["expired", "damaged"]},
                    **_LOC_PROPS},
        required=["product_query", "qty", "reason"],
    ),
    FunctionSchema(
        name="adjust_stock",
        description="Set the stock quantity at a location to a new value after a "
                    "confirmed recount. Use only when the worker explicitly asks for "
                    "a correction and has confirmed.",
        properties={"product_query": {"type": "string"}, **_LOC_PROPS,
                    "new_qty": {"type": "integer"},
                    "reason": {"type": "string",
                               "description": "Why, in the worker's words"}},
        required=["product_query", "aisle", "bin", "shelf", "new_qty", "reason"],
    ),
]

MANAGER_SCHEMAS = [
    FunctionSchema(
        name="get_stock_level",
        description="Total on-hand stock for a product with per-location breakdown. "
                    "Call when asked how much stock exists of something.",
        properties={"product_query": {"type": "string"}},
        required=["product_query"],
    ),
    FunctionSchema(
        name="get_sale_rate",
        description="Units sold per day for a product over a period, with trend vs "
                    "the prior period. Call for any sales-velocity question.",
        properties={"product_query": {"type": "string"},
                    "period_days": {"type": "integer",
                                    "description": "Period length in days, default 30"}},
        required=["product_query"],
    ),
    FunctionSchema(
        name="low_stock_report",
        description="Products below their reorder point, each with any open purchase "
                    "order. Call when asked what's low, short, or needs reordering.",
        properties={},
        required=[],
    ),
    FunctionSchema(
        name="open_pos_report",
        description="Open purchase orders with supplier, product, and days overdue. "
                    "Call when asked about orders, deliveries, or what's overdue.",
        properties={"only_overdue": {"type": "boolean"}},
        required=[],
    ),
    FunctionSchema(
        name="top_movers",
        description="Top N products by units sold over a recent period. Call when "
                    "asked what's selling best.",
        properties={"period_days": {"type": "integer"}, "n": {"type": "integer"}},
        required=[],
    ),
]

INBOUND_CALL_SCHEMAS = [
    FunctionSchema(
        name="end_call",
        description="Hang up the phone call. Call this ONLY after you have said "
                    "goodbye to the supplier.",
        properties={},
        required=[],
    ),
]


# ──────────────────────────────── registry ───────────────────────────────────

@dataclass
class PersonaConfig:
    name: str
    system: str
    tools: ToolsSchema
    handlers: dict


def build_persona(name: str, session_ref: str) -> PersonaConfig:
    if name == "ops":
        return PersonaConfig(name, OPS_PROMPT, ToolsSchema(standard_tools=OPS_SCHEMAS),
                             ops_tools.build_handlers(session_ref))
    if name == "manager":
        return PersonaConfig(name, MANAGER_PROMPT,
                             ToolsSchema(standard_tools=MANAGER_SCHEMAS),
                             manager_tools.build_handlers(session_ref))
    raise ValueError(f"unknown persona: {name}")
