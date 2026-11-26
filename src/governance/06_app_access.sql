-- The app's service principal (bigbox-ops-app), least privilege for what the app does as itself:
-- the KPI header reads the two metric views on the warehouse. Nothing else in Unity Catalog: the
-- queue and decisions live in Lakebase (grants in src/lakebase/03_app_grants.sql), the what-if uses
-- the serving-endpoint binding, and Genie runs on behalf of the signed-in user (user_api_scopes), not
-- as this SP. The app serves the Director of Operations, so it sees all regions and no PII.
-- Applied by scripts/deploy.sh once the app exists; ${sp_app} is its application id.

MERGE INTO ${catalog}.serving.region_access t
USING (
  SELECT * FROM VALUES ('${sp_app}', 'bigbox-ops-app (Director of Operations app)', '*', false)
  AS s(principal, persona, region, pii_cleartext)
) s
ON t.principal = s.principal AND t.region = s.region
WHEN MATCHED THEN UPDATE SET persona = s.persona, pii_cleartext = s.pii_cleartext
WHEN NOT MATCHED THEN INSERT *;

GRANT USE CATALOG ON CATALOG ${catalog} TO `${sp_app}`;
GRANT USE SCHEMA ON SCHEMA ${catalog}.serving TO `${sp_app}`;
GRANT SELECT ON VIEW ${catalog}.serving.availability_kpis TO `${sp_app}`;
GRANT SELECT ON VIEW ${catalog}.serving.sales_kpis TO `${sp_app}`;
