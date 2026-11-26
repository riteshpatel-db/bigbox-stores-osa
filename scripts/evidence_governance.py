"""Write the stage-B evidence: the same queries run as the owner and as each persona (own CLI
profile, own identity), grants, filters and masks, metric views vs hand-written SQL, comment and
tag coverage, and lineage from system tables.

  uv run python scripts/evidence_governance.py --warehouse-id <id> \
      --out evidence/02_unity_catalog.md --out-meta evidence/02b_catalog_metadata.md
"""

import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path

HOST = "https://fevm-serverless-stable-ritesh.cloud.databricks.com"
CAT = "bigbox_fe_bar"
PERSONAS = ["bigbox-sp-ops-director", "bigbox-sp-region-east", "bigbox-sp-analyst"]
MONTH = "2026-09-01"


class Sql:
    def __init__(self, profile: str, warehouse_id: str):
        self.profile, self.wh = profile, warehouse_id

    def _cli(self, *args: str, body: dict | None = None) -> dict:
        cmd = [
            os.environ.get("DATABRICKS_CLI", "databricks"),
            "-p",
            self.profile,
            *args,
            "-o",
            "json",
        ]
        if body is not None:
            cmd += ["--json", json.dumps(body)]
        return json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)

    def try_rows(self, statement: str) -> tuple[list[list] | None, str]:
        r = self._cli(
            "api",
            "post",
            "/api/2.0/sql/statements",
            body={
                "warehouse_id": self.wh,
                "statement": statement,
                "wait_timeout": "50s",
                "on_wait_timeout": "CONTINUE",
                "format": "JSON_ARRAY",
                "disposition": "INLINE",
            },
        )
        while r["status"]["state"] in ("PENDING", "RUNNING"):
            r = self._cli("api", "get", f"/api/2.0/sql/statements/{r['statement_id']}")
        if r["status"]["state"] != "SUCCEEDED":
            msg = r["status"].get("error", {}).get("message", "")
            return None, msg.split("]")[0].lstrip("[") if "]" in msg else msg[:80]
        return r.get("result", {}).get("data_array", []) or [], ""

    def rows(self, statement: str) -> list[list]:
        out, err = self.try_rows(statement)
        if out is None:
            raise RuntimeError(f"{self.profile}: {err}\n{statement}")
        return out


def f4(x) -> str:
    return "-" if x is None else f"{float(x):.4f}"


def num(x) -> str:
    return "-" if x is None else f"{float(x):,.0f}"


