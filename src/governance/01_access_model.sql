-- Access model: who may see which region, and who may see buyer PII (name, email, phone) in cleartext.
-- Applied before the pipeline update that attaches the row filter and the column mask, because the
-- pipeline references these functions. ${...} placeholders are filled by scripts/apply_governance.py.

CREATE TABLE IF NOT EXISTS ${catalog}.serving.region_access (
  principal STRING NOT NULL COMMENT 'User email or service-principal application id, as returned by current_user()',
  persona STRING COMMENT 'Business role this principal represents',
  region STRING NOT NULL COMMENT 'Region this principal may see; * = all regions',
  pii_cleartext BOOLEAN NOT NULL COMMENT 'True only for principals allowed to see buyer email / phone in cleartext'
)
COMMENT 'Mapping table behind the region row filter and the PII column mask (one row per principal and region).';

MERGE INTO ${catalog}.serving.region_access t
USING (
  SELECT * FROM VALUES
    ('${owner}', 'data owner (pipeline identity)', '*', true),
    ('${sp_ops_director}', 'Director of Operations', '*', false),
    ('${sp_region_east}', 'Regional manager, East', 'EAST', false),
    ('${sp_analyst}', 'Analyst', '*', false)
  AS s(principal, persona, region, pii_cleartext)
) s
ON t.principal = s.principal AND t.region = s.region
WHEN MATCHED THEN UPDATE SET persona = s.persona, pii_cleartext = s.pii_cleartext
WHEN NOT MATCHED THEN INSERT *;

CREATE OR REPLACE FUNCTION ${catalog}.serving.region_allowed(row_region STRING)
RETURNS BOOLEAN
COMMENT 'Row filter: true when the current principal may see rows of this region (serving.region_access).'
RETURN EXISTS (
  SELECT 1 FROM ${catalog}.serving.region_access a
  WHERE a.principal = current_user() AND (a.region = '*' OR a.region = row_region)
);

CREATE OR REPLACE FUNCTION ${catalog}.serving.mask_pii(value STRING)
RETURNS STRING
COMMENT 'Column mask for buyer PII (name, email, phone): cleartext only for principals with pii_cleartext; otherwise an email keeps its first character and domain, a phone its last 4 digits, a name its first letter.'
RETURN CASE
  WHEN EXISTS (
    SELECT 1 FROM ${catalog}.serving.region_access a
    WHERE a.principal = current_user() AND a.pii_cleartext
  ) THEN value
  WHEN value LIKE '%@%' THEN concat(left(value, 1), '***@', split_part(value, '@', 2))
  WHEN value RLIKE '^[+0-9() -]+$' THEN concat('***-***-', right(value, 4))
  ELSE concat(left(value, 1), '***')
END;
