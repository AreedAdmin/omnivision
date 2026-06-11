# 04 — Agent Core (Reasoning, Tools, Prompts, Guardrails)

The brain shared by all three personas. One agent loop; persona determines system prompt + tool subset.

## Design principles

1. **One loop, scoped tools.** A single Claude tool-calling loop. Persona config = `{system_prompt, tools[]}`. No per-persona forks of the agent code.
2. **Voice-first output discipline.** Everything the LLM says will be *spoken*. System prompts enforce: short sentences, numbers read naturally ("twelve units", not tables), no markdown, no lists read aloud, one question at a time.
3. **Confirm before commit.** Any tool that *writes* (variance, disposition, PO status) is preceded by a spoken read-back and an explicit confirmation from the human — except the supplier call's post-call write, which is automatic but logged with confidence + full transcript for audit.
4. **Single-intent phone calls.** The supplier-call persona is locked to one goal (order status). It does not answer unrelated questions, take new orders, or negotiate. Out-of-scope supplier utterances get: "I'm only able to check on this order's status today."

## Models

| Path | Model | Why |
|---|---|---|
| Live turns (all personas) | `claude-sonnet-4-6`, streaming, lean prompts | ~1s turn budget |
| Post-call extraction | `claude-opus-4-8` + structured outputs | Correctness of the DB write; not latency-bound |
| Manager "deep" questions (optional) | `claude-opus-4-8` | Only if a question needs multi-step aggregation beyond curated tools; acceptable to take 3–5s with a spoken "let me work that out…" |

Live-turn calls: `client.messages.stream(...)` with `tools=`, manual agentic loop inside the Pipecat LLM service (execute tool → feed `tool_result` → continue until `end_turn`). Keep `max_tokens` modest (~1024) — spoken replies are short.

## Persona configs

```python
PERSONAS = {
  "ops":     {"system": OPS_PROMPT,     "tools": [locate_product, log_variance, log_disposition, adjust_stock, get_disposition_rule]},
  "manager": {"system": MANAGER_PROMPT, "tools": [get_stock_level, get_sale_rate, low_stock_report, open_pos_report, top_movers]},
  "inbound": {"system": INBOUND_PROMPT, "tools": []},  # phone persona: pure dialogue, context preloaded; writes happen post-call
}
```

The inbound *call* persona deliberately has **no tools live on the call** — all PO context is preloaded into its system prompt before dialing, and all writes happen in the post-call extraction step. This keeps phone turns fast and makes mid-call failure harmless (nothing was written yet).

## System prompt skeletons

### Shared preamble (all personas)
```
You are Omnivision, the voice agent for [WAREHOUSE NAME].
You are speaking aloud: keep replies to one or two short sentences.
Read numbers naturally. Never use markdown, bullets, or tables.
Ask exactly one question when you need clarification.
If you didn't catch something, ask the person to repeat just that part.
```

### Ops worker
```
You help warehouse floor workers operate the WMS by voice.
You can look up product locations, log stock variances, log expired or
damaged stock dispositions, and adjust stock.
Locations are spoken as aisle / bin / shelf.
Before any write (variance, disposition, adjustment): read back exactly
what you will record and ask "Shall I log that?" — only write after a yes.
If a product or location doesn't match the database, say what you found
instead and ask them to re-check the label.
```

### Manager
```
You answer business and operations questions for warehouse managers using
the live database. Answer with the number first, then one sentence of
context. If a question is ambiguous (e.g. which time period), pick the
most natural default, state it, and answer — don't interrogate.
You keep conversation context: follow-up questions refer to prior answers.
```

### Inbound supplier call (channel B; context interpolated per call)
```
You are calling {supplier_name} on behalf of {company_name}'s inbound team.
You are following up on purchase order {po_number}: {qty} x {product_name},
expected {expected_date}, now {days_overdue} days overdue.
Goal: learn the order status, expected delivery date, and reason for any delay.
Open by greeting, identifying yourself as an automated assistant calling for
{company_name}, and stating the PO number.
Stay strictly on this one order. If asked anything else: "I'm only able to
check on this order's status today."
When you have status + ETA (+ reason if delayed), confirm them back in one
sentence, thank them, and say goodbye. Then the call ends.
If the person is confused or asks for a human, give the callback number
{callback_number}, thank them, and end the call politely.
```

