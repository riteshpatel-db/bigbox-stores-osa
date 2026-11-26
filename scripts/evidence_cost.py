"""Write evidence/07_cost.md: what the build cost, unit costs per run and per hour, monthly run cost, ROI.

  uv run python scripts/evidence_cost.py --refresh-run <bigbox_refresh run> --train-run <run> \
      --warehouse-id <id> --out evidence/07_cost.md

All $ are system.billing.usage x system.billing.list_prices (list price, pricing.default) in this
workspace. Usage is attributed to the build by the `project` tag where the platform carries it, and
otherwise by resource id (job, pipeline, endpoint, warehouse, app, Lakebase project); the evidence
shows how much of each component the tag alone would catch. The monthly model multiplies the measured
unit costs by the named assumptions in src/value/cost_assumptions.yaml; the ROI divides the value
model's annual value (same inputs as evidence/03b_backtest_value.md) by 12 months of that cost.
"""

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src" / "value"), str(ROOT / "src" / "ml")]
from evidence_governance import Sql  # noqa: E402
from evidence_ml import H_END, HIST0  # noqa: E402
from write_evidence import HOST, cli, code_hash, git_commit, ts  # noqa: E402

import cost_model  # noqa: E402
import value_model  # noqa: E402
from bigbox_ml.policy import Policy  # noqa: E402

CAT = "bigbox_fe_bar"
WS = "7474657773731312"
TAG = "bigbox-stores-osa"
START = "2026-10-29"  # the build's first day in this workspace (PROVENANCE)
CODE = ["src/value/cost_model.py", "src/value/cost_assumptions.yaml"]


def resources() -> dict[str, str]:
    jobs = cli("jobs", "list")
    jobs = jobs if isinstance(jobs, list) else jobs.get("jobs", [])
    by_name = {
        j["settings"]["name"]: str(j["job_id"]) for j in jobs if "bigbox" in j["settings"]["name"]
    }
    pipes = {p["name"]: p["pipeline_id"] for p in cli("pipelines", "list-pipelines")}
    synced = cli(
        "api", "get", f"/api/2.0/postgres/synced_tables/{CAT}.serving.recommendations_synced"
    )
    project = cli("api", "get", "/api/2.0/postgres/projects/bigbox-ops")
    return {
        **{f"job:{k}": v for k, v in by_name.items()},
        "pipeline": pipes["bigbox_osa_pipeline"],
        "sync_pipeline": synced["status"]["pipeline_id"],
        "lakebase_project": project["uid"],
    }


def component_sql(r: dict[str, str], warehouse: str) -> str:
    j = lambda n: r[f"job:{n}"]  # noqa: E731
    return f"""CASE
      WHEN usage_metadata.job_id = '{j("bigbox_refresh")}' THEN 'refresh job (features, score, sync, write-back)'
      WHEN usage_metadata.job_id = '{j("bigbox_ml_train")}' THEN 'training job'
      WHEN usage_metadata.job_id IN ('{j("bigbox_generate_data")}', '{j("bigbox_live_drip")}') THEN 'data generator and drip'
      WHEN usage_metadata.job_id = '{j("bigbox_lakebase_check")}' THEN 'Lakebase check job'
      WHEN usage_metadata.dlt_pipeline_id = '{r["pipeline"]}' THEN 'Lakeflow pipeline'
      WHEN usage_metadata.dlt_pipeline_id = '{r["sync_pipeline"]}' THEN 'synced-table pipeline'
      WHEN usage_metadata.endpoint_name = 'bigbox-demand-forecast' THEN 'serving endpoint'
      WHEN usage_metadata.warehouse_id = '{warehouse}' THEN 'SQL warehouse (shared; build queries, KPI header, Genie)'
      WHEN usage_metadata.app_name = 'bigbox-ops-app' THEN 'app'
      WHEN usage_metadata.project_id = '{r["lakebase_project"]}' THEN 'Lakebase project'
      WHEN custom_tags['project'] = '{TAG}' THEN 'other tagged'
    END"""


def priced(r: dict[str, str], warehouse: str) -> str:
    return f"""(SELECT u.*, u.usage_quantity * p.pricing.default AS usd, {component_sql(r, warehouse)} AS component,
            coalesce(u.custom_tags['project'] = '{TAG}', false) AS tagged
       FROM system.billing.usage u
       LEFT JOIN system.billing.list_prices p
         ON p.sku_name = u.sku_name AND p.usage_unit = u.usage_unit
        AND u.usage_start_time >= p.price_start_time
        AND (p.price_end_time IS NULL OR u.usage_start_time < p.price_end_time)
      WHERE u.workspace_id = '{WS}' AND u.usage_date >= '{START}')"""


