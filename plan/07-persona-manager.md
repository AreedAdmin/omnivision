# 07 — Persona: Manager (Talk-to-Data Mode)

Conversational analytics over live warehouse data. Channel A, persona `manager`. This persona proves the "same brain, different role" backbone claim in the demo with a 20-second beat.

## Design decision: curated tools, NOT text-to-SQL

Two ways to answer "what's my sale rate of product X":

| | Text-to-SQL | Curated tools |
|---|---|---|
| Coverage | Any question | The questions we define |
| Demo risk | High — one malformed query on stage and the beat dies | Near zero — tools are tested functions |
| Latency | Extra generation + execution round trip | One fast indexed query |
| Effort | Schema-prompting + SQL validation + error recovery | A handful of small functions |

**Decision: curated tools for the hackathon.** Five tools cover every demo-able question (see 04): `get_stock_level`, `get_sale_rate`, `low_stock_report`, `open_pos_report`, `top_movers`. Text-to-SQL is the roadmap slide ("open-ended analytics"), not weekend scope. If a judge asks an off-tool question live, the agent says what it *can* answer — system prompt instructs it to list its capabilities rather than hallucinate numbers. **Never let the model invent a figure**: every number it speaks must come from a tool result (prompt-enforced: "Only state numbers returned by your tools").

## Example dialogues

### D1 — Stock level (demo beat)
> **Mgr:** "How much stock do I have of basmati rice?"
> → `get_stock_level("basmati rice")`
> **Agent:** *"One hundred forty units total — one hundred at aisle 4 and forty at aisle 2. That's above its reorder point of fifty."*

### D2 — Sale rate + follow-up context (the wow moment)
> **Mgr:** "What's my sale rate on it this month?"  ← "it" resolves from D1 context
> → `get_sale_rate(product, 30)`
> **Agent:** *"Selling about nine units a day over the last thirty days — up roughly twenty percent on the month before."*
>
> **Mgr:** "So when do I run out?"
> Agent computes from the two prior tool results already in context (140 units ÷ 9/day): *"At that rate, roughly fifteen days of cover."*

D2's chain — pronoun resolution plus arithmetic over prior tool results with **no new tool needed** — is the moment that shows reasoning, not lookup. Rehearse it.

### D3 — Exception surfacing (ties personas together)
> **Mgr:** "Anything below reorder point?"
> → `low_stock_report()`
> **Agent:** *"Three products: AA batteries, dish soap, and sunflower oil. Sunflower oil already has an open PO — but it's six days overdue from Atlas Trading."*
>
> This hands the narrative directly to persona 3: *"...want me to have it chased?"* → segue into the supplier call. **Script the demo in exactly this order.**

## Spoken-number formatting rules (in system prompt)

- Round to speakable precision: "about nine units a day", not "9.13".
- Percentages to nearest 5% unless small: "up about twenty percent".
- Money: "twelve thousand four hundred dollars", never digit strings.
- Max three items spoken from any report; if more: "...and two others — they're on your screen." (Dashboard shows the full table — voice + screen complement each other.)

## Conversation state

Session history retained per WS connection (see 04). The follow-up beats (D2) depend on it — verify history threading works before scripting the demo around it.

## Model note

Default `claude-sonnet-4-6` like all live turns. The D2 arithmetic is trivially within Sonnet's reach. Only escalate to `claude-opus-4-8` if we add an open-ended "analyze why sales dipped" style question — `[NICE]`, with a spoken "give me a moment…" to cover latency.

## Demo-critical subset

D1 + D2 + D3 in that order, on seeded data with pre-verified numbers. Everything else is depth-on-request for judge Q&A.
