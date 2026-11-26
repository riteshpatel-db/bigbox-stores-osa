# 07 Cost: build to date, unit costs, monthly run cost and ROI
- Command: `uv run python scripts/evidence_cost.py` (SQL on `system.billing.usage` x `system.billing.list_prices`, list price)
- Run at: billing data through 2026-11-26T05:20:00.000Z (usage date 2026-11-26); evidence queried 2026-11-26T07:30:42Z (UTC)
- Workspace: https://fevm-serverless-stable-ritesh.cloud.databricks.com
- UC objects: `system.billing.usage`, `system.billing.list_prices`, `bigbox_fe_bar.ml.backtest_daily`, `bigbox_fe_bar.gold.store_sku_daily`
- Git commit: `3ab00c1`; source sha256 `853a5ea93a34` over src/value/cost_model.py, src/value/cost_assumptions.yaml

## Attribution

Components whose usage carries the tag `project = bigbox-stores-osa` in billing: training job, refresh job (features, score, sync, write-back), data generator and drip, serving endpoint, Lakebase check job, Lakebase project. Without it: SQL warehouse (shared; build queries, KPI header, Genie), Lakeflow pipeline, app, synced-table pipeline. Serverless pipelines have the tag in their settings, but serverless usage takes tags from a usage policy, which this build does not set; the warehouse is shared, and the app's usage arrives with no custom tags. So usage is attributed by resource id (job, pipeline, endpoint, warehouse, app, Lakebase project); the tag alone would catch $6.21 of $183.52 (3%).

## What the build has cost so far

| component | quantity | unit | list $ | of which tagged | days |
|---|---|---|---|---|---|
| SQL warehouse (shared; build queries, KPI header, Genie) | 249.22 | DBU | $174.46 | $0.00 | 2026-10-30 → 2026-11-26 |
| training job | 5.79 | DBU | $2.61 | $2.61 | 2026-11-24 → 2026-11-24 |
| Lakeflow pipeline | 4.97 | DBU | $2.24 | $0.00 | 2026-11-24 → 2026-11-25 |
| refresh job (features, score, sync, write-back) | 4.18 | DBU | $1.88 | $1.88 | 2026-11-24 → 2026-11-25 |
| data generator and drip | 1.38 | DBU | $0.62 | $0.62 | 2026-11-24 → 2026-11-24 |
| app | 0.50 | DBU | $0.48 | $0.00 | 2026-11-25 → 2026-11-25 |
| serving endpoint | 6.26 | DBU | $0.44 | $0.44 | 2026-11-24 → 2026-11-25 |
| Lakebase check job | 0.81 | DBU | $0.36 | $0.36 | 2026-11-25 → 2026-11-25 |
| Lakebase project | 0.66 | DBU + DSU | $0.31 | $0.31 | 2026-11-25 → 2026-11-26 |
| synced-table pipeline | 0.31 | DBU | $0.14 | $0.00 | 2026-11-25 → 2026-11-25 |

Total $183.52. The SQL warehouse is shared and sized Large (not resized: shared); `system.query.history` shows only this build's principals on it since 2026-11-20, so all of it is attributed here, mostly to build-time queries (governance, evidence, Genie scoring).

## Unit costs (measured)

One `bigbox_refresh` run `387755722703731` (2026-11-25T03:06:32Z, tasks pipeline, write_back, features, score, sync):

| part | DBU | list $ |
|---|---|---|
| job tasks (serverless) | 1.140 | $0.51 |
| pipeline update 65f27138-d54f-47a5-91a5-37a3c5396092 | 0.375 | $0.17 |
| synced-table update 3f709f1e-aaa6-4ab1-b4ee-f605b2e57b4b | 0.092 | $0.04 |

= $0.72 per refresh. One `bigbox_ml_train` run `311784219823432` (incl. its repaired attempts): 4.259 DBU, $1.92.

| resource | billed hours | mean DBU / billed hour | busiest hour DBU | busiest hour list $ (used in the model) |
|---|---|---|---|---|
| serving endpoint (Small, scale-to-zero) | 4 | 1.56 | 3.37 | $0.24 |
| SQL warehouse (Large, auto-stop 10 min) | 12 | 20.77 | 40.00 | $28.00 |
| app compute | 2 | 0.25 | 0.49 | $0.46 |

Billed hours include partly used ones (auto-stop, scale-to-zero, the app stopped after its test), which pull the mean down; the monthly model assumes continuous use while up, so it uses the busiest hour.

Lakebase project: $0.31 over 27.3 h observed = $0.27 per day (compute scales to zero after 5 idle minutes; storage).

## Monthly run cost (modelled)

Assumptions (`src/value/cost_assumptions.yaml`): days_per_month 30.42, refresh_runs_per_day 96, training_runs_per_month 4, endpoint_hours_per_day 12, warehouse_hours_per_day 12, app_hours_per_day 24, scale_data_costs_with_revenue True. Company scale applies the value model's revenue factor x3.56 to refresh and training only.

| component | modelled slice ($/month) | company scale ($/month) |
|---|---|---|
| refresh | $2,112 | $7,524 |
| training | $7.67 | $27.31 |
| endpoint | $86.08 | $86.08 |
| warehouse | $10,221 | $10,221 |
| app | $338.79 | $338.79 |
| lakebase | $8.23 | $8.23 |
| total | $12,774 | $18,206 |

Per 15-minute refresh: $0.72 at the modelled slice, $2.58 at company scale.

## ROI

Annual value $10,988,206 (value model, ML policy at service level 0.95, 50% realisation, `03b_backtest_value.md`) vs annual run cost $218,468 at company scale: net $10,769,738, 50 $ of value per $ of run cost. Not included: build effort, existing platform costs, and storage outside the Lakebase project.
