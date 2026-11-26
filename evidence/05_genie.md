# 05 Genie: space, 25 questions scored against reference SQL, 3 runs
- Command: `uv run python src/genie/space.py deploy`, then `uv run python src/genie/score.py --runs 3 --label final`, then `uv run python scripts/evidence_genie.py`
- Run at: 2026-11-25T04:18:32Z → 2026-11-25T04:36:00Z (UTC); evidence written 2026-11-25T04:36:56Z
- Workspace: https://fevm-serverless-stable-ritesh.cloud.databricks.com
- UC objects: `bigbox_fe_bar.gold.inventory_position`, `bigbox_fe_bar.gold.recommendations`, `bigbox_fe_bar.gold.reorder_decisions`, `bigbox_fe_bar.gold.replenishment_fill`, `bigbox_fe_bar.gold.store_sku_daily`, `bigbox_fe_bar.serving.availability_kpis`, `bigbox_fe_bar.serving.sales_kpis`
- Git commit: none yet (first commit pending); source sha256 `710317e78b64` over src/genie; raw runs in `results/genie/final_run1..3.json`

## Space

"Bigbox Stores - Store Ops" (`01f1e884bece1d39994e9ba5a98ab5f1`), warehouse `d5b43df809d40fcf`. Configuration exported to `src/genie/space.json` (built from `space.yaml` + `kpi_definitions.md` and recreated by `src/genie/space.py deploy`): 7 data sources (2 metric views first, gold tables for queue, decisions, supplier fill and drill-down), 75 column synonyms, 3 join specs, 8 example SQL, 5 sample questions, instructions of 5,062 characters ending with the KPI definitions table verbatim (26 KPIs). None of the 25 scored questions is an example SQL.

Scoring (`src/genie/score.py`): a new conversation per question and run through the Conversation API; Genie's SQL and the reference SQL run on the same warehouse; results are compared order-insensitively, numbers within 0.5 %, extra Genie columns allowed, same row count required.

## Accuracy

| run | passed | accuracy |
|---|---|---|
| `v0`: data sources only (ablation) | 16/25 | 64% |
| `v1`: full configuration, first run | 25/25 | 100% |
| run 1 | 25/25 | 100% |
| run 2 | 25/25 | 100% |
| run 3 | 25/25 | 100% |

## Per question

| id | question | run 1 | run 2 | run 3 | reason when failed |
|---|---|---|---|---|---|
| q01 | What was on-shelf availability by region last week? | pass | pass | pass |  |
| q02 | Which stores lost the most sales to stockouts last week and why? Show the top 5. | pass | pass | pass |  |
| q03 | What was the in-stock rate for each store format in September 2026? | pass | pass | pass |  |
| q04 | Which perishable category had the highest shrink last quarter? | pass | pass | pass |  |
| q05 | What was the forecast WAPE in each of the last three full months? | pass | pass | pass |  |
| q06 | How much did we lose to stockouts in dollars by category last month? | pass | pass | pass |  |
| q07 | Which region had the lowest online fill rate last month? | pass | pass | pass |  |
| q08 | How many OOS hours did store S042 have last week? | pass | pass | pass |  |
| q09 | What were the days of supply by category last week? | pass | pass | pass |  |
| q10 | What were inventory turns by region last quarter? | pass | pass | pass |  |
| q11 | What was total revenue by channel last month? | pass | pass | pass |  |
| q12 | What was the average order value in each region last week? | pass | pass | pass |  |
| q13 | What were the top 5 categories by units sold in September 2026? | pass | pass | pass |  |
| q14 | What was the item return rate for Electronics last quarter? | pass | pass | pass |  |
| q15 | How many unique buyers ordered online last month? | pass | pass | pass |  |
| q16 | Which 3 categories had the highest average discount rate last quarter? | pass | pass | pass |  |
| q17 | Which 5 suppliers had the worst replenishment fill rate on orders due last month? | pass | pass | pass |  |
| q18 | How many purchase-order lines due last month arrived late? | pass | pass | pass |  |
| q19 | How many store-SKUs are at stockout risk in tonight's reorder queue? | pass | pass | pass |  |
| q20 | Which 10 store-SKUs in tonight's queue have the highest expected lost sales? | pass | pass | pass |  |
| q21 | What is the total cost of tonight's recommended orders by region? | pass | pass | pass |  |
| q22 | How many overstock items are in tonight's queue for each category? | pass | pass | pass |  |
| q23 | How many reorder decisions were approved, overridden and rejected? | pass | pass | pass |  |
| q24 | For overridden decisions, how many units did planners add in total compared with the recommendation? | pass | pass | pass |  |
| q25 | How many store-SKUs are out of stock right now? | pass | pass | pass |  |

