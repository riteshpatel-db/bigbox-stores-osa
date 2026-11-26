# 03b Backtest and value: incumbent vs ML policy on the 8 held-out weeks
- Command: `databricks bundle run bigbox_ml_train` (run `311784219823432`), then `uv run python scripts/evidence_ml.py` (SQL on the warehouse, registry and serving APIs)
- Run at: 2026-11-24T07:27:52Z → 2026-11-24T08:36:35Z (UTC); evidence queried 2026-11-24T08:43:00Z
- Workspace: https://fevm-serverless-stable-ritesh.cloud.databricks.com
- UC objects: `bigbox_fe_bar.ml.backtest_daily`, `bigbox_fe_bar.gold.store_sku_daily`, `bigbox_fe_bar.ml.demand_lgbm`
- Git commit: none yet (first commit pending); source sha256 `c85c2a625f31` over src/ml, src/value, src/governance/02_ml_tables.sql

Same world: the backtest re-runs the generator's simulation (config sha256 checked against the landing manifest). Over the holdout, the generator's history vs `gold.store_sku_daily`: in-stock 0.909060 vs 0.909060, OSA 0.926274 vs 0.926274, units 6,005,368 vs 5,965,472 (gold excludes quarantined rows).

All policies trade the same true demand from the same start state, with supply and damage draws seeded by day. `history` = the generator's own run; `incumbent` = the same rule replayed (differs from history only by those draws); `ml` = policy (b) at each service level.

| policy | service level | in-stock | OSA | lost units share | lost sales $ | shrink | days of supply | slow DoS | slow OSA | waste $ | avg inventory $ | PO lines |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| history | - | 0.9091 | 0.9263 | 0.0376 | 5,429,948 | 0.1058 | 4.5226 | 12.8738 | 0.8395 | 1,035,706 | 2,357,814 | 414,383 |
| incumbent | - | 0.9094 | 0.9266 | 0.0375 | 5,416,201 | 0.1056 | 4.5183 | 12.8672 | 0.8408 | 1,034,935 | 2,354,586 | 414,753 |
| ml | 0.9 | 0.9132 | 0.9366 | 0.0519 | 4,354,528 | 0.0656 | 3.5137 | 12.7287 | 0.8974 | 634,426 | 2,221,603 | 393,380 |
| ml | 0.95 | 0.9292 | 0.9482 | 0.0407 | 3,588,351 | 0.0698 | 3.8049 | 13.0214 | 0.9131 | 698,819 | 2,463,650 | 395,335 |
| ml | 0.98 | 0.9434 | 0.9582 | 0.0311 | 2,927,470 | 0.0752 | 4.1621 | 13.4476 | 0.9264 | 777,083 | 2,759,090 | 397,131 |

## ML policy (service level 0.95) vs incumbent, against the hypotheses

| measure | incumbent | ML | change | hypothesis |
|---|---|---|---|---|
| lost sales $ | 5,416,201 | 3,588,351 | -33.7% | -20 to -30 % |
| on-shelf availability | 0.9266 | 0.9482 | +2.16 pts | +2 to +4 pts |
| in-stock at close | 0.9094 | 0.9292 | +1.98 pts | - |
| perishable shrink | 0.1056 | 0.0698 | -33.9% | -10 to -20 % |
| days of supply, slow movers | 12.8672 | 13.0214 | +1.2% | down, no OSA loss |
| OSA, slow movers | 0.8408 | 0.9131 | +7.23 pts | no loss |

By segment (incumbent vs ML at 0.95): the shelf-life cap removes most safety stock on fast-moving perishables, which cuts their waste and raises their lost units; slow movers gain the most availability.

| segment | perishable | policy | lost units share | lost sales $ | OSA | days of supply | waste $ | demand units |
|---|---|---|---|---|---|---|---|---|
| other | false | ml | 0.0427 | 1,694,023 | 0.9599 | 3.9779 | 39,935 | 3,357,710 |
| other | false | incumbent | 0.0434 | 2,314,970 | 0.9514 | 4.3428 | 41,437 | 3,357,710 |
| other | true | ml | 0.0286 | 330,590 | 0.9684 | 2.4704 | 481,329 | 2,547,004 |
| other | true | incumbent | 0.008 | 126,308 | 0.9827 | 3.8575 | 822,993 | 2,547,004 |
| slow | false | ml | 0.1156 | 1,532,576 | 0.9131 | 13.4802 | 19,498 | 294,280 |
| slow | false | incumbent | 0.2194 | 2,945,362 | 0.8316 | 13.3674 | 15,016 | 294,280 |
| slow | true | ml | 0.0876 | 31,162 | 0.9127 | 9.8497 | 158,057 | 41,266 |
| slow | true | incumbent | 0.0856 | 29,561 | 0.9153 | 9.8218 | 155,489 | 41,266 |

## Value model (`src/value/value_model.py`, assumptions in `src/value/assumptions.yaml`)

Measured: modelled assortment revenue over 365 days of history $280,727,195 (gold), the holdout deltas above. Assumed: company revenue $1,000,000,000 (scale x3.56), realisation 50%, carrying cost 20%/yr, linear annualisation x6.52 (no seasonality adjustment).

| component (per year, company scale) | $ |
|---|---|
| lost sales recovered (revenue) | 21,219,297 |
| gross margin on recovered sales | 7,125,122 |
| waste avoided (expired + damaged, at cost) | 3,901,935 |
| carrying cost on inventory change | -38,851 |
| **total value (margin + waste + carrying)** | 10,988,206 |

By service level (same assumptions; the configured level is the headline):

| service level | lost sales recovered | margin | waste | carrying | total |
|---|---|---|---|---|---|
| 0.9 | 12,324,834 | 4,045,908 | 4,649,460 | 47,371 | 8,742,738 |
| 0.95 | 21,219,297 | 7,125,122 | 3,901,935 | -38,851 | 10,988,206 |
| 0.98 | 28,891,383 | 9,787,917 | 2,993,372 | -144,091 | 12,637,198 |

Sensitivity of the total ($/yr):

| realisation | revenue $800,000,000 | revenue $1,000,000,000 | revenue $1,200,000,000 |
|---|---|---|---|
| 25% | 4,395,283 | 5,494,103 | 6,592,924 |
| 50% | 8,790,565 | 10,988,206 | 13,185,848 |
| 75% | 13,185,848 | 16,482,309 | 19,778,771 |
| 100% | 17,581,130 | 21,976,413 | 26,371,695 |

Not credited: intraday visibility (the simulator has no backroom or expedited delivery); policy (b) reads history columns observed under the incumbent's stockouts. ROI needs the run cost (evidence/07_cost.md).
