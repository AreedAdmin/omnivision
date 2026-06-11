# 06 — Persona: Operations Worker (Floor Mode)

The floor worker runs the WMS by voice: hands full, eyes on shelves, no terminal. Channel A (in-app push-to-talk), persona `ops`.

## Workflows

### W1 — Stock variance logging (demo beat #1)

> **Worker:** "I've calculated a variance at aisle four, bin twelve, shelf two — basmati rice, I count eight."
>
> 1. `locate_product("basmati rice")` → resolves product; agent reads system qty at that location via `log_variance` pre-check.
> 2. **Read-back:** *"Basmati rice at aisle 4, bin 12, shelf 2 — system says twelve, you counted eight, variance minus four. Shall I log that?"*
> 3. **Worker:** "Yes." → `log_variance(...)` writes the row, flags it (|−4| ≥ threshold 3).
> 4. **Agent:** *"Logged and flagged for review."*

Edge handling:
- Location doesn't hold that product → *"I don't show basmati rice at that location — I have it at aisle 4 bin 12 and aisle 2 bin 3. Which one are you at?"*
- Counted == system → still loggable as a confirmed count (write with delta 0, not flagged): *"That matches the system — recorded as a clean count."*

### W2 — Product location lookup

> **Worker:** "Where is product X stored?" / "Where do we keep olive oil?"
>
> `locate_product` → *"Olive oil one liter is at aisle 2, bin 3, shelf 1 — forty units — and aisle 5, bin 1, shelf 2 — twelve units."*

- Multiple fuzzy matches → ask once: *"I have olive oil one liter and olive oil five hundred mil — which one?"*
- No match → *"I can't find that product — can you read me the SKU from the label?"* (SKU path must work: spoken SKUs come through STT as digits/words; normalize in the tool.)

### W3 — Expired / damaged stock disposition (demo beat #2 candidate)

> **Worker:** "I've found six expired units of Greek yoghurt — where do I take them?"
>
> 1. `get_disposition_rule(product, "expired")` → perishable food → disposal zone.
> 2. **Agent:** *"Expired food goes to disposal zone D1. Want me to log six units of Greek yoghurt as expired and update stock?"*
> 3. **Worker:** "Yes." → `log_disposition(...)` writes disposition + decrements inventory + stock_movement.
> 4. **Agent:** *"Done — six units logged as expired, stock updated. Take them to D1."*

Note the ordering: the agent **answers the question first** (where do I take them) — that's the value moment — then offers the write. Never make the worker wait through a logging ceremony to get their answer.

### W4 — Direct stock adjustment

> "Set aisle 1 bin 4 shelf 1 dish soap to twenty units — recount confirmed."
>
> Read-back with old → new qty, confirm, `adjust_stock`. Reason captured verbatim ("recount confirmed").

## Voice UX rules for this persona

- **Locations echo format:** always read back as "aisle N, bin N, shelf N" — fixed order, no abbreviations (STT-friendly and unambiguous).
- **Numbers:** confirm quantities digit-critical values by repeating them; if STT confidence on a number seems off (e.g. "8" vs "80" magnitude jump vs system qty), ask: *"Eight or eighty?"*
- **One write per confirmation.** Never batch multiple writes behind one "yes".
- **Speed of correction:** "no, bin THIRTEEN" mid-read-back → barge-in cancels, agent re-resolves with the corrected slot only.

## Noisy environment (acknowledged, scoped out)

Demo is quiet-room push-to-talk. If judges ask: AssemblyAI's models are strong on noisy audio; deployment-grade floor use adds a directional headset mic — hardware detail, not architecture change. Push-to-talk (vs open mic) is itself a noise-robustness choice.

## Demo-critical subset

W1 (variance) is the scripted demo beat — must be flawless against seeded data. W2 (locate) is the warm-up beat and nearly free to build. W3 is the backup beat if time allows. W4 is `[NICE]`.