Flipped between runs: none. Passed in all 3 runs: 25 of 25.

`v0`, data sources only (ablation), failed 9: q05 no Genie column matches reference column 'month'; q06 no Genie column matches reference column 'lost_sales'; q08 no Genie column matches reference column 'stockout_hours'; q11 no Genie column matches reference column 'total_revenue'; q12 row count 0 vs reference 4; q15 no Genie column matches reference column 'unique_buyers'; q17 no Genie column matches reference column 'supplier_id'; q18 no Genie column matches reference column 'late_lines'; q19 no Genie column matches reference column 'stockout_risk_items'. Of these, 8 anchored relative dates on current_date() (after the data ends) instead of the latest date in the data.

Caveat: the 25 questions were written with the instructions, so 100 % shows the space answers its intended questions consistently, not that it generalises to any question; the ablation shows how much of that comes from the curation.

## Worked conversation (run 1, `q02`, pass, 20.1 s)

**Question:** Which stores lost the most sales to stockouts last week and why? Show the top 5.

**Genie's SQL:**

```sql
WITH `store_lost_sales` AS (
  SELECT
    `store_id`,
    MEASURE(`lost_sales`) AS `lost_sales`,
    MEASURE(`stockout_hours`) AS `stockout_hours`,
    MEASURE(`on_shelf_availability`) AS `on_shelf_availability`,
    RANK() OVER (ORDER BY MEASURE(`lost_sales`) DESC) AS `lost_sales_rank`
  FROM `bigbox_fe_bar`.`serving`.`availability_kpis`
  WHERE `store_id` IS NOT NULL
    AND `date` BETWEEN '2026-09-21' AND '2026-09-27'
  GROUP BY ALL
),
`top_stores` AS (
  SELECT
    `store_id`,
    `lost_sales`,
    `stockout_hours`,
    `on_shelf_availability`,
    `lost_sales_rank`
  FROM `store_lost_sales`
  WHERE `lost_sales_rank` <= 5
),
`store_drivers` AS (
  SELECT
    `store_id`,
    SUM(`received_units`) AS `received_units`,
    SUM(CASE WHEN `on_promo` THEN `units_sold` ELSE 0 END) AS `promo_units_sold`,
    SUM(`stockout_hours`) AS `driver_stockout_hours`,
    SUM(CASE WHEN `received_units` = 0 THEN `stockout_hours` ELSE 0 END) AS `stockout_hours_no_receipts`
  FROM `bigbox_fe_bar`.`gold`.`store_sku_daily`
  WHERE `store_id` IS NOT NULL
    AND `date` BETWEEN '2026-09-21' AND '2026-09-27'
  GROUP BY `store_id`
)
SELECT
  `t`.`store_id`,
  `t`.`lost_sales`,
  `t`.`stockout_hours`,
  `t`.`on_shelf_availability`,
  `d`.`received_units`,
  `d`.`promo_units_sold`,
  `d`.`stockout_hours_no_receipts`
FROM `top_stores` `t`
LEFT JOIN `store_drivers` `d`
  ON `t`.`store_id` = `d`.`store_id`
ORDER BY `t`.`lost_sales_rank` ASC, `t`.`store_id` ASC
```

**Result:**

| store_id | lost_sales | stockout_hours | on_shelf_availability | received_units | promo_units_sold | stockout_hours_no_receipts |
|---|---|---|---|---|---|---|
| S065 | 11984.912484643923 | 2090 | 0.9289115646258503 | 18077 | 0 | 2007 |
| S075 | 10169.179291691686 | 2215 | 0.9246598639455782 | 12699 | 0 | 2156 |
| S054 | 9421.4097669847 | 2027 | 0.9310544217687075 | 13189 | 0 | 1986 |
| S067 | 9126.535588425515 | 2142 | 0.9271428571428572 | 13332 | 0 | 2094 |
| S068 | 8576.44441611174 | 2176 | 0.9259863945578232 | 12191 | 0 | 2133 |

**Genie's answer text:** Last week, the **top 5 stores** for sales lost to stockouts were: - **S065** — **11,984.91** lost sales, **2,090** stockout hours, on-shelf availability **0.9289** - **S075** — **10,169.18** lost sales, **2,215** stockout hours, on-shelf availability **0.9247** - **S054** — **9,421.41** lost sales, **2,027** stockout hours, on-shelf availability **0.9311** - **S067** — **9,126.54** lost sales, **2,142** stockout hours, on-shelf availability **0.9271** - **S068** — **8,576.44** lost sales, **2,176** stockout hours, on-shelf availability **0.9260**  Across all 5 stores, the main visible driver was that nearly all stockout time happened on days with **no receipts** (about **1,986 to 2,156** hours), while **promo-driven demand was 0** for every store.

Verdict against the reference SQL: match.
