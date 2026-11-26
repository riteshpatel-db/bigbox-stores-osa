# 02 Unity Catalog: personas, grants, row filter, column mask, metric views
- Command: `uv run python scripts/evidence_governance.py` (SQL statements on warehouse `d5b43df809d40fcf`, each persona authenticated with its own CLI profile)
- Run at: 2026-11-25T03:53:15Z
- Workspace: https://fevm-serverless-stable-ritesh.cloud.databricks.com
- UC objects: `bigbox_fe_bar.serving.region_access`, `bigbox_fe_bar.serving.region_allowed`, `bigbox_fe_bar.serving.mask_pii`, `bigbox_fe_bar.serving.sales_lines`, `bigbox_fe_bar.serving.sales_kpis`, `bigbox_fe_bar.serving.availability_kpis`, `bigbox_fe_bar.gold.*`, `bigbox_fe_bar.silver.buyers`
- Git commit: none yet (first commit pending); source in `src/governance/`, `src/pipeline/`

## Personas (each query below ran under this identity)

| CLI profile | current_user() | persona | regions | PII cleartext |
|---|---|---|---|---|
| owner | `ritesh.patel@databricks.com` | data owner (pipeline identity) | * | true |
| bigbox-sp-ops-director | `bca34f6d-2c4f-44de-a3fd-9dbcd50d3de2` | Director of Operations | * | false |
| bigbox-sp-region-east | `3c86153e-fa92-42a9-8954-3fd9fba0af46` | Regional manager, East | EAST | false |
| bigbox-sp-analyst | `7043dc63-81b4-4245-82e2-29a7cf6c0da5` | Analyst | * | false |

## Grants per persona (information_schema privileges)

| persona | catalog | schemas | tables / views |
|---|---|---|---|
| bigbox-sp-ops-director | bigbox_fe_bar (use catalog) | gold (use schema), serving (use schema), silver (use schema) | gold.forecast (select), gold.inventory_position (select), gold.kpi_store_daily (select), gold.online_fill (select), gold.recommendations (select), gold.reorder_decisions (select), gold.replenishment_fill (select), gold.store_sku_daily (select), serving.availability_kpis (select), serving.sales_kpis (select), serving.sales_lines (select), silver.buyers (select) |
| bigbox-sp-region-east | bigbox_fe_bar (use catalog) | gold (use schema), serving (use schema) | gold.forecast (select), gold.inventory_position (select), gold.kpi_store_daily (select), gold.online_fill (select), gold.reorder_decisions (select), gold.replenishment_fill (select), gold.store_sku_daily (select), serving.availability_kpis (select), serving.sales_kpis (select), serving.sales_lines (select) |
| bigbox-sp-analyst | bigbox_fe_bar (use catalog) | gold (use schema), serving (use schema) | gold.forecast (select), gold.inventory_position (select), gold.kpi_store_daily (select), gold.online_fill (select), gold.recommendations (select), gold.reorder_decisions (select), gold.replenishment_fill (select), gold.store_sku_daily (select), serving.availability_kpis (select), serving.sales_kpis (select), serving.sales_lines (select) |

