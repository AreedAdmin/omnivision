-- Omnivision seed data — choreographed to match the demo script (see plan/10-demo-plan.md).
-- Idempotent: wipes and re-inserts. Run before every rehearsal ("reset demo").
--
-- ⚠️ MANUAL STEP: set the real demo supplier phone (your teammate's number) below,
--    search for: UPDATE-ME-SUPPLIER-PHONE

set search_path = assemblyai;

-- wipe (order matters for FKs)
truncate call_transcripts, calls, po_events, purchase_orders, suppliers,
         sales, dispositions, variance_logs, stock_movements, inventory,
         locations, products cascade;

-- ============ products ============
insert into products (id, sku, name, category, is_perishable, reorder_point, unit_price) values
  ('a0000000-0000-0000-0000-000000000001', 'RICE-BAS-5KG', 'Basmati Rice 5kg',        'food',     false, 50, 12.50),
  ('a0000000-0000-0000-0000-000000000002', 'OIL-SUN-1L',   'Sunflower Oil 1L',        'food',     false, 50,  4.20),
  ('a0000000-0000-0000-0000-000000000003', 'OIL-OLV-1L',   'Olive Oil 1L',            'food',     false, 30,  9.80),
  ('a0000000-0000-0000-0000-000000000004', 'YOG-GRK-500',  'Greek Yoghurt 500g',      'food',     true,  25,  2.10),
  ('a0000000-0000-0000-0000-000000000005', 'CLN-DSH-750',  'Dish Soap 750ml',         'non-food', false, 30,  1.90),
  ('a0000000-0000-0000-0000-000000000006', 'BAT-AA-8',     'AA Batteries 8-pack',     'non-food', false, 40,  6.50),
  ('a0000000-0000-0000-0000-000000000007', 'OIL-OLV-500',  'Olive Oil 500ml',         'food',     false, 25,  5.90),
  ('a0000000-0000-0000-0000-000000000008', 'TOM-PST-400',  'Tomato Paste 400g',       'food',     false, 40,  1.20),
  ('a0000000-0000-0000-0000-000000000009', 'PPR-TWL-6',    'Paper Towels 6-roll',     'non-food', false, 35,  4.80),
  ('a0000000-0000-0000-0000-000000000010', 'WTR-SPK-12',   'Sparkling Water 12-pack', 'food',     false, 60,  7.40),
  ('a0000000-0000-0000-0000-000000000011', 'FLR-WHT-1KG',  'White Flour 1kg',         'food',     false, 45,  1.60),
  ('a0000000-0000-0000-0000-000000000012', 'SGR-WHT-1KG',  'White Sugar 1kg',         'food',     false, 45,  1.40),
  ('a0000000-0000-0000-0000-000000000013', 'CLN-LDY-2L',   'Laundry Detergent 2L',    'non-food', false, 25,  8.90),
  ('a0000000-0000-0000-0000-000000000014', 'MLK-PWD-900',  'Milk Powder 900g',        'food',     false, 30, 11.20),
  ('a0000000-0000-0000-0000-000000000015', 'HNY-PUR-500',  'Pure Honey 500g',         'food',     false, 20,  9.30);

-- ============ locations ============
insert into locations (id, aisle, bin, shelf, zone) values
  ('b0000000-0000-0000-0000-000000000001', 4, 12, 2, 'storage'),  -- DEMO: variance beat happens here
  ('b0000000-0000-0000-0000-000000000002', 2,  3, 1, 'storage'),
  ('b0000000-0000-0000-0000-000000000003', 5,  1, 2, 'storage'),
  ('b0000000-0000-0000-0000-000000000004', 1,  4, 1, 'storage'),
  ('b0000000-0000-0000-0000-000000000005', 3,  2, 1, 'storage'),
  ('b0000000-0000-0000-0000-000000000006', 2,  1, 1, 'storage'),
  ('b0000000-0000-0000-0000-000000000007', 6,  2, 2, 'storage'),
  ('b0000000-0000-0000-0000-000000000008', 1,  1, 1, 'storage'),
  ('b0000000-0000-0000-0000-000000000009', 4,  1, 1, 'storage'),
  ('b0000000-0000-0000-0000-000000000010', 3,  5, 2, 'storage'),
  ('b0000000-0000-0000-0000-000000000011', 5,  3, 1, 'storage'),
  ('b0000000-0000-0000-0000-000000000012', 6,  4, 1, 'storage'),
  ('b0000000-0000-0000-0000-000000000013', 1,  2, 2, 'storage'),
  ('b0000000-0000-0000-0000-000000000014', 2,  5, 2, 'storage'),
  ('b0000000-0000-0000-0000-000000000015', 3,  1, 2, 'storage'),
  ('b0000000-0000-0000-0000-000000000020', 0,  0, 1, 'disposal'),       -- zone D1
  ('b0000000-0000-0000-0000-000000000021', 0,  0, 2, 'returns_cage'),   -- zone R2
  ('b0000000-0000-0000-0000-000000000022', 0,  1, 1, 'receiving');

-- ============ inventory (demo choreography) ============
insert into inventory (product_id, location_id, qty) values
  -- Basmati rice: variance beat at A4-B12-S2 (system says 12, worker counts 8); total 140
  ('a0000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000001', 12),
  ('a0000000-0000-0000-0000-000000000001', 'b0000000-0000-0000-0000-000000000002', 128),
  -- Sunflower oil: 20 on hand, reorder 50 → LOW STOCK with overdue PO-8841 (manager beat D3)
  ('a0000000-0000-0000-0000-000000000002', 'b0000000-0000-0000-0000-000000000003', 20),
  -- Olive oil 1L in two locations (locate beat shows multi-location answer)
  ('a0000000-0000-0000-0000-000000000003', 'b0000000-0000-0000-0000-000000000004', 40),
  ('a0000000-0000-0000-0000-000000000003', 'b0000000-0000-0000-0000-000000000005', 12),
  ('a0000000-0000-0000-0000-000000000007', 'b0000000-0000-0000-0000-000000000006', 25),
  -- Greek yoghurt (expired-disposition beat W3)
  ('a0000000-0000-0000-0000-000000000004', 'b0000000-0000-0000-0000-000000000007', 30),
  -- Dish soap: 18 on hand, reorder 30 → LOW STOCK (no open PO)
  ('a0000000-0000-0000-0000-000000000005', 'b0000000-0000-0000-0000-000000000008', 18),
  -- AA batteries: 12 on hand, reorder 40 → LOW STOCK (open PO not overdue)
  ('a0000000-0000-0000-0000-000000000006', 'b0000000-0000-0000-0000-000000000009', 12),
  ('a0000000-0000-0000-0000-000000000008', 'b0000000-0000-0000-0000-000000000010', 90),
  ('a0000000-0000-0000-0000-000000000009', 'b0000000-0000-0000-0000-000000000011', 55),
  ('a0000000-0000-0000-0000-000000000010', 'b0000000-0000-0000-0000-000000000012', 110),
  ('a0000000-0000-0000-0000-000000000011', 'b0000000-0000-0000-0000-000000000013', 70),
  ('a0000000-0000-0000-0000-000000000012', 'b0000000-0000-0000-0000-000000000014', 65),
  ('a0000000-0000-0000-0000-000000000013', 'b0000000-0000-0000-0000-000000000015', 32),
  ('a0000000-0000-0000-0000-000000000014', 'b0000000-0000-0000-0000-000000000011', 41),
  ('a0000000-0000-0000-0000-000000000015', 'b0000000-0000-0000-0000-000000000013', 26);

-- ============ suppliers ============
insert into suppliers (id, name, phone, contact_name) values
  -- ⚠️ UPDATE-ME-SUPPLIER-PHONE: replace with your teammate's real number (E.164)
  ('c0000000-0000-0000-0000-000000000001', 'Atlas Trading Co',    '+10000000000', 'Omar'),
  ('c0000000-0000-0000-0000-000000000002', 'GreenFields Produce', '+10000000001', 'Sara'),
  ('c0000000-0000-0000-0000-000000000003', 'Northline Packaging', '+10000000002', 'Dean'),
  ('c0000000-0000-0000-0000-000000000004', 'BlueWave Imports',    '+10000000003', 'Lina');

-- ============ purchase orders ============
insert into purchase_orders (id, po_number, supplier_id, product_id, qty, expected_date, status) values
  -- THE HERO: PO-8841, sunflower oil from Atlas Trading, 6 days overdue
  ('d0000000-0000-0000-0000-000000000001', 'PO-8841', 'c0000000-0000-0000-0000-000000000001',
   'a0000000-0000-0000-0000-000000000002', 200, current_date - 6, 'overdue'),
  ('d0000000-0000-0000-0000-000000000002', 'PO-8852', 'c0000000-0000-0000-0000-000000000001',
   'a0000000-0000-0000-0000-000000000001', 100, current_date + 7, 'open'),
  ('d0000000-0000-0000-0000-000000000003', 'PO-8810', 'c0000000-0000-0000-0000-000000000002',
   'a0000000-0000-0000-0000-000000000004',  60, current_date - 2, 'overdue'),
  ('d0000000-0000-0000-0000-000000000004', 'PO-8790', 'c0000000-0000-0000-0000-000000000003',
   'a0000000-0000-0000-0000-000000000009', 120, current_date - 10, 'received'),
  ('d0000000-0000-0000-0000-000000000005', 'PO-8860', 'c0000000-0000-0000-0000-000000000004',
   'a0000000-0000-0000-0000-000000000006',  80, current_date + 3, 'open');

insert into po_events (po_id, event, detail)
select id, 'created', jsonb_build_object('po_number', po_number) from purchase_orders;

-- ============ sales (deterministic for the manager beat) ============
-- Basmati rice: 9/day last 30 days, 7/day the 30 before → sale-rate answer ≈ "9 a day, up ~30%"
insert into sales (product_id, qty, sold_at)
select 'a0000000-0000-0000-0000-000000000001', 9, d
from generate_series(now() - interval '29 days', now(), interval '1 day') d;
insert into sales (product_id, qty, sold_at)
select 'a0000000-0000-0000-0000-000000000001', 7, d
from generate_series(now() - interval '59 days', now() - interval '30 days', interval '1 day') d;

-- Sunflower oil: 4/day (so "days of cover" on 20 units sounds urgent)
insert into sales (product_id, qty, sold_at)
select 'a0000000-0000-0000-0000-000000000002', 4, d
from generate_series(now() - interval '59 days', now(), interval '1 day') d;

-- Background sales for other products
insert into sales (product_id, qty, sold_at)
select 'a0000000-0000-0000-0000-000000000003', 3, d
from generate_series(now() - interval '59 days', now(), interval '1 day') d;
insert into sales (product_id, qty, sold_at)
select 'a0000000-0000-0000-0000-000000000004', 5, d
from generate_series(now() - interval '59 days', now(), interval '1 day') d;
insert into sales (product_id, qty, sold_at)
select 'a0000000-0000-0000-0000-000000000005', 2, d
from generate_series(now() - interval '59 days', now(), interval '1 day') d;
insert into sales (product_id, qty, sold_at)
select 'a0000000-0000-0000-0000-000000000006', 1, d
from generate_series(now() - interval '59 days', now(), interval '1 day') d;
insert into sales (product_id, qty, sold_at)
select 'a0000000-0000-0000-0000-000000000010', 6, d
from generate_series(now() - interval '59 days', now(), interval '1 day') d;
insert into sales (product_id, qty, sold_at)
select 'a0000000-0000-0000-0000-000000000008', 2, d
from generate_series(now() - interval '59 days', now(), interval '1 day') d;