def money(x) -> str:
    x = float(x or 0)
    return f"${x:,.2f}" if abs(x) < 1000 else f"${x:,.0f}"


def table(head: list[str], rows: list[list]) -> list[str]:
    return [
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
        *("| " + " | ".join(map(str, r)) + " |" for r in rows),
    ]


def pipeline_update_for(run: dict, pipeline_id: str) -> str | None:
    """The update the run's pipeline task started (created within the task's time window)."""
    t = next((t for t in run["tasks"] if t["task_key"] == "pipeline"), None)
    if not t:
        return None
    ups = cli("pipelines", "list-updates", pipeline_id, "--max-results", "50").get("updates", [])
    inside = [u for u in ups if t["start_time"] - 60_000 <= u["creation_time"] <= t["end_time"]]
    return inside[0]["update_id"] if inside else None


def sync_update_for(run: dict) -> str | None:
    t = next((t for t in run["tasks"] if t["task_key"] == "sync"), None)
    if not t:
        return None
    logs = cli("jobs", "get-run-output", str(t["run_id"])).get("logs", "")
    return json.loads(logs[logs.index("{") :]).get("update_id") if "{" in logs else None


def measure(sql: Sql, warehouse: str, refresh_run: str, train_run: str) -> dict:
    """Billing at list price: build cost to date by component, and the measured unit costs."""
    r = resources()
    u = priced(r, warehouse)
    latest = sql.rows(
        f"SELECT max(usage_end_time), max(usage_date) FROM {u} WHERE component IS NOT NULL"
    )[0]

    # 1. What the build has cost so far, by component.
    comp = sql.rows(
        f"""SELECT component, round(sum(usage_quantity), 2), concat_ws(' + ', sort_array(collect_set(usage_unit))), sum(usd),
                   sum(IF(tagged, usd, 0)), min(usage_date), max(usage_date)
              FROM {u} WHERE component IS NOT NULL GROUP BY 1 ORDER BY 4 DESC"""
    )
    total = sum(float(c[3] or 0) for c in comp)
    tagged = sum(float(c[4] or 0) for c in comp)

    # 2. Unit costs.
    refresh = cli("jobs", "get-run", refresh_run)
    upd, supd = pipeline_update_for(refresh, r["pipeline"]), sync_update_for(refresh)
    parts = sql.rows(
        f"""SELECT CASE WHEN usage_metadata.job_run_id = '{refresh_run}' THEN 'job tasks (serverless)'
                        WHEN usage_metadata.dlt_update_id = '{upd}' THEN 'pipeline update {upd}'
                        WHEN usage_metadata.dlt_update_id = '{supd}' THEN 'synced-table update {supd}' END,
                   round(sum(usage_quantity), 3), sum(usd)
              FROM {u}
             WHERE usage_metadata.job_run_id = '{refresh_run}'
                OR usage_metadata.dlt_update_id IN ('{upd}', '{supd}')
             GROUP BY 1 ORDER BY 1"""
    )
    refresh_usd = sum(float(p[2] or 0) for p in parts)
    train = sql.rows(
        f"SELECT round(sum(usage_quantity), 3), sum(usd) FROM {u} WHERE usage_metadata.job_run_id = '{train_run}'"
    )[0]

    def per_hour(component: str) -> dict[str, float]:
        """Mean $ per billed hour, and the busiest billed hour (a fully used hour)."""
        rows = sql.rows(
            f"""SELECT date_trunc('HOUR', usage_start_time), sum(usd), sum(usage_quantity)
                  FROM {u} WHERE component LIKE '{component}%' GROUP BY 1"""
        )
        usd = [float(x[1] or 0) for x in rows]
        dbu = [float(x[2] or 0) for x in rows]
        if not rows:
            return {"hours": 0, "mean_usd": 0.0, "peak_usd": 0.0, "mean_dbu": 0.0, "peak_dbu": 0.0}
        k = max(range(len(rows)), key=lambda i: dbu[i])
        return {
            "hours": len(rows),
            "mean_usd": sum(usd) / len(rows),
            "mean_dbu": sum(dbu) / len(rows),
            "peak_usd": usd[k],
            "peak_dbu": dbu[k],
        }

    ep, wh, app = per_hour("serving endpoint"), per_hour("SQL warehouse"), per_hour("app")
    lb = sql.rows(
        f"""SELECT sum(usd), (unix_timestamp(max(usage_end_time)) - unix_timestamp(min(usage_start_time))) / 3600
              FROM {u} WHERE component = 'Lakebase project'"""
    )[0]
    lb_usd, lb_hours = float(lb[0] or 0), float(lb[1] or 0)
    lb_day = lb_usd / lb_hours * 24 if lb_hours else 0.0
    # The model assumes continuous use while up, so it takes the busiest (fully used) hour.
    units = cost_model.UnitCosts(
        refresh_usd, float(train[1] or 0), ep["peak_usd"], wh["peak_usd"], app["peak_usd"], lb_day
    )
    return {
        "r": r,
        "u": u,
        "latest": latest,
        "comp": comp,
        "total": total,
        "tagged": tagged,
        "refresh": refresh,
        "upd": upd,
        "supd": supd,
        "parts": parts,
        "refresh_usd": refresh_usd,
        "train": train,
        "ep": ep,
        "wh": wh,
        "app": app,
        "lb_usd": lb_usd,
        "lb_hours": lb_hours,
        "lb_day": lb_day,
        "units": units,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-run", required=True)
    ap.add_argument("--train-run", required=True)
    ap.add_argument("--warehouse-id", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    sql = Sql(os.environ["DATABRICKS_CONFIG_PROFILE"], args.warehouse_id)
    m = measure(sql, args.warehouse_id, args.refresh_run, args.train_run)
    (
        latest,
        comp,
        total,
        tagged,
        refresh,
        parts,
        refresh_usd,
        train,
        ep,
        wh,
        app,
        lb_usd,
        lb_hours,
        lb_day,
        units,
    ) = (
        m[k]
        for k in (
            "latest",
            "comp",
            "total",
            "tagged",
            "refresh",
            "parts",
            "refresh_usd",
            "train",
            "ep",
            "wh",
            "app",
            "lb_usd",
            "lb_hours",
            "lb_day",
            "units",
        )
    )

    # 3. Monthly model and ROI (value model inputs as in evidence_ml.py).
    a = cost_model.load()
    va = value_model.load()
    pol_sl = Policy.load().service_level
    tot = sql.rows(
        f"""SELECT policy, service_level, count(DISTINCT date), sum(lost_sales), sum(lost_margin),
                   sum(waste_cost), sum(closing_cost) FROM {CAT}.ml.backtest_daily
             WHERE policy IN ('incumbent', 'ml') GROUP BY 1, 2"""
    )
    pt = {
        (x[0], None if x[1] is None else float(x[1])): value_model.PolicyTotals(
            int(x[2]), *map(float, x[3:])
        )
        for x in tot
    }
    rev = float(
        sql.rows(
            f"SELECT sum(revenue) FROM {CAT}.gold.store_sku_daily WHERE date BETWEEN '{HIST0}' AND '{H_END}'"
        )[0][0]
    )
    v = value_model.annual_value(pt[("incumbent", None)], pt[("ml", pol_sl)], rev, va)
    m_model = cost_model.monthly_cost(units, a, revenue_scale=1.0)
    m_company = cost_model.monthly_cost(units, a, revenue_scale=v["scale_to_company"])
    roi = cost_model.roi(v["total"], m_company["total"])

    commit = git_commit()
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    md = [
        "# 07 Cost: build to date, unit costs, monthly run cost and ROI",
        "- Command: `uv run python scripts/evidence_cost.py` (SQL on `system.billing.usage` x "
        "`system.billing.list_prices`, list price)",
        f"- Run at: billing data through {latest[0]} (usage date {latest[1]}); evidence queried {now} (UTC)",
        f"- Workspace: {HOST}",
        "- UC objects: `system.billing.usage`, `system.billing.list_prices`, "
        f"`{CAT}.ml.backtest_daily`, `{CAT}.gold.store_sku_daily`",
        f"- Git commit: {f'`{commit}`' if commit else 'none yet (first commit pending)'}; "
        f"source sha256 `{code_hash(CODE)}` over {', '.join(CODE)}",
        "",
        "## Attribution",
        "",
        (
            f"Components whose usage carries the tag `project = {TAG}` in billing: "
            + ", ".join(c[0] for c in comp if float(c[4] or 0) > 0)
            + ". Without it: "
            + ", ".join(c[0] for c in comp if float(c[4] or 0) == 0)
            + ". Serverless pipelines have the tag in their settings, but serverless usage takes tags from a "
            "usage policy, which this build does not set; the warehouse is shared, and the app's usage "
            "arrives with no custom tags. So usage is attributed by resource id (job, pipeline, endpoint, warehouse, app, "
            f"Lakebase project); the tag alone would catch {money(tagged)} of {money(total)} "
            f"({tagged / total:.0%})."
        )
        if total
        else "No attributed usage yet.",
        "",
        "## What the build has cost so far",
        "",
    ]
    md += table(
        ["component", "quantity", "unit", "list $", "of which tagged", "days"],
        [[c[0], c[1], c[2], money(c[3]), money(c[4]), f"{c[5]} → {c[6]}"] for c in comp],
    )
    md += [
        "",
        f"Total {money(total)}. The SQL warehouse is shared and sized Large (not resized: shared); "
        "`system.query.history` shows only this build's principals on it since 2026-11-20, so all of it "
        "is attributed here, mostly to build-time queries (governance, evidence, Genie scoring).",
        "",
        "## Unit costs (measured)",
        "",
        f"One `bigbox_refresh` run `{args.refresh_run}` ({ts(refresh['start_time'])}, tasks "
        f"{', '.join(t['task_key'] for t in sorted(refresh['tasks'], key=lambda t: t['start_time']))}):",
        "",
    ]
    md += table(["part", "DBU", "list $"], [[p[0], p[1], money(p[2])] for p in parts])
    md += [
        "",
        f"= {money(refresh_usd)} per refresh. One `bigbox_ml_train` run `{args.train_run}` (incl. its "
        f"repaired attempts): {train[0]} DBU, {money(train[1])}.",
        "",
    ]
    md += table(
        [
            "resource",
            "billed hours",
            "mean DBU / billed hour",
            "busiest hour DBU",
            "busiest hour list $ (used in the model)",
        ],
        [
            [name, x["hours"], f"{x['mean_dbu']:.2f}", f"{x['peak_dbu']:.2f}", money(x["peak_usd"])]
            for name, x in (
                ("serving endpoint (Small, scale-to-zero)", ep),
                ("SQL warehouse (Large, auto-stop 10 min)", wh),
                ("app compute", app),
            )
        ],
    )
    md += [
        "",
        "Billed hours include partly used ones (auto-stop, scale-to-zero, the app stopped after its test), "
        "which pull the mean down; the monthly model assumes continuous use while up, so it uses the "
        "busiest hour.",
    ]
    md += [
        "",
        f"Lakebase project: {money(lb_usd)} over {lb_hours:.1f} h observed = {money(lb_day)} per day "
        "(compute scales to zero after 5 idle minutes; storage).",
        "",
        "## Monthly run cost (modelled)",
        "",
        "Assumptions (`src/value/cost_assumptions.yaml`): "
        + ", ".join(f"{k} {v}" for k, v in a.items())
        + f". Company scale applies the value model's revenue factor x{v['scale_to_company']:.2f} to "
        "refresh and training only.",
        "",
    ]
    md += table(
        ["component", "modelled slice ($/month)", "company scale ($/month)"],
        [[k, money(m_model[k]), money(m_company[k])] for k in m_model],
    )
    md += [
        "",
        f"Per 15-minute refresh: {money(refresh_usd)} at the modelled slice, "
        f"{money(refresh_usd * v['scale_to_company'])} at company scale.",
        "",
        "## ROI",
        "",
        f"Annual value {money(roi['annual_value'])} (value model, ML policy at service level {pol_sl}, "
        f"{va['realisation']:.0%} realisation, `03b_backtest_value.md`) vs annual run cost "
        f"{money(roi['annual_cost'])} at company scale: net {money(roi['net'])}, "
        f"{roi['value_per_dollar']:.0f} $ of value per $ of run cost. Not included: build effort, "
        "existing platform costs, and storage outside the Lakebase project.",
    ]
    Path(args.out).write_text("\n".join(md) + "\n")
    print(f"wrote {args.out} ({len(chr(10).join(md)):,} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