Grants on pipeline-internal `__materialization_*` tables omitted above: 0. Gold is granted table by table, so the unfiltered `gold.recommendations` (synced to Lakebase, where UC row filters don't apply) is not granted to the East persona.

## The same queries, run as each identity

**A. gold.kpi_store_daily rows by region (row filter)**

```sql
SELECT region, count(*) FROM bigbox_fe_bar.gold.kpi_store_daily GROUP BY 1 ORDER BY 1
```

| identity | result |
|---|---|
| owner | CENTRAL 9,150; EAST 9,150; SOUTH 9,150; WEST 9,150 |
| bigbox-sp-ops-director | CENTRAL 9,150; EAST 9,150; SOUTH 9,150; WEST 9,150 |
| bigbox-sp-region-east | EAST 9,150 |
| bigbox-sp-analyst | CENTRAL 9,150; EAST 9,150; SOUTH 9,150; WEST 9,150 |

**B. serving.sales_kpis units_sold by region, 2026-09 (metric view)**

```sql
SELECT region, MEASURE(units_sold) FROM bigbox_fe_bar.serving.sales_kpis WHERE sale_month = DATE'2026-09-01' GROUP BY ALL ORDER BY 1
```

| identity | result |
|---|---|
| owner | CENTRAL 836,405; EAST 756,772; SOUTH 736,388; WEST 805,305 |
| bigbox-sp-ops-director | CENTRAL 836,405; EAST 756,772; SOUTH 736,388; WEST 805,305 |
| bigbox-sp-region-east | EAST 756,772 |
| bigbox-sp-analyst | CENTRAL 836,405; EAST 756,772; SOUTH 736,388; WEST 805,305 |

**C. serving.availability_kpis in_stock_pct by region, 2026-09 (metric view on filtered gold)**

```sql
SELECT region, round(MEASURE(in_stock_pct), 4) FROM bigbox_fe_bar.serving.availability_kpis WHERE month = DATE'2026-09-01' GROUP BY ALL ORDER BY 1
```

| identity | result |
|---|---|
| owner | CENTRAL 0.915; EAST 0.9144; SOUTH 0.9137; WEST 0.9157 |
| bigbox-sp-ops-director | CENTRAL 0.915; EAST 0.9144; SOUTH 0.9137; WEST 0.9157 |
| bigbox-sp-region-east | EAST 0.9144 |
| bigbox-sp-analyst | CENTRAL 0.915; EAST 0.9144; SOUTH 0.9137; WEST 0.9157 |

**D. silver.buyers first row (column mask)**

```sql
SELECT buyer_id, first_name, last_name, email, phone FROM bigbox_fe_bar.silver.buyers ORDER BY buyer_id LIMIT 1
```

| identity | result |
|---|---|
| owner | B0000001 / Avery / Garcia / avery.garcia1@example.com / +1-555-245-0905 |
| bigbox-sp-ops-director | B0000001 / A*** / G*** / a***@example.com / ***-***-0905 |
| bigbox-sp-region-east | DENIED: `INSUFFICIENT_PERMISSIONS` |
| bigbox-sp-analyst | DENIED: `INSUFFICIENT_PERMISSIONS` |

**E. serving.region_access (mapping table, owner only)**

```sql
SELECT count(*) FROM bigbox_fe_bar.serving.region_access
```

| identity | result |
|---|---|
| owner | 4 |
| bigbox-sp-ops-director | DENIED: `INSUFFICIENT_PERMISSIONS` |
| bigbox-sp-region-east | DENIED: `INSUFFICIENT_PERMISSIONS` |
| bigbox-sp-analyst | DENIED: `INSUFFICIENT_PERMISSIONS` |

**F. silver.pos_order_lines (not granted to personas)**

```sql
SELECT count(*) FROM bigbox_fe_bar.silver.pos_order_lines
```

| identity | result |
|---|---|
| owner | 32,202,795 |
| bigbox-sp-ops-director | DENIED: `INSUFFICIENT_PERMISSIONS` |
| bigbox-sp-region-east | DENIED: `INSUFFICIENT_PERMISSIONS` |
| bigbox-sp-analyst | DENIED: `INSUFFICIENT_PERMISSIONS` |

**G. gold.forecast rows by region (stage-C table, row filter declared in its DDL)**

```sql
SELECT region, count(*) FROM bigbox_fe_bar.gold.forecast GROUP BY 1 ORDER BY 1
```

| identity | result |
|---|---|
| owner | CENTRAL 2,557,632; EAST 2,496,358; SOUTH 2,520,852; WEST 2,534,084 |
| bigbox-sp-ops-director | CENTRAL 2,557,632; EAST 2,496,358; SOUTH 2,520,852; WEST 2,534,084 |
| bigbox-sp-region-east | EAST 2,496,358 |
| bigbox-sp-analyst | CENTRAL 2,557,632; EAST 2,496,358; SOUTH 2,520,852; WEST 2,534,084 |

**H. gold.recommendations (no row filter, synced to Lakebase: all-region personas only)**

```sql
SELECT count(*) FROM bigbox_fe_bar.gold.recommendations
```

| identity | result |
|---|---|
| owner | 28,005 |
| bigbox-sp-ops-director | 28,005 |
| bigbox-sp-region-east | DENIED: `INSUFFICIENT_PERMISSIONS` |
| bigbox-sp-analyst | 28,005 |

## Row filters and column masks attached (information_schema)

| table | function | column(s) |
|---|---|---|
| gold.forecast | `bigbox_fe_bar.serving.region_allowed` | region |
| gold.inventory_position | `bigbox_fe_bar.serving.region_allowed` | region |
| gold.kpi_store_daily | `bigbox_fe_bar.serving.region_allowed` | region |
| gold.reorder_decisions | `bigbox_fe_bar.serving.region_allowed` | region |
| gold.store_sku_daily | `bigbox_fe_bar.serving.region_allowed` | region |
| silver.buyers | `bigbox_fe_bar.serving.mask_pii` | email |
| silver.buyers | `bigbox_fe_bar.serving.mask_pii` | first_name |
| silver.buyers | `bigbox_fe_bar.serving.mask_pii` | last_name |
| silver.buyers | `bigbox_fe_bar.serving.mask_pii` | phone |

## Metric views vs hand-written SQL (2026-09, as owner)

**serving.sales_kpis**

| region | units_sold (metric view / hand SQL) | total_revenue (metric view / hand SQL) | avg_order_value (metric view / hand SQL) | item_return_rate (metric view / hand SQL) | match |
|---|---|---|---|---|---|
| CENTRAL | 836,405.0000 / 836,405.0000 | 6,222,710.7100 / 6,222,710.7100 | 19.4757 / 19.4757 | 0.0094 / 0.0094 | yes |
| EAST | 756,772.0000 / 756,772.0000 | 5,666,110.9200 / 5,666,110.9200 | 19.5338 / 19.5338 | 0.0091 / 0.0091 | yes |
| SOUTH | 736,388.0000 / 736,388.0000 | 5,481,966.3700 / 5,481,966.3700 | 19.3313 / 19.3313 | 0.0093 / 0.0093 | yes |
| WEST | 805,305.0000 / 805,305.0000 | 5,978,269.7700 / 5,978,269.7700 | 19.4102 / 19.4102 | 0.0092 / 0.0092 | yes |

**serving.availability_kpis**

| region | in_stock_pct (metric view / hand SQL) | on_shelf_availability (metric view / hand SQL) | shrink_pct (metric view / hand SQL) | days_of_supply (metric view / hand SQL) | match |
|---|---|---|---|---|---|
| CENTRAL | 0.9150 / 0.9150 | 0.9310 / 0.9310 | 0.1053 / 0.1053 | 4.6214 / 4.6214 | yes |
| EAST | 0.9144 / 0.9144 | 0.9298 / 0.9298 | 0.1136 / 0.1136 | 4.8028 / 4.8028 | yes |
| SOUTH | 0.9137 / 0.9137 | 0.9296 / 0.9296 | 0.1111 / 0.1111 | 4.7908 / 4.7908 | yes |
| WEST | 0.9157 / 0.9157 | 0.9315 / 0.9315 | 0.1067 / 0.1067 | 4.6760 / 4.6760 | yes |
