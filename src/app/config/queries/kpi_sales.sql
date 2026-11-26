-- KPI header: revenue and orders for the same two 7-day periods as kpi_availability.
-- @param anchor DATE = 2026-09-30
SELECT IF(sale_date > date_sub(:anchor, 7), 'current', 'prior') AS period,
       MEASURE(total_revenue) AS total_revenue,
       MEASURE(total_orders) AS total_orders
FROM bigbox_fe_bar.serving.sales_kpis
WHERE sale_date BETWEEN date_sub(:anchor, 13) AND :anchor
GROUP BY 1
ORDER BY 1
