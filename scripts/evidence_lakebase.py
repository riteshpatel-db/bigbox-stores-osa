"""Write evidence/04_lakebase.md from a bigbox_lakebase_check run and a bigbox_refresh run.

  uv run python scripts/evidence_lakebase.py --check-run <run> --refresh-run <run> \
      --warehouse-id <id> --out evidence/04_lakebase.md

The check run's notebooks return their measurements (dbutils.notebook.exit); the write-back and
sync tasks print one JSON line each. Project, endpoint and synced-table state come from the
Postgres API; counts on the Delta side (and through the bigbox_ops_pg catalog) from SQL on the
warehouse, once as the owner and once as the East regional persona. Nothing is typed.
"""

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evidence_governance import Sql  # noqa: E402
from write_evidence import HOST, cli, code_hash, git_commit, ts  # noqa: E402

CAT, PG_CAT = "bigbox_fe_bar", "bigbox_ops_pg"
SYNCED = f"{CAT}.serving.recommendations_synced"
BRANCH = "projects/bigbox-ops/branches/production"
CODE = ["src/lakebase", "src/governance/02b_lakebase_tables.sql", "scripts/setup_lakebase.py"]


def latest_tasks(run: dict) -> dict:
    out = {}
    for t in sorted(run["tasks"], key=lambda t: t.get("start_time", 0)):
        out[t["task_key"]] = t
    return out


def output(task: dict) -> dict:
    o = cli("jobs", "get-run-output", str(task["run_id"]))
    if "notebook_output" in o:
        return json.loads(o["notebook_output"]["result"])
    lines = [ln for ln in o.get("logs", "").splitlines() if ln.strip()]
    text = o.get("logs", "")
    start = text.find("{")  # the task prints one JSON document (possibly indented)
    return json.loads(text[start:]) if start >= 0 else {"logs": lines[-3:]}


def minutes(t: dict) -> str:
    return f"{(t['end_time'] - t['start_time']) / 60000:.1f}"