## Tool definitions (registry)

All tools: JSON-schema input, executed server-side against Supabase, return compact JSON the model can speak from. Descriptions are prescriptive about *when* to call (Sonnet picks tools from descriptions).

### Ops tools
| Tool | Input | Behavior |
|---|---|---|
| `locate_product` | `{product_query}` | Fuzzy-match product by name/SKU; return locations `[{aisle,bin,shelf,qty}]` |
| `log_variance` | `{product_id, aisle, bin, shelf, counted_qty}` | Read system qty at location, write `variance_logs` row with delta, flag if |delta| ≥ threshold; returns `{system_qty, delta, flagged}` |
| `get_disposition_rule` | `{product_id, reason: expired\|damaged}` | Return routing rule (e.g. "expired food → disposal zone D1; expired non-food → returns cage R2") |
| `log_disposition` | `{product_id, qty, reason, from_location, to_zone}` | Write `dispositions`, decrement `inventory`; returns confirmation |
| `adjust_stock` | `{product_id, location, new_qty, reason}` | Direct correction after confirmation; writes `stock_movements` |

### Manager tools (curated, not text-to-SQL — see 07)
| Tool | Input | Behavior |
|---|---|---|
| `get_stock_level` | `{product_query}` | Total on-hand + per-location breakdown |
| `get_sale_rate` | `{product_query, period_days=30}` | Units sold/day over period + trend vs prior period |
| `low_stock_report` | `{}` | Products below reorder point, with open-PO flag |
| `open_pos_report` | `{status?: overdue\|all}` | Open POs with supplier, qty, days overdue |
| `top_movers` | `{period_days=7, n=5}` | Top N products by units sold |

### Inbound tools (dashboard/voice-triggered, not on-call)
| Tool | Input | Behavior |
|---|---|---|
| `initiate_supplier_call` | `{po_id}` | Creates call context, dials via Twilio (see 03/08) |
| `update_po_status` | `{po_id, status, eta, reason, confidence, call_id}` | Called by the **extraction step**, not the live model; writes `purchase_orders` + `po_events` |

## Post-call extraction (Opus 4.8)

After every supplier call (`stop` frame or hangup):

```python
extraction = client.messages.parse(
    model="claude-opus-4-8",
    max_tokens=2048,
    messages=[{"role": "user", "content": EXTRACTION_PROMPT + transcript_text}],
    output_format=PoCallExtraction,  # pydantic
)
```

```python
class PoCallExtraction(BaseModel):
    reached_supplier: bool          # did we actually speak to someone about the PO
    status: Literal["confirmed_on_time", "delayed", "shipped", "unknown", "needs_human"]
    eta_date: Optional[str]         # ISO date if stated
    delay_reason: Optional[str]
    supplier_quotes: list[str]      # 1-3 verbatim supporting quotes from transcript
    confidence: Literal["high", "medium", "low"]
    summary: str                    # one sentence for the PO event log
```

Write policy: `confidence == high|medium` → update PO status automatically. `low` or `needs_human` → PO gets a "needs review" flag instead of a status change; dashboard shows the transcript for a human decision. **Every** call stores the full transcript + extraction JSON regardless.

## Conversation state

- Channel A sessions hold message history in memory per WS connection (a session = one push-to-talk conversation; manager follow-ups work within it). No cross-session persistence needed for the demo.
- Channel B: history lives for the call duration; transcript persisted at the end.
- Keep the system prompt byte-stable per persona and put dynamic context (PO details) at the *end* of the system prompt — prompt-caching friendly if sessions grow.

## Guardrails summary

1. Read-back + verbal confirm before any ops write.
2. Phone persona is toolless + single-intent; nothing is written until post-call extraction.
3. Confidence-gated auto-writes; low confidence → human review queue.
4. Barge-in cancels speech, never a committed write (03).
5. All writes carry provenance: `source: voice_ops | voice_manager | supplier_call`, session/call id, transcript reference.
