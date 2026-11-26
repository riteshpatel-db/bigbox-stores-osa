# 00 Raw data (synthetic generator)
- Command: `./scripts/deploy.sh && databricks bundle run bigbox_generate_data` (job `bigbox_generate_data`, run `367799309166838`)
- Run at: 2026-11-24T04:53:57Z → 2026-11-24T05:04:19Z (UTC)
- Workspace: https://fevm-serverless-stable-ritesh.cloud.databricks.com
- UC objects: `bigbox_fe_bar.raw.landing`, `/Volumes/bigbox_fe_bar/raw/landing`
- Git commit: none yet (first commit pending); source sha256 `dc83a4081880` over src/generator

## Tasks

| task | result | duration |
|---|---|---|
| generate | SUCCESS | 6.5 min |
| determinism_check | SUCCESS | 3.9 min |
| validate | SUCCESS | 2.6 min |

## Output: generate

```text
masters: 100 stores, 300 SKUs, 28005 ranged store-SKU cells, 150000 buyers
  simulated 2025-09-03  (1 s)
  simulated 2025-10-03  (5 s)
  simulated 2025-11-02  (25 s)
  simulated 2025-12-02  (43 s)
  simulated 2026-01-01  (62 s)
  simulated 2026-01-31  (78 s)
  simulated 2026-03-02  (95 s)
  simulated 2026-04-01  (113 s)
  simulated 2026-05-01  (130 s)
  simulated 2026-05-31  (146 s)
  simulated 2026-06-30  (164 s)
  simulated 2026-07-30  (181 s)
  simulated 2026-08-29  (199 s)
  simulated 2026-09-28  (216 s)
  simulated 2026-10-28  (353 s)
done: 3862 files, 1.64 GB in 357 s
```

## Output: determinism_check

```text
masters: 100 stores, 300 SKUs, 28005 ranged store-SKU cells, 150000 buyers
  simulated 2025-09-03  (1 s)
  simulated 2025-10-03  (4 s)
  simulated 2025-11-02  (20 s)
  simulated 2025-12-02  (36 s)
  simulated 2026-01-01  (52 s)
  simulated 2026-01-31  (67 s)
  simulated 2026-03-02  (83 s)
  simulated 2026-04-01  (99 s)
  simulated 2026-05-01  (115 s)
  simulated 2026-05-31  (130 s)
  simulated 2026-06-30  (146 s)
  simulated 2026-07-30  (163 s)
  simulated 2026-08-29  (179 s)
  simulated 2026-09-28  (196 s)
  simulated 2026-10-28  (213 s)
done: 3862 files, 1.64 GB in 214 s
determinism check: 3862 files compared, 0 differ
```

## Output: validate

## Files, bytes and rows per entity

| entity | files | MB | rows (manifest) | rows (Spark) | match | min ts | max ts |
|---|---|---|---|---|---|---|---|
| stores | 1 | 0.0 | 100 | 100 | yes | - | - |
| products | 1 | 0.0 | 300 | 300 | yes | - | - |
| assortment | 1 | 0.1 | 30,000 | 30,000 | yes | - | - |
| buyers | 1 | 4.1 | 150,000 | 150,000 | yes | - | - |
| promotions | 1 | 0.0 | 984 | 984 | yes | 2025-11-28 | 2026-10-07 |
| pos_order_lines | 757 | 608.1 | 35,107,993 | 35,107,993 | yes | 2025-10-01 08:00:09 | 2029-10-28 21:12:31 |
| online_order_lines | 757 | 83.2 | 3,178,135 | 3,178,135 | yes | 2025-10-01 08:00:01 | 2026-10-28 21:59:24 |
| inventory_snapshots | 757 | 707.7 | 152,110,854 | 152,110,854 | yes | 2025-10-01 09:00:00 | 2026-10-28 22:00:00 |
| replenishment_orders | 393 | 34.7 | 2,875,029 | 2,875,029 | yes | 2025-09-17 23:00:00 | 2026-10-28 23:00:00 |
| replenishment_receipts | 393 | 48.4 | 2,838,781 | 2,838,781 | yes | 2025-10-01 06:00:00 | 2026-10-28 06:59:57 |
| write_offs | 393 | 3.4 | 647,441 | 647,441 | yes | 2025-10-01 | 2026-10-28 |
| returns | 392 | 14.2 | 476,587 | 476,587 | yes | 2025-10-02 08:04:17 | 2026-10-28 21:58:53 |

Total rows read by Spark: 197,416,204

## Injected defects (generator manifest)

| defect | entity | injected | must be caught by |
|---|---|---|---|
| online_late | online_order_lines | 31,484 | extract_ts - order_ts beyond the batch window: flagged late |
| online_overship | online_order_lines | 1,495 | expectation shipped_qty <= requested_qty -> drop |
| online_schema_drift_rows | online_order_lines | 1,677,333 | Auto Loader schema evolution / _rescued_data |
| pos_cents_price | pos_order_lines | 3,662 | price-range check: unit_price > 50 x list price -> /100 |
| pos_duplicate | pos_order_lines | 170,668 | silver dedup on line_id (extra copies removed) |
| pos_future_ts | pos_order_lines | 6,985 | expectation event_ts <= extract_ts -> drop |
| pos_late | pos_order_lines | 690,429 | extract_ts - event_ts > 24 h: flagged late, gold recomputed |
| pos_negative_qty | pos_order_lines | 17,415 | expectation quantity > 0 on sale lines -> drop |
| pos_null_price | pos_order_lines | 69,735 | expectation unit_price IS NOT NULL -> quarantine |
| pos_null_sku | pos_order_lines | 52,100 | expectation sku_id IS NOT NULL -> quarantine |
| pos_null_store | pos_order_lines | 52,632 | expectation store_id IS NOT NULL -> quarantine |
| pos_orphan_sku | pos_order_lines | 35,044 | FK expectation sku_id in products -> quarantine |
| pos_test_store | pos_order_lines | 17,580 | FK expectation store_id in stores (test store) -> quarantine |
| receipts_uom_cases | replenishment_receipts | 80,137 | UoM normalisation: CS x case_pack -> EA |

## Censored demand vs ground truth (history, through 2026-09-30)

| measure | value |
|---|---|
| store-SKU-days (history) | 10,080,921 |
| days with >=1 stocked-out trading hour | 7.24% |
| days closing with zero on hand | 7.24% |
| stocked-out share of trading hours (1 - OSA) | 5.69% |
| true demand units | 38,894,312 |
| units served (sold + shipped) | 37,630,559 |
| demand lost to stockouts (units) | 3.25% |
| lost sales at list price ($, ground truth) | 23,828,460 |
| sales at list price ($) | 283,628,145 |
| online fill rate (shipped / requested) | 94.27% |
| perishable shrink (expired / received) | 9.41% |

## How to read this

- `pos_order_lines` max ts in 2029 is the injected `pos_future_ts` defect (event_ts shifted by `future_ts_shift_days`), not a generator bug.
- `replenishment_orders` min ts before 2025-10-01 are open orders raised during the burn-in period and received inside the window; they are emitted so that every receipt has a PO.
- Ground-truth measures are computed by Spark from `_ground_truth/` (history only) and are never visible to the pipeline or the model.
- The source sha256 above covers `src/generator` as it ran here. Afterwards, only `bigbox_gen/drip.py` changed: its first release now starts at the earliest staged batch, not midnight. Generation code is unchanged. The drip run is recorded in `00b_live_drip.md`.