def table(head: list[str], rows: list[list]) -> list[str]:
    def f(v):
        if isinstance(v, bool) or v is None:
            return "-" if v is None else str(v).lower()
        if isinstance(v, int):
            return f"{v:,}"
        return str(v)

    return [
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
        *("| " + " | ".join(f(v) for v in r) + " |" for r in rows),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-run", required=True)
    ap.add_argument("--refresh-run", required=True)
    ap.add_argument("--warehouse-id", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    profile = os.environ["DATABRICKS_CONFIG_PROFILE"]
    sql = Sql(profile, args.warehouse_id)
    east = Sql("bigbox-sp-region-east", args.warehouse_id)
    check = cli("jobs", "get-run", args.check_run)
    refresh = cli("jobs", "get-run", args.refresh_run)
    ct, rt = latest_tasks(check), latest_tasks(refresh)
    seed, verify = output(ct["seed"]), output(ct["verify"])
    wb1, wb2 = output(ct["write_back"]), output(ct["write_back_again"])
    sync, rwb = output(rt["sync"]), output(rt["write_back"])

    project = cli("api", "get", "/api/2.0/postgres/projects/bigbox-ops")
    ep = cli("api", "get", f"/api/2.0/postgres/{BRANCH}/endpoints/primary")
    st = cli("api", "get", f"/api/2.0/postgres/synced_tables/{SYNCED}")
    catalog = cli("api", "get", f"/api/2.0/postgres/catalogs/{PG_CAT}")
    commit = git_commit()
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    md = [
        "# 04 Lakebase: synced recommendations, decisions table, write-back to Delta",
        "- Command: `./scripts/deploy.sh` (bundle project + `scripts/setup_lakebase.py`), "
        f"`databricks bundle run bigbox_refresh` (run `{refresh['run_id']}`), "
        f"`databricks bundle run bigbox_lakebase_check` (run `{check['run_id']}`), then "
        "`uv run python scripts/evidence_lakebase.py`",
        f"- Run at: refresh {ts(refresh['start_time'])} → {ts(refresh['end_time'])}; check "
        f"{ts(check['start_time'])} → {ts(check['end_time'])} (UTC); evidence queried {now}",
        f"- Workspace: {HOST}",
        f"- UC objects: `{SYNCED}`, `{CAT}.gold.recommendations`, `{CAT}.gold.reorder_decisions`, "
        f"`{PG_CAT}.app.reorder_decisions`",
        f"- Git commit: {f'`{commit}`' if commit else 'none yet (first commit pending)'}; "
        f"source sha256 `{code_hash(CODE)}` over {', '.join(CODE)}",
        "",
        "## Lakebase resources",
        "",
    ]
    ps, es = project["status"], ep["status"]
    pg_db = (catalog.get("status") or catalog.get("spec") or {}).get("postgres_database")
    md += table(
        ["object", "state / settings"],
        [
            [
                "project `bigbox-ops` (bundle resource)",
                f"Autoscaling, Postgres {ps['pg_version']}, owner = deployer, tag "
                + ", ".join(f"{t['key']}={t['value']}" for t in ps.get("custom_tags", [])),
            ],
            [
                "endpoint `production/primary`",
                f"{es.get('current_state')}, {es.get('autoscaling_limit_min_cu')}–"
                f"{es.get('autoscaling_limit_max_cu')} CU, suspends after "
                f"{es.get('suspend_timeout_duration')} idle",
            ],
            [
                f"UC catalog `{PG_CAT}`",
                f"database `{pg_db}` on branch production",
            ],
            [
                f"synced table `{SYNCED}`",
                f"{st['status']['detailed_state']}, {st['status']['scheduling_policy']}, "
                f"PK {' + '.join(st['status']['primary_key_columns'])}, source "
                f"`{st['status']['source_table_full_name']}` (CDF on)",
            ],
        ],
    )
    s = seed["status"]
    md += [
        "",
        f"Last sync: {s['last_sync_start']} → {s['last_sync_end']}, caught up to source version "
        f"{s['synced_source_version']} (latest source version {s['source_latest_version']}).",
        "",
        "## Triggered sync after each refresh (`bigbox_refresh`)",
        "",
    ]
    md += table(
        ["task", "result", "minutes"],
        [[k, t["state"].get("result_state"), minutes(t)] for k, t in rt.items()],
    )
    md += [
        "",
        f"`sync` started update `{sync['update_id']}` of the synced table's pipeline: "
        f"{sync['update_state']} in {sync['seconds']} s, source version "
        f"{sync['source_commit_version_before']} → {sync['source_commit_version_after']} "
        f"(the `score` task rewrote `gold.recommendations`), state after: "
        f"{sync['detailed_state']}. `write_back` in the same run: {rwb['inserted']} new decisions "
        f"(Postgres {rwb['postgres_rows']}, Delta {rwb['delta_rows']}).",
        "",
        "## Source vs synced, row by row (task `seed`)",
        "",
    ]
    p = seed["parity"]
    md += table(
        ["measure", "`gold.recommendations`", "Postgres `serving.recommendations_synced`"],
        [
            ["rows", p["source_rows"], p["synced_rows"]],
            ["queue rows (queue_reason not null)", p["queue_rows_source"], p["queue_rows_synced"]],
            ["keys only on this side", p["only_in_source"], p["only_in_synced"]],
        ],
    )
    md += [
        "",
        "Rows that differ, per column (doubles within 1e-9): "
        + ", ".join(f"{k} {v}" for k, v in p["rows_differing_by_column"].items())
        + ".",
        "",
        "## Lookup latency from a serverless task in the workspace (one connection, after 10 "
        "warm-up queries)",
        "",
    ]
    md += table(
        ["query", "n", "p50 ms", "p95 ms", "p99 ms", "max ms"],
        [
            [k, v["n"], v["p50_ms"], v["p95_ms"], v["p99_ms"], v["max_ms"]]
            for k, v in seed["latency"].items()
        ],
    )
    sd = seed["seed"]
    md += [
        "",
        "## Decisions: Postgres → write-back → Delta",
        "",
        f"`seed` inserted {sd['evidence_decisions']} decisions for the top-priority queue rows of "
        f"snapshot {sd['snapshot_as_of_ts']} with the app's INSERT (`decided_by = "
        f"'stage-d-evidence'`; "
        + ", ".join(f"{k} {v}" for k, v in sd["by_action"].items())
        + f"): `app.reorder_decisions` "
        f"{sd['postgres_rows_before']} → {sd['postgres_rows_after']} rows.",
        "",
    ]
    md += table(
        ["step", "inserted into Delta", "Postgres rows", "Delta rows"],
        [
            ["`write_back`", wb1["inserted"], wb1["postgres_rows"], wb1["delta_rows"]],
            [
                "`write_back_again` (idempotence)",
                wb2["inserted"],
                wb2["postgres_rows"],
                wb2["delta_rows"],
            ],
        ],
    )
    md += [
        "",
        f"`verify`: {verify['matching_ids']} of {verify['seeded_ids']} ids in both Postgres and "
        f"Delta; column mismatches "
        + ", ".join(f"{k} {v}" for k, v in verify["column_mismatches"].items())
        + f"; region missing "
        f"{verify['region_missing']}; decided → written back at most "
        f"{verify['decided_to_written_back_s_max']} s.",
        "",
    ]
    q = sql.rows(
        f"SELECT 'Delta gold.reorder_decisions' AS src, decided_by, action, count(*) "
        f"FROM {CAT}.gold.reorder_decisions GROUP BY ALL "
        f"UNION ALL SELECT 'bigbox_ops_pg.app.reorder_decisions', decided_by, action, count(*) "
        f"FROM {PG_CAT}.app.reorder_decisions GROUP BY ALL ORDER BY 1, 2, 3"
    )
    md += ["Now, from the SQL warehouse (owner):", ""]
    md += table(["source", "decided_by", "action", "rows"], [[a, b, c, int(n)] for a, b, c, n in q])
    e_rows, e_err = east.try_rows(
        f"SELECT region, count(*) FROM {CAT}.gold.reorder_decisions GROUP BY region ORDER BY region"
    )
    o_rows = sql.rows(
        f"SELECT region, count(*) FROM {CAT}.gold.reorder_decisions GROUP BY region ORDER BY region"
    )
    pg_rows, pg_err = east.try_rows(f"SELECT count(*) FROM {PG_CAT}.app.reorder_decisions")
    md += [
        "",
        "Row filter on the written-back table: owner sees "
        + ", ".join(f"{r} {int(n)}" for r, n in o_rows)
        + "; `bigbox-sp-region-east` sees "
        + (", ".join(f"{r} {int(n)}" for r, n in e_rows) if e_rows is not None else e_err)
        + ". The East persona reading Postgres through the catalog: "
        + (f"{pg_rows[0][0]} rows" if pg_rows is not None else f"denied ({pg_err})")
        + ".",
        "",
    ]
    lin = sql.rows(
        "SELECT source_table_full_name, target_table_full_name, max(event_time) "
        "FROM system.access.table_lineage WHERE target_table_full_name = "
        f"'{CAT}.gold.reorder_decisions' AND source_table_full_name IS NOT NULL GROUP BY ALL ORDER BY 1"
    )
    md += ["## Lineage (system.access.table_lineage)", ""]
    md += (
        table(["source", "target", "last seen"], [list(r) for r in lin])
        if lin
        else [
            "No lineage rows for `gold.reorder_decisions` yet (system tables lag by up to hours)."
        ]
    )
    md += [
        "",
        "## Trade-offs",
        "",
        "- The synced table holds all of tonight's store × SKUs, not only the queue: TRIGGERED "
        "sync needs a Delta source with change data feed (a filtered view would force snapshot "
        "mode), and the app's what-if needs any store × SKU's feature row. The app reads the "
        "queue through a partial index (`queue_reason IS NOT NULL`).",
        "- Unity Catalog row filters do not reach Postgres. `gold.recommendations` carries no "
        "filter and no PII (it is granted to the all-region personas only), and the app's service "
        "principal will get SELECT on schema `serving` and INSERT/SELECT on `app` only (stage F).",
        "- The evidence decisions are labelled `decided_by = 'stage-d-evidence'` and kept; real "
        "app decisions are told apart by that column.",
    ]
    Path(args.out).write_text("\n".join(md) + "\n")
    print(f"wrote {args.out} ({len(chr(10).join(md))} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
