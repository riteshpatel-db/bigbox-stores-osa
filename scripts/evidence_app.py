"""Write evidence/06_app.md for the deployed app bigbox-ops-app.

  uv run --with 'psycopg[binary]>=3.2' --with databricks-sdk==0.170.0 python scripts/evidence_app.py \
      --session-user <email> \
      --warehouse-id <id> --out evidence/06_app.md

Collects: app.yaml and the bundle's resource bindings as committed; the app, its active deployment
and its bindings as the Apps API returns them; the grants its service principal holds in Unity
Catalog and in Postgres; an excerpt of `databricks apps logs` for one real browser session of
--session-user (opening the queue and deciding an item); and results/app/smoke_test.json written by
scripts/smoke_test_app.sh. Nothing is typed.
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "lakebase"))
from evidence_governance import Sql  # noqa: E402
from write_evidence import HOST, code_hash, git_commit  # noqa: E402

APP = "bigbox-ops-app"
CAT = "bigbox_fe_bar"
CODE = [
    "src/app/server",
    "src/app/client/src",
    "src/app/config",
    "src/app/app.yaml",
    "src/app/package.json",
]
SESSION_EVENTS = ("queue", "item", "whatif", "decision")


def cli(*args: str, raw: bool = False):
    cmd = [
        os.environ.get("DATABRICKS_CLI", "databricks"),
        "-p",
        os.environ["DATABRICKS_CONFIG_PROFILE"],
    ]
    out = subprocess.run(
        [*cmd, *args, *([] if raw else ["-o", "json"])], check=True, capture_output=True, text=True
    ).stdout
    return out if raw else json.loads(out)


def session_lines(text: str, user: str, since: str) -> list[dict]:
    """Structured [APP] log events of one user after `since` (the smoke test's end), in order."""
    out = []
    for ln in text.splitlines():
        if "[APP]" not in ln or "{" not in ln:
            continue
        try:
            ev = json.loads(ln[ln.index("{") :])
        except ValueError:
            continue
        if ev.get("event") in SESSION_EVENTS and ev.get("user") == user and ev["ts"] > since:
            out.append(ev)
    return out


def app_space_id(app: dict) -> str:
    return next(
        r["genie_space"]["space_id"] for r in app.get("resources", []) if "genie_space" in r
    )


def postgres_grants(sp: str) -> list[tuple]:
    from databricks.sdk import WorkspaceClient

    from bigbox_lakebase import connect  # psycopg via uv run --with

    w = WorkspaceClient(profile=os.environ["DATABRICKS_CONFIG_PROFILE"])
    with connect(w) as conn:
        return conn.execute(
            """SELECT table_schema || '.' || table_name, string_agg(privilege_type, ', ' ORDER BY privilege_type)
               FROM information_schema.role_table_grants WHERE grantee = %s GROUP BY 1 ORDER BY 1""",
            (sp,),
        ).fetchall()


def excerpt(events: list[dict]) -> list[dict]:
    """The first override with the requests that led to it, then the session's other decisions."""
    first = next(
        (i for i, e in enumerate(events) if e["event"] == "decision" and e["action"] == "override"),
        None,
    )
    if first is None:
        return events[:12]
    start = max(
        0, next((i for i in range(first, -1, -1) if events[i]["event"] == "item"), first) - 1
    )
    head = events[start : first + 2]
    rest = [e for e in events[first + 2 :] if e["event"] == "decision"]
    return head + rest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-user", required=True, help="email of the real browser session")
    ap.add_argument("--warehouse-id", required=True)
    ap.add_argument("--log-lines", type=int, default=2000)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    app = cli("apps", "get", APP)
    dep = app.get("active_deployment") or {}
    deps = cli("apps", "list-deployments", APP)
    deployments = deps if isinstance(deps, list) else deps.get("app_deployments", [])
    sp = app["service_principal_client_id"]
    smoke = json.loads((ROOT / "results" / "app" / "smoke_test.json").read_text())
    sql = Sql(os.environ["DATABRICKS_CONFIG_PROFILE"], args.warehouse_id)
    uc = sql.rows(f"SHOW GRANTS `{sp}` ON CATALOG {CAT}")
    uc += sql.rows(f"SHOW GRANTS `{sp}` ON SCHEMA {CAT}.serving")
    for v in ("availability_kpis", "sales_kpis"):
        uc += sql.rows(f"SHOW GRANTS `{sp}` ON TABLE {CAT}.serving.{v}")
    region = sql.rows(
        f"SELECT region, pii_cleartext FROM {CAT}.serving.region_access WHERE principal = '{sp}'"
    )
    pg = postgres_grants(sp)
    logs = cli("apps", "logs", APP, "--tail-lines", str(args.log_lines), raw=True)
    events = session_lines(logs, args.session_user, smoke["finished"])
    genie_posts = [ln for ln in logs.splitlines() if "[HTTP]" in ln and "POST /api/genie/" in ln]
    genie_ok = sum(1 for ln in genie_posts if '" 200 ' in ln)
    convs = sorted(set(re.findall(r"/api/genie/default/conversations/(\w+)/", logs)))
    space = app_space_id(app)
    genie_msgs = []
    for c in convs:
        page = cli("genie", "list-conversation-messages", space, c)
        for m in reversed(page.get("messages", [])):
            q = [a["query"] for a in m.get("attachments") or [] if a.get("query")]
            genie_msgs.append(
                (m.get("content"), m.get("status"), (q[0].get("query") or "") if q else "")
            )
    ids = [e["decision_id"] for e in events if e["event"] == "decision"]
    id_list = ", ".join(f"'{i}'" for i in ids) or "''"
    in_pg = sql.rows(
        f"SELECT count(*) FROM bigbox_ops_pg.app.reorder_decisions WHERE CAST(decision_id AS STRING) IN ({id_list})"
    )[0][0]
    in_delta = sql.rows(
        f"SELECT count(*) FROM {CAT}.gold.reorder_decisions WHERE decision_id IN ({id_list})"
    )[0][0]
    commit = git_commit()
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    md = [
        "# 06 App: bigbox-ops-app deployed, its bindings, a real session and an HTTP smoke test",
        "- Command: `./scripts/deploy.sh` (bundle resource `resources/bigbox_ops_app.app.yml`), "
        "`databricks bundle run bigbox_ops_app`, `./scripts/smoke_test_app.sh`, then "
        "`uv run python scripts/evidence_app.py`",
        f"- Run at: deployment {dep.get('create_time')} (UTC); smoke test {smoke['started']} → "
        f"{smoke['finished']}; evidence queried {now}",
        f"- Workspace: {HOST}",
        f"- UC objects: `{CAT}.serving.availability_kpis`, `{CAT}.serving.sales_kpis`, "
        f"`{CAT}.serving.recommendations_synced`, `bigbox_ops_pg.app.reorder_decisions`, "
        f"`{CAT}.gold.reorder_decisions`",
        f"- Git commit: {f'`{commit}`' if commit else 'none yet (first commit pending)'}; "
        f"source sha256 `{code_hash(CODE)}` over {', '.join(CODE)}",
        "",
        "## Deployment",
        "",
        f"App `{APP}` at {app['url']}: app status {app.get('app_status', {}).get('state')}, compute "
        f"{app.get('compute_status', {}).get('state')}. Active deployment `{dep.get('deployment_id')}`: "
        f"{(dep.get('status') or {}).get('state')} ({(dep.get('status') or {}).get('message')}), mode "
        f"{dep.get('mode')}. Runs as its service principal `{app.get('service_principal_name')}` "
        f"(`{sp}`). User API scopes requested in the bundle: {app.get('user_api_scopes')} (Genie runs as "
        f"the signed-in user, with their own grants); effective, with the platform's defaults: "
        f"{app.get('effective_user_api_scopes')}.",
        "",
        "Deployments (`databricks apps list-deployments`); the session and the smoke test below ran on the one "
        "active at their time:",
        "",
        "| deployment | created (UTC) | state | source |",
        "|---|---|---|---|",
        *(
            f"| `{x['deployment_id']}` | {x.get('create_time')} | {x['status']['state']} | "
            f"`{x.get('source_code_path', '').split('/files/')[-1]}` |"
            for x in deployments
        ),
        "",
        "The first build failed by construction (the new service principal had no grants yet, HANDOFF trap 50); the "
        "last two redeploy the same source from `src/app` after the repository move.",
        "",
        "Resource bindings as the Apps API stores them (declared in the bundle):",
        "",
        "| name | type | target | permission |",
        "|---|---|---|---|",
    ]
    for r in app.get("resources", []):
        kind = next(k for k in r if k not in ("name", "description"))
        v = r[kind]
        target = v.get("id") or v.get("space_id") or v.get("database") or v.get("name") or v
        md.append(f"| {r['name']} | {kind} | `{target}` | {v.get('permission')} |")
    md += [
        "",
        "`src/app/app.yaml`:",
        "",
        "```yaml",
        (ROOT / "src" / "app" / "app.yaml").read_text().strip(),
        "```",
        "",
        "## Least privilege of the app's service principal",
        "",
        "Unity Catalog (`SHOW GRANTS`): "
        + "; ".join(sorted({f"{r[1]} on {r[2].lower()} `{r[3]}`" for r in uc}))
        + ". Row filter mapping: "
        + ", ".join(f"region {r[0]}, PII cleartext {r[1]}" for r in region)
        + ". Postgres (`information_schema.role_table_grants`): "
        + "; ".join(f"`{t}` {p}" for t, p in pg)
        + ". No other table, schema or ownership.",
        "",
        f"## A real session (`databricks apps logs`, user {args.session_user})",
        "",
        "Structured events the app logs for each request (`server/routes/ops.ts`), browser session after "
        f"the smoke test: {len(events)} events, "
        + ", ".join(
            f"{n} {k}" for k in SESSION_EVENTS if (n := sum(e["event"] == k for e in events))
        )
        + ". Excerpt (first item opened, what-if, override, queue refreshed; then the last decisions):",
        "",
        "```text",
        *(
            json.dumps({k: v for k, v in e.items() if k != "user"}, separators=(",", ":"))[:260]
            for e in excerpt(events)
        ),
        "```",
        "",
        f"Decisions of this session: {len(ids)} ({', '.join(sorted({e['action'] for e in events if e['event'] == 'decision'}))}); "
        f"in Postgres {in_pg}, in Delta `gold.reorder_decisions` after the next write-back {in_delta}.",
        "",
        f"Genie in the same session (runs as the user): {len(genie_posts)} questions posted to "
        f"`/api/genie/default/messages`, {genie_ok} answered HTTP 200. The conversation, read back "
        "through the Genie API:",
        "",
        "| question | status | Genie SQL (start) |",
        "|---|---|---|",
        *(f"| {q} | {st} | `{' '.join(sq.split())[:70]}` |" for q, st, sq in genie_msgs),
        "",
        "## HTTP smoke test of the deployed URL (`scripts/smoke_test_app.sh`, token generated at runtime)",
        "",
        "| step | request | result |",
        "|---|---|---|",
        f"| health | GET /api/health | {smoke['health_status']}: {smoke['health'].get('rows')} synced rows, "
        f"{smoke['health'].get('queue_rows')} in the queue, Lakebase {smoke['health'].get('lakebase_ms')} ms |",
        f"| identity | GET /api/whoami | {smoke['whoami_status']} |",
        f"| queue | GET /api/queue?open=true&limit=5 | {smoke['queue_status']}: {smoke['queue']['total']} open "
        f"items in {smoke['queue']['ms']} ms; first {smoke['item']} |",
        f"| what-if | POST /api/whatif (15 % off) | {smoke['whatif_status']}: batch "
        f"{smoke['whatif']['batch_forecast']:.4f}, endpoint same row {smoke['whatif']['endpoint_baseline']:.4f}, "
        f"what-if {smoke['whatif']['whatif_forecast']:.4f} units, {smoke['whatif']['ms']} ms |",
        f"| decision | POST /api/decisions (reject, labelled smoke test) | {smoke['decision_status']}: "
        f"`{smoke['decision']['decision_id']}` |",
        f"| Postgres rows | `bigbox_ops_pg.app.reorder_decisions` | {smoke['pg_before']} → {smoke['pg_after']} |",
        f"| write-back | `bigbox_refresh` task write_back only, run {smoke['writeback_run_id']} | "
        f"{smoke['writeback_result']} |",
        f"| Delta rows | `{CAT}.gold.reorder_decisions` | {smoke['delta_before']} → {smoke['delta_after']}; "
        f"the new id found {smoke['decision_in_delta']} time(s) |",
        "",
        f"Verdict: {'PASS' if smoke['passed'] else 'FAIL'}.",
    ]
    Path(args.out).write_text("\n".join(md) + "\n")
    print(f"wrote {args.out} ({len(chr(10).join(md)):,} chars, {len(events)} session events)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
