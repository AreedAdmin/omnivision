# 05 — Data Model (Supabase)

Supabase Postgres is the system of record. Schema below is `supabase/schema.sql`; seed plan at the bottom is `supabase/seed.sql`.

## Schema

```sql
-- ============ catalog & locations ============
create table products (
  id            uuid primary key default gen_random_uuid(),
  sku           text unique not null,
  name          text not null,
  category      text not null,              -- e.g. 'food', 'non-food'
  is_perishable boolean not null default false,
  reorder_point int not null default 20,
  unit_price    numeric(10,2) not null
);

create table locations (
  id      uuid primary key default gen_random_uuid(),
  aisle   int not null,
  bin     int not null,
  shelf   int not null,
  zone    text not null default 'storage',  -- storage | disposal | returns_cage | receiving
  unique (aisle, bin, shelf)
);

create table inventory (
  id          uuid primary key default gen_random_uuid(),
  product_id  uuid not null references products(id),
  location_id uuid not null references locations(id),
  qty         int not null check (qty >= 0),
  unique (product_id, location_id)
);

-- ============ floor operations ============
create table stock_movements (
  id          uuid primary key default gen_random_uuid(),
  product_id  uuid not null references products(id),
  location_id uuid references locations(id),
  delta       int not null,
  reason      text not null,                -- adjustment | disposition | receiving | sale
  source      text not null,                -- voice_ops | voice_manager | supplier_call | seed
  session_ref text,                         -- ws session or call id
  created_at  timestamptz not null default now()
);

create table variance_logs (
  id          uuid primary key default gen_random_uuid(),
  product_id  uuid not null references products(id),
  location_id uuid not null references locations(id),
  system_qty  int not null,
  counted_qty int not null,
  delta       int generated always as (counted_qty - system_qty) stored,
  flagged     boolean not null default false,
  status      text not null default 'open', -- open | reviewed | resolved
  session_ref text,
  created_at  timestamptz not null default now()
);

create table dispositions (
  id            uuid primary key default gen_random_uuid(),
  product_id    uuid not null references products(id),
  qty           int not null check (qty > 0),
  reason        text not null,              -- expired | damaged
  from_location uuid references locations(id),
  to_zone       text not null,              -- e.g. 'disposal' / 'returns_cage'
  session_ref   text,
  created_at    timestamptz not null default now()
);

-- ============ purchasing / inbound ============
create table suppliers (
  id    uuid primary key default gen_random_uuid(),
  name  text not null,
  phone text not null,                      -- DEMO: teammate's number
  contact_name text
);

create table purchase_orders (
  id            uuid primary key default gen_random_uuid(),
  po_number     text unique not null,       -- e.g. 'PO-8841'
  supplier_id   uuid not null references suppliers(id),
  product_id    uuid not null references products(id),
  qty           int not null,
  expected_date date not null,
  status        text not null default 'open',
    -- open | overdue | chasing | confirmed_on_time | delayed | shipped | received | needs_review
  eta_date      date,
  delay_reason  text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create table po_events (
  id        uuid primary key default gen_random_uuid(),
  po_id     uuid not null references purchase_orders(id),
  event     text not null,                  -- created | chase_started | call_completed | call_failed | status_changed | flagged_review
  detail    jsonb,
  created_at timestamptz not null default now()
);

-- ============ calls & transcripts ============
create table calls (
  id          uuid primary key default gen_random_uuid(),
  po_id       uuid references purchase_orders(id),
  supplier_id uuid references suppliers(id),
  twilio_sid  text,
  direction   text not null default 'outbound',
  outcome     text,                         -- completed | no_answer | busy | failed | incomplete
  started_at  timestamptz not null default now(),
  ended_at    timestamptz,
  extraction  jsonb                          -- the Opus PoCallExtraction result
);

create table call_transcripts (
  id        uuid primary key default gen_random_uuid(),
  call_id   uuid not null references calls(id),
  turn_no   int not null,
  speaker   text not null,                  -- agent | supplier
  text      text not null,
  ts        timestamptz not null default now()
);

-- ============ sales (for manager analytics) ============
create table sales (
  id         uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id),
  qty        int not null,
  sold_at    timestamptz not null
);

-- helpful indexes
create index on inventory (product_id);
create index on sales (product_id, sold_at);
create index on purchase_orders (status);
create index on call_transcripts (call_id, turn_no);
```

Enable **Supabase Realtime** on `purchase_orders`, `calls`, and `variance_logs` — the dashboard subscribes so PO cards flip live during the demo.

RLS: keep it simple for the hackathon — service-role key on the server, anon key with read-only policies for the dashboard.

## Disposition rules (config, not table — hardcode in `tools/ops.py`)

| reason | category | to_zone | spoken rule |
|---|---|---|---|
| expired | food | disposal | "Take them to disposal zone D1." |
| expired | non-food | returns_cage | "Take them to the returns cage, R2." |
| damaged | any | returns_cage | "Returns cage R2 — tag them as damaged." |

## Seed data plan (`seed.sql`)

Realistic enough that every demo utterance has a satisfying answer:

- **~25 products** across food/non-food, recognizable names (rice 5kg, olive oil 1L, dish soap, AA batteries…), varied prices and reorder points; 4–5 perishables.
- **~60 locations**: aisles 1–6, bins 1–5, shelves 1–2, plus zones `disposal`, `returns_cage`, `receiving`.
- **Inventory**: every product in 1–3 locations; include a few below reorder point (feeds `low_stock_report`), and one with an intentional "wrong" qty for the variance demo (system says 12 where the script counts 8).
- **~5 suppliers** — one is "Atlas Trading Co." with the **teammate's phone number** for the live call.
- **~10 POs**: mix of open/received; **2–3 overdue** including the hero `PO-8841` (Atlas Trading, product the manager also asks about — ties the personas together in one narrative).
- **Sales**: 60 days of randomized rows weighted so `top_movers` and `get_sale_rate` produce clean, speakable numbers.

## Demo data choreography (important)

Seed values are chosen so the **demo script numbers are predictable**: the variance utterance ("counted 8, system says 12") matches a seeded row; the manager's "stock of basmati rice?" returns a round, speakable total; PO-8841 is 6 days overdue from Atlas Trading. Keep a `seed-reset.sql` (or a `make reset-demo` task) that restores the exact pre-demo state in one command — run it before every rehearsal and before going on stage.
