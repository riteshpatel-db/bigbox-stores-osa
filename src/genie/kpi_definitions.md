<!-- BUILD_PROMPT section 3 KPI definitions, verbatim. Loaded into the Genie space instructions by src/genie/space.py. -->
| KPI | Exact definition |
|---|---|
| `units_sold` | Σ `quantity` on sale lines (POS + online fulfilled), excluding returns |
| `item_revenue` | Σ `quantity × unit_price − discount_amount` on sale lines |
| `total_revenue` | `item_revenue` + Σ online `delivery_fee` |
| `total_orders` | COUNT DISTINCT `order_id` (one POS basket = one order) |
| `avg_order_value` | `total_revenue / total_orders` |
| `avg_discount` | Σ `discount_amount` / Σ `quantity × unit_price` (revenue-weighted rate) |
| `unique_buyers` | COUNT DISTINCT non-null `buyer_id` (anonymous POS baskets excluded) |
| `items_returned` | Σ `quantity` on return lines, attributed to the **original sale date** |
| `item_return_rate` | `items_returned / units_sold` |
| `returned_orders` | COUNT DISTINCT `original_order_id` with ≥1 return line |
| `return_rate` | `returned_orders / total_orders` |
| `in_stock_pct` | ranged store-SKU-days with **closing** `on_hand > 0` / ranged store-SKU-days |
| `on_shelf_availability` | ranged store-SKU **open hours** with `on_hand > 0` / ranged store-SKU open hours |
| `online_fill_rate` | Σ **shipped** units / Σ **requested** units on online order lines |
| `replenishment_fill_rate` | Σ **received** eaches / Σ **ordered** eaches on replenishment orders due in the period |
| `lost_sales_units` | Σ over ranged open hours with `on_hand = 0` of the estimated hourly demand (the forecast for that store-SKU-day × the hour-of-day profile) |
| `lost_sales` ($) | `lost_sales_units × unit_price` |
| `days_of_supply` | closing `on_hand` / mean daily `units_sold` over the trailing 28 days (on uncensored days only) |
| `inventory_turns` | (Σ `units_sold × unit_cost`) / (mean daily `on_hand × unit_cost`) × 365 / days in period |
| `shrink_pct` | perishables: Σ units written off (expired + damaged) / Σ units received |
| `forecast_wape` | Σ\|actual − forecast\| / Σ actual, over **uncensored** store-SKU-days (`on_hand > 0` all open hours) |
