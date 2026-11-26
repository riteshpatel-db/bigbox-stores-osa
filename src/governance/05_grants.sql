-- Least-privilege grants per persona. Nobody but the owner may read serving.region_access (it says
-- who can see what), bronze, or silver; the director alone also reads silver.buyers, where the
-- PII mask applies. Views and metric views run with the owner's rights on their sources, so
-- readers need SELECT on the view only. Region and PII rules are enforced by the row filter and
-- the column mask, not by these grants.

GRANT USE CATALOG ON CATALOG ${catalog} TO `${sp_ops_director}`;
GRANT USE CATALOG ON CATALOG ${catalog} TO `${sp_region_east}`;
GRANT USE CATALOG ON CATALOG ${catalog} TO `${sp_analyst}`;

-- gold: read-only, table by table (the row filter limits regions). Not schema-wide: the
-- unfiltered gold.recommendations (synced to Lakebase, where UC row filters don't apply) is granted
-- to the all-region personas only. The REVOKE removes the earlier schema-wide grant.
REVOKE SELECT ON SCHEMA ${catalog}.gold FROM `${sp_ops_director}`;
REVOKE SELECT ON SCHEMA ${catalog}.gold FROM `${sp_region_east}`;
REVOKE SELECT ON SCHEMA ${catalog}.gold FROM `${sp_analyst}`;
GRANT USE SCHEMA ON SCHEMA ${catalog}.gold TO `${sp_ops_director}`;
GRANT USE SCHEMA ON SCHEMA ${catalog}.gold TO `${sp_region_east}`;
GRANT USE SCHEMA ON SCHEMA ${catalog}.gold TO `${sp_analyst}`;
GRANT SELECT ON TABLE ${catalog}.gold.store_sku_daily TO `${sp_ops_director}`;
GRANT SELECT ON TABLE ${catalog}.gold.store_sku_daily TO `${sp_region_east}`;
GRANT SELECT ON TABLE ${catalog}.gold.store_sku_daily TO `${sp_analyst}`;
GRANT SELECT ON TABLE ${catalog}.gold.inventory_position TO `${sp_ops_director}`;
GRANT SELECT ON TABLE ${catalog}.gold.inventory_position TO `${sp_region_east}`;
GRANT SELECT ON TABLE ${catalog}.gold.inventory_position TO `${sp_analyst}`;
GRANT SELECT ON TABLE ${catalog}.gold.kpi_store_daily TO `${sp_ops_director}`;
GRANT SELECT ON TABLE ${catalog}.gold.kpi_store_daily TO `${sp_region_east}`;
GRANT SELECT ON TABLE ${catalog}.gold.kpi_store_daily TO `${sp_analyst}`;
GRANT SELECT ON TABLE ${catalog}.gold.online_fill TO `${sp_ops_director}`;
GRANT SELECT ON TABLE ${catalog}.gold.online_fill TO `${sp_region_east}`;
GRANT SELECT ON TABLE ${catalog}.gold.online_fill TO `${sp_analyst}`;
GRANT SELECT ON TABLE ${catalog}.gold.replenishment_fill TO `${sp_ops_director}`;
GRANT SELECT ON TABLE ${catalog}.gold.replenishment_fill TO `${sp_region_east}`;
GRANT SELECT ON TABLE ${catalog}.gold.replenishment_fill TO `${sp_analyst}`;
GRANT SELECT ON TABLE ${catalog}.gold.forecast TO `${sp_ops_director}`;
GRANT SELECT ON TABLE ${catalog}.gold.forecast TO `${sp_region_east}`;
GRANT SELECT ON TABLE ${catalog}.gold.forecast TO `${sp_analyst}`;
GRANT SELECT ON TABLE ${catalog}.gold.recommendations TO `${sp_ops_director}`;
GRANT SELECT ON TABLE ${catalog}.gold.recommendations TO `${sp_analyst}`;
GRANT SELECT ON TABLE ${catalog}.gold.reorder_decisions TO `${sp_ops_director}`;
GRANT SELECT ON TABLE ${catalog}.gold.reorder_decisions TO `${sp_region_east}`;
GRANT SELECT ON TABLE ${catalog}.gold.reorder_decisions TO `${sp_analyst}`;

-- serving: the KPI views only, not the access mapping table
GRANT USE SCHEMA ON SCHEMA ${catalog}.serving TO `${sp_ops_director}`;
GRANT USE SCHEMA ON SCHEMA ${catalog}.serving TO `${sp_region_east}`;
GRANT USE SCHEMA ON SCHEMA ${catalog}.serving TO `${sp_analyst}`;
GRANT SELECT ON VIEW ${catalog}.serving.sales_kpis TO `${sp_ops_director}`;
GRANT SELECT ON VIEW ${catalog}.serving.sales_kpis TO `${sp_region_east}`;
GRANT SELECT ON VIEW ${catalog}.serving.sales_kpis TO `${sp_analyst}`;
GRANT SELECT ON VIEW ${catalog}.serving.availability_kpis TO `${sp_ops_director}`;
GRANT SELECT ON VIEW ${catalog}.serving.availability_kpis TO `${sp_region_east}`;
GRANT SELECT ON VIEW ${catalog}.serving.availability_kpis TO `${sp_analyst}`;
GRANT SELECT ON VIEW ${catalog}.serving.sales_lines TO `${sp_ops_director}`;
GRANT SELECT ON VIEW ${catalog}.serving.sales_lines TO `${sp_region_east}`;
GRANT SELECT ON VIEW ${catalog}.serving.sales_lines TO `${sp_analyst}`;

-- silver.buyers: Director of Operations only; names, email and phone are masked for them
GRANT USE SCHEMA ON SCHEMA ${catalog}.silver TO `${sp_ops_director}`;
GRANT SELECT ON TABLE ${catalog}.silver.buyers TO `${sp_ops_director}`;
