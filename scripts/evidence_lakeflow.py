"""Write evidence/01_lakeflow.md: pipeline updates, expectation counts from the event log reconciled
against the generator's injected-defect manifest, quarantine counts and incremental ingestion.

  uv run python scripts/evidence_lakeflow.py --pipeline-id <id> --updates <first> <second> \
      --warehouse-id <id> --out evidence/01_lakeflow.md

Every number is the result of a query printed next to it; nothing is typed.
"""

import argparse
import datetime as dt
import json
import os
import subprocess
from pathlib import Path

EXP_SCHEMA = "array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>"
HOST = "https://fevm-serverless-stable-ritesh.cloud.databricks.com"
CAT = "bigbox_fe_bar"
LANDING = f"/Volumes/{CAT}/raw/landing"
TEST_STORE = "S999"


def cli(*args: str, body: dict | None = None) -> dict:
    cmd = [
        os.environ.get("DATABRICKS_CLI", "databricks"),
        "-p",
        os.environ["DATABRICKS_CONFIG_PROFILE"],
        *args,
        "-o",
        "json",
    ]
    if body is not None:
        cmd += ["--json", json.dumps(body)]
    return json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)


class Sql:
    def __init__(self, warehouse_id: str):
        self.wh = warehouse_id

    def rows(self, statement: str) -> list[list]:
        r = cli(
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
            r = cli("api", "get", f"/api/2.0/sql/statements/{r['statement_id']}")
        if r["status"]["state"] != "SUCCEEDED":
            raise RuntimeError(f"{r['status']}\n{statement}")
        return r.get("result", {}).get("data_array", []) or []

    def one(self, statement: str):
        return self.rows(statement)[0][0]


def fs_json(rel: str) -> dict:
    cmd = [
        os.environ.get("DATABRICKS_CLI", "databricks"),
        "-p",
        os.environ["DATABRICKS_CONFIG_PROFILE"],
        "fs",
        "cat",
    ]
    out = subprocess.run(
        cmd + [f"dbfs:{LANDING}/{rel}"], check=True, capture_output=True, text=True
    )
    return json.loads(out.stdout)


def n(x) -> str:
    return f"{int(float(x)):,}" if x is not None else "-"


EXPECTATIONS = (  # (manifest defect, dataset, expectation name)
    ("pos_null_sku", "pos_order_lines", "sku_id_not_null"),
    ("pos_null_store", "pos_order_lines", "store_id_not_null"),
    ("pos_null_price", "pos_order_lines", "unit_price_not_null"),
    ("pos_orphan_sku", "pos_order_lines", "sku_in_products"),
    ("pos_test_store", "pos_order_lines", "store_in_stores"),
    ("pos_negative_qty", "pos_order_lines", "quantity_positive"),
    ("pos_future_ts", "pos_order_lines", "event_not_after_extract"),
    ("online_overship", "online_order_lines", "shipped_not_above_requested"),
)
TABLE_CHECKS = (  # (manifest defect, how it is caught, SQL returning the caught count)
    (
        "pos_duplicate",
        "silver keeps the earliest copy per line_id; sum(_copies - 1)",
        f"SELECT sum(_copies - 1) FROM {CAT}.silver.pos_order_lines",
    ),
    (
        "pos_late",
        "is_late = extract_ts after the row's normal batch",
        f"SELECT count_if(is_late) FROM {CAT}.silver.pos_order_lines",
    ),
    (
        "pos_cents_price",
        "unit_price > 50 x list price, divided by 100",
        f"SELECT count_if(_price_from_cents) FROM {CAT}.silver.pos_order_lines",
    ),
    (
        "online_late",
        "is_late (silver + quarantine)",
        f"SELECT (SELECT count_if(is_late) FROM {CAT}.silver.online_order_lines)"
        f" + (SELECT count_if(is_late) FROM {CAT}.silver.quarantine_online_order_lines)",
    ),
    (
        "receipts_uom_cases",
        "uom = CS converted with case_pack",
        f"SELECT count_if(_uom_converted) FROM {CAT}.silver.replenishment_receipts",
    ),
    (
        "online_schema_drift_rows",
        "new column fulfilment_method populated (schema evolution)",
        f"SELECT count(fulfilment_method) FROM {CAT}.bronze.online_order_lines",
    ),
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pipeline-id", required=True)
    ap.add_argument(
        "--updates", nargs="+", required=True, help="first (backfill) update, then later ones"
    )
    ap.add_argument("--warehouse-id", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--command", required=True)
    args = ap.parse_args()
    sql = Sql(args.warehouse_id)
    pid = args.pipeline_id
    totals = {
        k: v["count"] for k, v in fs_json("_manifest/injected_defects.json")["defects"].items()
    }
    by_file = fs_json("_manifest/injected_defects_by_file.json")
    # Reconcile against the files bronze has ingested so far (live batches still in _staging/ are
    # not delivered yet). Files are matched by entity and name: the drip moves staged files.
    delivered = set()
    for entity in ("pos_order_lines", "online_order_lines", "replenishment_receipts"):
        for (path,) in sql.rows(f"SELECT DISTINCT _source_file FROM {CAT}.bronze.{entity}"):
            delivered.add((entity, path.rstrip("/").split("/")[-1]))
    manifest: dict[str, int] = {k: 0 for k in totals}
    for path, counts in by_file.items():
        entity, name = path.split("/")[-2:]
        if (entity, name) in delivered:
            for k, v in counts.items():
                manifest[k] += v

    updates = []
    for u in args.updates:
        up = cli("pipelines", "get-update", pid, u)["update"]
        prog = sql.rows(
            f"SELECT min(timestamp), max(timestamp) FROM event_log('{pid}') "
            f"WHERE origin.update_id = '{u}' AND event_type = 'update_progress'"
        )[0]
        updates.append((u, up["state"], up.get("cause", ""), prog[0], prog[1]))
    first, last = updates[0], updates[-1]
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = [
        "# 01 Lakeflow (ingest): bronze / silver / gold with expectations",
        f"- Command: `{args.command}`",
        f"- Run at: updates {first[3]} → {last[4]} (UTC); queried {now}",
        f"- Workspace: {HOST}",
        f"- UC objects: pipeline `bigbox_osa_pipeline` (`{pid}`); `{CAT}.bronze.*`, "
        f"`{CAT}.silver.*`, "
        f"`{CAT}.gold.*`; event log via `event_log('{pid}')`",
        "- Git commit: none yet (first commit pending); source in `src/pipeline/`",
        "",
        "## Pipeline updates",
        "",
        "| update_id | state | cause | started | finished |",
        "|---|---|---|---|---|",
    ]
    out += [f"| `{u}` | {s} | {c} | {a} | {b} |" for u, s, c, a, b in updates]

    exp = {
        (r[0], r[1]): (r[2], r[3])
        for r in sql.rows(f"""
        SELECT split(origin.flow_name, '\\\\.')[size(split(origin.flow_name, '\\\\.')) - 1],
               e.name, sum(e.passed_records), sum(e.failed_records)
        FROM event_log('{pid}'),
             LATERAL explode(from_json(details:flow_progress.data_quality.expectations,
               '{EXP_SCHEMA}')) t(e)
        WHERE event_type = 'flow_progress' AND origin.update_id = '{last[0]}'
        GROUP BY 1, 2""")
    }
    out += [
        "",
        f"## Expectations vs injected defects (event log, latest update `{last[0]}`)",
        "",
        "Silver POS / online lines are materialized views, fully recomputed each update, so the "
        "latest update's counts cover every delivered file.",
        "",
        "| injected defect | injected (all files) | injected (delivered files) "
        "| dataset.expectation | failed (event log) | match |",
        "|---|---|---|---|---|---|",
    ]
    for defect, ds, name in EXPECTATIONS:
        inj = manifest[defect]
        failed = exp.get((ds, name), (None, None))[1]
        ok = "yes" if failed is not None and int(failed) == inj else "NO"
        out.append(
            f"| {defect} | {totals[defect]:,} | {inj:,} | silver.{ds}.{name} | {n(failed)} | {ok} |"
        )
    out += [
        "",
        "## Other defects, caught in silver / bronze (table queries)",
        "",
        "| injected defect | injected (all files) | injected (delivered files) | caught by "
        "| caught | match |",
        "|---|---|---|---|---|---|",
    ]
    for defect, how, q in TABLE_CHECKS:
        inj = manifest[defect]
        got = sql.one(q)
        ok = "yes" if got is not None and int(float(got)) == inj else "NO"
        out.append(f"| {defect} | {totals[defect]:,} | {inj:,} | {how} | {n(got)} | {ok} |")

    out += [
        "",
        "## All expectations with failures (latest update)",
        "",
        "| dataset | expectation | passed | failed |",
        "|---|---|---|---|",
    ]
    out += [f"| {d} | {e} | {n(p)} | {n(f)} |" for (d, e), (p, f) in sorted(exp.items()) if int(f)]
    clean = sorted(f"{d}.{e}" for (d, e), (_, f) in exp.items() if not int(f))
    out += ["", f"Expectations with zero failures: {', '.join(clean)}."]

    out += ["", "## Quarantine tables", "", "| table | failed rule | rows |", "|---|---|---|"]
    for t in ("quarantine_pos_order_lines", "quarantine_online_order_lines"):
        for rule, cnt in sql.rows(
            f"SELECT r, count(*) FROM {CAT}.silver.{t} LATERAL VIEW explode(_failed_rules) x AS r "
            "GROUP BY r ORDER BY r"
        ):
            out.append(f"| silver.{t} | {rule} | {n(cnt)} |")

    drift = sql.rows(
        f"SELECT min(to_date(order_ts)), count(fulfilment_method) FROM "
        f"{CAT}.bronze.online_order_lines WHERE fulfilment_method IS NOT NULL"
    )[0]
    rescued = sql.rows(
        " UNION ALL ".join(
            f"SELECT '{t}', count(*), count(_rescued_data) FROM {CAT}.bronze.{t}"
            for t in (
                "pos_order_lines",
                "online_order_lines",
                "inventory_snapshots",
                "replenishment_orders",
                "replenishment_receipts",
                "write_offs",
                "returns",
            )
        )
    )
    out += [
        "",
        "## Bronze rows, parse errors and schema drift",
        "",
        "| bronze table | rows | rows with _rescued_data |",
        "|---|---|---|",
    ]
    out += [f"| {t} | {n(c)} | {n(r)} |" for t, c, r in rescued]
    out += [
        "",
        f"Schema drift: `fulfilment_method` first populated on {drift[0]}, in {n(drift[1])} "
        "rows; earlier rows are NULL (Auto Loader `addNewColumns`).",
    ]

    update_list = ", ".join(f"'{u[0]}'" for u in updates)
    flows = sql.rows(f"""
        SELECT origin.update_id, split(origin.flow_name, '\\\\.')[1] AS layer,
               split(origin.flow_name, '\\\\.')[2] AS tbl,
               sum(details:flow_progress.metrics.num_output_rows::bigint)
        FROM event_log('{pid}')
        WHERE event_type = 'flow_progress' AND origin.update_id IN ({update_list})
          AND details:flow_progress.metrics.num_output_rows IS NOT NULL
          AND split(origin.flow_name, '\\\\.')[1] = 'bronze'
        GROUP BY 1, 2, 3""")
    by = {(u, t): r for u, _, t, r in flows}
    tables = sorted({t for _, t in by})
    out += [
        "",
        "## Incremental ingestion: rows written per bronze flow, per update",
        "",
        "| bronze table | " + " | ".join(f"update `{u[0][:8]}`" for u in updates) + " |",
        "|---|" + "---|" * len(updates),
    ]
    out += [f"| {t} | " + " | ".join(n(by.get((u[0], t))) for u in updates) + " |" for t in tables]

    gold = sql.rows(
        " UNION ALL ".join(
            f"SELECT '{t}', count(*) FROM {CAT}.gold.{t}"
            for t in (
                "store_sku_daily",
                "inventory_position",
                "kpi_store_daily",
                "online_fill",
                "replenishment_fill",
            )
        )
    )
    out += ["", "## Gold tables", "", "| table | rows |", "|---|---|"]
    out += [f"| gold.{t} | {n(c)} |" for t, c in gold]
    # Gold vs the generator's ground truth (history only; the pipeline never reads _ground_truth).
    h = "date <= '2026-09-30'"
    cal = fs_json("_manifest/generator_run.json")["calendar"]
    hours = cal["close_hour"] - cal["open_hour"]
    gt = f"read_files('{LANDING}/_ground_truth/', format => 'csv', header => true)"
    g = sql.rows(
        "SELECT sum(in_stock_sku_days) / sum(ranged_sku_days), "
        "sum(sku_hours_on_shelf) / sum(sku_trading_hours), "
        "sum(online_units_shipped) / sum(online_units_requested), "
        "sum(perishable_units_expired) / sum(perishable_units_received), sum(units_sold) "
        f"FROM {CAT}.gold.kpi_store_daily WHERE {h}"
    )[0]
    t = sql.rows(
        f"SELECT avg(int(closing_on_hand > 0)), 1 - avg(stockout_hours / {hours}), "
        "sum(shipped_online) / sum(demand_online), "
        "sum(CASE WHEN p.perishable THEN expired_units END) "
        "/ sum(CASE WHEN p.perishable THEN received_units END), "
        "sum(sold_instore + shipped_online) "
        f"FROM {gt} t JOIN {CAT}.silver.products p USING (sku_id) WHERE t.{h}"
    )[0]
    real = f"coalesce(store_id, '') <> '{TEST_STORE}'"  # test-store copies are not real sales
    q_pos = sql.one(
        f"SELECT sum(abs(quantity)) FROM {CAT}.silver.quarantine_pos_order_lines WHERE {real} AND "
        "to_date(CASE WHEN array_contains(_failed_rules, 'event_not_after_extract') "
        "THEN event_ts - INTERVAL 1096 DAYS ELSE event_ts END) <= '2026-09-30'"
    )
    q_online = sql.one(
        f"SELECT sum(requested_qty) FROM {CAT}.silver.quarantine_online_order_lines "
        "WHERE order_date <= '2026-09-30'"
    )
    staged = sql.one(
        f"SELECT sum(abs(quantity)) FROM read_files('{LANDING}/_staging/pos_order_lines/', "
        "format => 'csv', header => true, schemaHints => 'line_id BIGINT, quantity BIGINT, "
        f"event_ts TIMESTAMP') s WHERE to_date(event_ts) <= '2026-09-30' AND {real} AND "
        f"line_id NOT IN (SELECT line_id FROM {CAT}.bronze.pos_order_lines)"
    )
    pct = [f"{float(x):.4%}" for x in g[:4]]
    tpct = [f"{float(x):.4%}" for x in t[:4]]
    gap = int(float(t[4])) - int(float(g[4])) - int(float(q_pos)) - int(float(q_online))
    gap -= int(float(staged or 0))
    out += [
        "",
        "## Gold vs ground truth (history 2025-10-01 → 2026-09-30)",
        "",
        "| measure | gold (pipeline) | ground truth (generator) |",
        "|---|---|---|",
    ]
    for name, a_, b_ in zip(
        (
            "in-stock at close",
            "on-shelf availability (hours)",
            "online fill rate",
            "perishable shrink",
        ),
        pct,
        tpct,
        strict=True,
    ):
        out.append(f"| {name} | {a_} | {b_} |")
    out += [
        "",
        "Online fill differs only because overshipped lines (shipped > requested) are in "
        "quarantine, so gold excludes their requested and shipped units.",
    ]
    out += [
        "",
        "| units sold (sold in store + shipped online) | units |",
        "|---|---|",
        f"| ground truth | {n(t[4])} |",
        f"| gold.kpi_store_daily | {n(g[4])} |",
        f"| quarantined POS lines (real sales, excl. test store) | {n(q_pos)} |",
        f"| quarantined online lines (overship: true shipped = requested) | {n(q_online)} |",
        f"| history-dated POS units in live files not yet released (_staging) | {n(staged)} |",
        f"| **unexplained difference** | **{gap:,}** |",
    ]
    text = "\n".join(out) + "\n"
    Path(args.out).write_text(text)
    print(f"wrote {args.out}: {len(text):,} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