def value(x) -> str:
    """Integers with thousands separators; anything else as returned."""
    try:
        return f"{int(x):,}"
    except (TypeError, ValueError):
        return str(x)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warehouse-id", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--out-meta", required=True)
    args = ap.parse_args()
    owner_profile = os.environ["DATABRICKS_CONFIG_PROFILE"]
    owner = Sql(owner_profile, args.warehouse_id)
    sessions = [("owner", owner)] + [(p, Sql(p, args.warehouse_id)) for p in PERSONAS]
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = [
        f"- Command: `uv run python scripts/evidence_governance.py` (SQL statements on warehouse "
        f"`{args.warehouse_id}`, each persona authenticated with its own CLI profile)",
        f"- Run at: {now}",
        f"- Workspace: {HOST}",
        f"- UC objects: `{CAT}.serving.region_access`, `{CAT}.serving.region_allowed`, "
        f"`{CAT}.serving.mask_pii`, `{CAT}.serving.sales_lines`, `{CAT}.serving.sales_kpis`, "
        f"`{CAT}.serving.availability_kpis`, `{CAT}.gold.*`, `{CAT}.silver.buyers`",
        "- Git commit: none yet (first commit pending); source in `src/governance/`, "
        "`src/pipeline/`",
    ]

    out = ["# 02 Unity Catalog: personas, grants, row filter, column mask, metric views", *header]
    who = {}
    for name, s in sessions:
        who[name] = s.rows("SELECT current_user()")[0][0]
    access = {
        r[0]: r[1:]
        for r in owner.rows(
            f"SELECT principal, persona, region, pii_cleartext FROM {CAT}.serving.region_access"
        )
    }
    out += [
        "",
        "## Personas (each query below ran under this identity)",
        "",
        "| CLI profile | current_user() | persona | regions | PII cleartext |",
        "|---|---|---|---|---|",
    ]
    for name, _ in sessions:
        persona, region, pii = access.get(who[name], ("-", "-", "-"))
        out.append(f"| {name} | `{who[name]}` | {persona} | {region} | {pii} |")

    grantees = ", ".join(f"'{who[p]}'" for p in PERSONAS)
    grants = owner.rows(f"""
        SELECT grantee, 'CATALOG' AS on_type, catalog_name AS obj, privilege_type
          FROM system.information_schema.catalog_privileges
         WHERE catalog_name = '{CAT}' AND grantee IN ({grantees})
        UNION ALL
        SELECT grantee, 'SCHEMA', schema_name, privilege_type
          FROM {CAT}.information_schema.schema_privileges WHERE grantee IN ({grantees})
        UNION ALL
        SELECT grantee, 'TABLE/VIEW', concat(table_schema, '.', table_name), privilege_type
          FROM {CAT}.information_schema.table_privileges WHERE grantee IN ({grantees})
        ORDER BY 1, 2, 3, 4""")
    name_of = {who[p]: p for p in PERSONAS}
    by: dict[str, dict[str, list[str]]] = {p: {} for p in PERSONAS}
    hidden = 0
    for g, t, o, p in grants:
        if o.split(".")[-1].startswith("__materialization"):
            hidden += 1  # pipeline-internal backing tables
            continue
        key = {"CATALOG": "catalog", "SCHEMA": "schemas"}.get(t, "tables / views")
        by[name_of[g]].setdefault(key, []).append(f"{o} ({p.replace('_', ' ').lower()})")
    out += [
        "",
        "## Grants per persona (information_schema privileges)",
        "",
        "| persona | catalog | schemas | tables / views |",
        "|---|---|---|---|",
    ]
    for p in PERSONAS:
        g = by[p]
        out.append(
            f"| {p} | "
            + " | ".join(
                ", ".join(g.get(k, ["-"])) for k in ("catalog", "schemas", "tables / views")
            )
            + " |"
        )
    out += [
        "",
        f"Grants on pipeline-internal `__materialization_*` tables omitted above: {hidden}. "
        "Gold is granted table by table, so the unfiltered `gold.recommendations` (synced to "
        "Lakebase, where UC row filters don't apply) is not granted to the East persona.",
    ]

    queries = [
        (
            "A. gold.kpi_store_daily rows by region (row filter)",
            f"SELECT region, count(*) FROM {CAT}.gold.kpi_store_daily GROUP BY 1 ORDER BY 1",
        ),
        (
            f"B. serving.sales_kpis units_sold by region, {MONTH[:7]} (metric view)",
            f"SELECT region, MEASURE(units_sold) FROM {CAT}.serving.sales_kpis "
            f"WHERE sale_month = DATE'{MONTH}' GROUP BY ALL ORDER BY 1",
        ),
        (
            f"C. serving.availability_kpis in_stock_pct by region, {MONTH[:7]} (metric view on "
            "filtered gold)",
            f"SELECT region, round(MEASURE(in_stock_pct), 4) FROM {CAT}.serving.availability_kpis "
            f"WHERE month = DATE'{MONTH}' GROUP BY ALL ORDER BY 1",
        ),
        (
            "D. silver.buyers first row (column mask)",
            f"SELECT buyer_id, first_name, last_name, email, phone FROM {CAT}.silver.buyers "
            "ORDER BY buyer_id LIMIT 1",
        ),
        (
            "E. serving.region_access (mapping table, owner only)",
            f"SELECT count(*) FROM {CAT}.serving.region_access",
        ),
        (
            "F. silver.pos_order_lines (not granted to personas)",
            f"SELECT count(*) FROM {CAT}.silver.pos_order_lines",
        ),
        (
            "G. gold.forecast rows by region (stage-C table, row filter declared in its DDL)",
            f"SELECT region, count(*) FROM {CAT}.gold.forecast GROUP BY 1 ORDER BY 1",
        ),
        (
            "H. gold.recommendations (no row filter, synced to Lakebase: all-region personas only)",
            f"SELECT count(*) FROM {CAT}.gold.recommendations",
        ),
    ]
    out += ["", "## The same queries, run as each identity", ""]
    for title, q in queries:
        out += [f"**{title}**", "", "```sql", q, "```", "", "| identity | result |", "|---|---|"]
        for name, s in sessions:
            res, err = s.try_rows(q)
            if res is None:
                cell = f"DENIED: `{err}`"
            elif len(res) == 1 and len(res[0]) == 1:
                cell = num(res[0][0])
            elif len(res[0]) == 2:
                cell = "; ".join(f"{r[0]} {value(r[1])}" for r in res)
            else:
                cell = " / ".join(str(v) for v in res[0])
            out.append(f"| {name} | {cell} |")
        out.append("")

    attached = owner.rows(
        "SELECT table_schema, table_name, filter_name, target_columns FROM "
        f"{CAT}.information_schema.row_filters "
        "UNION ALL SELECT table_schema, table_name, mask_name, column_name FROM "
        f"{CAT}.information_schema.column_masks "
        "ORDER BY 1, 2, 4"
    )
    out += [
        "## Row filters and column masks attached (information_schema)",
        "",
        "| table | function | column(s) |",
        "|---|---|---|",
    ]
    out += [f"| {s}.{t} | `{f}` | {c} |" for s, t, f, c in attached]

    hand_sales = owner.rows(f"""
        WITH l AS (
          SELECT 'POS' ch, order_id, line_id, store_id, quantity u, unit_price p, discount_amount
              d, 0.0 fee
            FROM {CAT}.silver.pos_order_lines WHERE date_trunc('MONTH', sale_date) = DATE'{MONTH}'
          UNION ALL
          SELECT 'ONLINE', order_id, line_id, store_id, shipped_qty, unit_price, discount_amount,
              delivery_fee
            FROM {CAT}.silver.online_order_lines WHERE date_trunc('MONTH', order_date) =
                DATE'{MONTH}'),
        r AS (SELECT channel ch, original_line_id line_id, sum(quantity) ru FROM
            {CAT}.silver.returns GROUP BY 1, 2)
        SELECT s.region, sum(u), sum(u * p - d) + sum(fee),
               (sum(u * p - d) + sum(fee)) / count(DISTINCT concat(l.ch, ':', order_id)),
               coalesce(sum(ru), 0) / sum(u)
          FROM l JOIN {CAT}.silver.stores s USING (store_id) LEFT JOIN r USING (ch, line_id)
         GROUP BY 1 ORDER BY 1""")
    mv_sales = owner.rows(
        f"SELECT region, MEASURE(units_sold), MEASURE(total_revenue), MEASURE(avg_order_value), "
        f"MEASURE(item_return_rate) FROM {CAT}.serving.sales_kpis WHERE sale_month = DATE'{MONTH}' "
        "GROUP BY ALL ORDER BY 1"
    )
    hand_av = owner.rows(f"""
        SELECT region, avg(int(in_stock_at_close)), sum(trading_hours - stockout_hours) /
            sum(trading_hours),
               sum(CASE WHEN perishable THEN expired_units + damaged_units END)
                   / sum(CASE WHEN perishable THEN received_units END),
               sum(closing_on_hand) / sum(units_sold)
          FROM {CAT}.gold.store_sku_daily WHERE date_trunc('MONTH', date) = DATE'{MONTH}'
         GROUP BY 1 ORDER BY 1""")
    mv_av = owner.rows(
        "SELECT region, MEASURE(in_stock_pct), MEASURE(on_shelf_availability), "
        "MEASURE(shrink_pct), "
        f"MEASURE(days_of_supply) FROM {CAT}.serving.availability_kpis WHERE month = DATE'{MONTH}' "
        "GROUP BY ALL ORDER BY 1"
    )

    def compare(title, names, hand, mv, fmt):
        rows = [
            "",
            f"**{title}**",
            "",
            "| region | "
            + " | ".join(f"{n} (metric view / hand SQL)" for n in names)
            + " | match |",
            "|---|" + "---|" * (len(names) + 1),
        ]
        for h, m in zip(hand, mv, strict=True):
            ok = h[0] == m[0] and all(
                abs(float(a) - float(b)) < 1e-9 * max(1, abs(float(a)))
                for a, b in zip(h[1:], m[1:], strict=True)
            )
            rows.append(
                f"| {m[0]} | "
                + " | ".join(f"{fmt(b)} / {fmt(a)}" for a, b in zip(h[1:], m[1:], strict=True))
                + f" | {'yes' if ok else 'NO'} |"
            )
        return rows

    out += ["", f"## Metric views vs hand-written SQL ({MONTH[:7]}, as owner)"]
    out += compare(
        "serving.sales_kpis",
        ["units_sold", "total_revenue", "avg_order_value", "item_return_rate"],
        hand_sales,
        mv_sales,
        lambda x: f"{float(x):,.4f}",
    )
    out += compare(
        "serving.availability_kpis",
        ["in_stock_pct", "on_shelf_availability", "shrink_pct", "days_of_supply"],
        hand_av,
        mv_av,
        f4,
    )
    text = "\n".join(out) + "\n"
    Path(args.out).write_text(text)
    print(f"wrote {args.out}: {len(text):,} chars")

    meta = ["# 02b Unity Catalog: comments, tags and lineage", *header]
    cov = owner.rows(f"""
        SELECT c.table_schema, c.table_name, count(*), count(c.comment), max(t.comment IS NOT NULL)
          FROM {CAT}.information_schema.columns c JOIN {CAT}.information_schema.tables t
            ON t.table_schema = c.table_schema AND t.table_name = c.table_name
         WHERE c.table_schema IN ('gold', 'serving') AND c.table_name NOT LIKE '\\\\_\\\\_%'
         GROUP BY 1, 2 ORDER BY 1, 2""")
    # The synced table's pipeline writes its event log into serving (system-managed, not ours).
    logs = [r for r in cov if r[1].startswith("event_log_")]
    cov = [r for r in cov if not r[1].startswith("event_log_")]
    meta += [
        "",
        "## Comment coverage, gold and serving (information_schema)",
        "",
        "| object | columns | columns with comment | table comment |",
        "|---|---|---|---|",
    ]
    meta += [f"| {s}.{t} | {n} | {c} | {tc} |" for s, t, n, c, tc in cov]
    if any(t == "recommendations_synced" for _, t, *_ in cov):
        meta += [
            "",
            "`serving.recommendations_synced` is a Lakebase synced table: UC rejects comments on "
            "it (`UPDATE_OR_DELETE_FORBIDDEN_FOR_FOREIGN_SECURABLE`, only the owner can change); "
            "its source `gold.recommendations` is fully commented. Omitted: "
            f"{len(logs)} pipeline event-log table(s) in serving (system-managed).",
        ]
    tags = owner.rows(f"""
        SELECT schema_name, table_name, concat_ws(', ', sort_array(collect_list(concat(tag_name,
            '=', tag_value))))
          FROM {CAT}.information_schema.table_tags GROUP BY 1, 2
        UNION ALL
        SELECT schema_name, concat(table_name, '.', column_name), max(concat(tag_name, '=',
            tag_value))
          FROM {CAT}.information_schema.column_tags GROUP BY 1, 2 ORDER BY 1, 2""")
    meta += [
        "",
        "## Tags (table and column)",
        "",
        "Tag values follow the account's governed tag policies: `layer` allows only bronze / "
        "silver / "
        "gold, so raw, ml and serving carry no layer tag; PII types use the governed `pii_type` "
        "key and "
        "table classification the governed `sensitivity` key.",
        "",
        "| object | tags |",
        "|---|---|",
    ]
    meta += [f"| {s}.{t} | {v} |" for s, t, v in tags]
    edges = owner.rows(f"""
        SELECT coalesce(source_table_full_name, source_path), target_table_full_name, entity_type,
               max(event_time)
          FROM system.access.table_lineage
         WHERE target_table_full_name LIKE '{CAT}.%' AND target_table_full_name NOT LIKE
             '%event_log%'
           AND coalesce(source_table_full_name, source_path) IS NOT NULL
         GROUP BY 1, 2, 3 ORDER BY 2, 1""")
    meta += [
        "",
        "## Table lineage (system.access.table_lineage)",
        "",
        "| source | target | via | last seen (UTC date) |",
        "|---|---|---|---|",
    ]
    meta += [
        f"| {s.replace(CAT + '.', '')} | {t.replace(CAT + '.', '')} | {e or 'query'} | {ts[:10]} |"
        for s, t, e, ts in edges
    ]
    bronze_src = owner.rows(f"""
        SELECT count(*), count(source_table_full_name), count(source_path) FROM
            system.access.table_lineage
         WHERE target_table_full_name LIKE '{CAT}.bronze.%' AND target_table_full_name NOT LIKE
             '%event_log%'""")[0]
    meta += [
        "",
        f"Raw volume → bronze: {num(bronze_src[0])} lineage rows target a bronze table, with "
        f"{num(bronze_src[1])} source tables and {num(bronze_src[2])} source paths recorded. The "
        "Auto Loader reads of `/Volumes/bigbox_fe_bar/raw/landing/<entity>/` are not captured as "
        "path lineage; that hop is documented by `_source_file` on every bronze row instead.",
    ]
    col = owner.rows(f"""
        SELECT DISTINCT source_table_full_name, source_column_name, target_table_full_name,
            target_column_name
          FROM system.access.column_lineage
         WHERE target_table_full_name = '{CAT}.gold.kpi_store_daily'
           AND target_column_name IN ('in_stock_pct', 'on_shelf_availability', 'online_fill_rate')
           AND source_table_full_name IS NOT NULL ORDER BY 4, 2""")
    meta += [
        "",
        "## Column lineage sample (system.access.column_lineage)",
        "",
        "| source column | target column |",
        "|---|---|",
    ]
    meta += [
        f"| {s.replace(CAT + '.', '')}.{sc} | {t.replace(CAT + '.', '')}.{tc} |"
        for s, sc, t, tc in col
    ]
    text = "\n".join(meta) + "\n"
    Path(args.out_meta).write_text(text)
    print(f"wrote {args.out_meta}: {len(text):,} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
