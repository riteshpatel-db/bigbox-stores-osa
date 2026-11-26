-- KPI header: the last 7 complete days up to :anchor vs the 7 days before, from the governed
-- metric view (one definition per KPI). :anchor is the day before the recommendation snapshot.
-- @param anchor DATE = 2026-09-30
SELECT IF(date > date_sub(:anchor, 7), 'current', 'prior') AS period,
       min(date) AS first_day,
       max(date) AS last_day,
       MEASURE(on_shelf_availability) AS on_shelf_availability,
       MEASURE(in_stock_pct) AS in_stock_pct,
       MEASURE(lost_sales) AS lost_sales,
       MEASURE(shrink_pct) AS shrink_pct,
       MEASURE(online_fill_rate) AS online_fill_rate
FROM bigbox_fe_bar.serving.availability_kpis
WHERE date BETWEEN date_sub(:anchor, 13) AND :anchor
GROUP BY 1
ORDER BY 1
