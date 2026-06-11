-- Omnivision schema. Run in the Supabase SQL editor.
-- Tables live in the dedicated "assemblyai" schema (per project convention).
--
-- MANUAL STEP after running this file:
--   Dashboard → Settings → API → "Exposed schemas" → add: assemblyai
--   (otherwise PostgREST / supabase-js cannot see these tables)

create schema if not exists assemblyai;
set search_path = assemblyai;

-- ============ catalog & locations ============
create table if not exists products (
  id            uuid primary key default gen_random_uuid(),
  sku           text unique not null,
  name          text not null,
  category      text not null,              -- 'food' | 'non-food'
  is_perishable boolean not null default false,
  reorder_point int not null default 20,
  unit_price    numeric(10,2) not null
);

create table if not exists locations (
  id      uuid primary key default gen_random_uuid(),
  aisle   int not null,
  bin     int not null,
  shelf   int not null,
  zone    text not null default 'storage',  -- storage | disposal | returns_cage | receiving
  unique (aisle, bin, shelf)
);

create table if not exists inventory (
  id          uuid primary key default gen_random_uuid(),
  product_id  uuid not null references products(id),
  location_id uuid not null references locations(id),
  qty         int not null check (qty >= 0),
  unique (product_id, location_id)
);

-- ============ floor operations ============
create table if not exists stock_movements (
  id          uuid primary key default gen_random_uuid(),
  product_id  uuid not null references products(id),
  location_id uuid references locations(id),
  delta       int not null,
  reason      text not null,                -- adjustment | disposition | receiving | sale
  source      text not null,                -- voice_ops | voice_manager | supplier_call | seed
  session_ref text,
  created_at  timestamptz not null default now()
);

create table if not exists variance_logs (
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

create table if not exists dispositions (
  id            uuid primary key default gen_random_uuid(),
  product_id    uuid not null references products(id),
  qty           int not null check (qty > 0),
  reason        text not null,              -- expired | damaged
  from_location uuid references locations(id),
  to_zone       text not null,
  session_ref   text,
  created_at    timestamptz not null default now()
);

-- ============ purchasing / inbound ============
create table if not exists suppliers (
  id           uuid primary key default gen_random_uuid(),
  name         text not null,
  phone        text not null,
  contact_name text
);

create table if not exists purchase_orders (
  id            uuid primary key default gen_random_uuid(),
  po_number     text unique not null,
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

create table if not exists po_events (
  id         uuid primary key default gen_random_uuid(),
  po_id      uuid not null references purchase_orders(id),
  event      text not null,  -- created | chase_started | call_completed | call_failed | status_changed | flagged_review
  detail     jsonb,
  created_at timestamptz not null default now()
);

-- ============ calls & transcripts ============
create table if not exists calls (
  id          uuid primary key default gen_random_uuid(),
  po_id       uuid references purchase_orders(id),
  supplier_id uuid references suppliers(id),
  twilio_sid  text,
  direction   text not null default 'outbound',
  outcome     text,           -- completed | no_answer | busy | failed | incomplete
  started_at  timestamptz not null default now(),
  ended_at    timestamptz,
  extraction  jsonb
);

create table if not exists call_transcripts (
  id      uuid primary key default gen_random_uuid(),
  call_id uuid not null references calls(id),
  turn_no int not null,
  speaker text not null,      -- agent | supplier
  text    text not null,
  ts      timestamptz not null default now()
);

-- ============ sales (manager analytics) ============
create table if not exists sales (
  id         uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id),
  qty        int not null,
  sold_at    timestamptz not null
);

-- indexes
create index if not exists idx_inventory_product on inventory (product_id);
create index if not exists idx_sales_product_time on sales (product_id, sold_at);
create index if not exists idx_po_status on purchase_orders (status);
create index if not exists idx_transcripts_call on call_transcripts (call_id, turn_no);

-- ============ realtime ============
-- Dashboard subscribes to live changes on these tables.
do $$
begin
  alter publication supabase_realtime add table assemblyai.purchase_orders;
exception when duplicate_object then null; end $$;
do $$
begin
  alter publication supabase_realtime add table assemblyai.calls;
exception when duplicate_object then null; end $$;
do $$
begin
  alter publication supabase_realtime add table assemblyai.call_transcripts;
exception when duplicate_object then null; end $$;
do $$
begin
  alter publication supabase_realtime add table assemblyai.variance_logs;
exception when duplicate_object then null; end $$;
do $$
begin
  alter publication supabase_realtime add table assemblyai.dispositions;
exception when duplicate_object then null; end $$;

-- Hackathon-simple grants: full access for anon/authenticated via PostgREST
-- (no RLS — do NOT ship this to production)
grant usage on schema assemblyai to anon, authenticated, service_role;
grant all on all tables in schema assemblyai to anon, authenticated, service_role;
alter default privileges in schema assemblyai grant all on tables to anon, authenticated, service_role;
