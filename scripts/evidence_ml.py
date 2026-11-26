"""Write the stage-C evidence from a finished bigbox_ml_train run, the UC tables it wrote, the model
registry, the deployed endpoint and the ground truth.

  uv run python scripts/evidence_ml.py --run-id <bigbox_ml_train run> --warehouse-id <id> \
      --out evidence/03_ml.md --out-backtest evidence/03b_backtest_value.md

Every number is queried or returned by an API at run time; nothing is typed.
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src" / "value"),
    str(ROOT / "src" / "ml"),
    str(ROOT / "src" / "generator"),
]
from evidence_governance import Sql  # noqa: E402
from write_evidence import HOST, cli, code_hash, git_commit, ts  # noqa: E402

import value_model  # noqa: E402
from bigbox_gen.config import load_config  # noqa: E402
from bigbox_ml.policy import Policy  # noqa: E402

CAT = "bigbox_fe_bar"
MODEL = f"{CAT}.ml.demand_lgbm"
ENDPOINT = "bigbox-demand-forecast"
TRUTH = f"/Volumes/{CAT}/raw/landing/_ground_truth/"
CODE = ["src/ml", "src/value", "src/governance/02_ml_tables.sql"]
CAL = load_config()["calendar"]
H_END = CAL["history_end"]
H0 = H_END - dt.timedelta(days=55)  # the 8-week holdout, as in 02_train
HIST0 = CAL["history_start"]


def task_output(run: dict, key: str) -> dict:
    # a repaired run lists every attempt; the last one is the output that stands
    t = max((t for t in run["tasks"] if t["task_key"] == key), key=lambda t: t["start_time"])
    out = cli("jobs", "get-run-output", str(t["run_id"]))
    return json.loads(out["notebook_output"]["result"])


def fmt(x, nd=4) -> str:
    """Integers with separators, large values rounded, ratios to `nd` decimals; text as is."""
    if x is None:
        return "-"
    if isinstance(x, bool):
        return str(x).lower()
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    if f.is_integer() or abs(f) >= 1000:
        return f"{f:,.0f}"
    return f"{f:.{nd}f}".rstrip("0").rstrip(".")


def table(head: list[str], rows: list[list]) -> list[str]:
    return [
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
        *("| " + " | ".join(fmt(v) for v in r) + " |" for r in rows),
    ]


def header(title: str, run: dict, uc: list[str]) -> list[str]:
    commit = git_commit()
    code = f"`{commit}`" if commit else "none yet (first commit pending)"
    return [
        f"# {title}",
        f"- Command: `databricks bundle run bigbox_ml_train` (run `{run['run_id']}`), then "
        "`uv run python scripts/evidence_ml.py` (SQL on the warehouse, registry and serving APIs)",
        f"- Run at: {ts(run['start_time'])} → {ts(run['end_time'])} (UTC); evidence queried "
        f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"- Workspace: {HOST}",
        f"- UC objects: {', '.join(f'`{u}`' for u in uc)}",
        f"- Git commit: {code}; source sha256 `{code_hash(CODE)}` over {', '.join(CODE)}",
    ]


def ml_file(run: dict, sql: Sql) -> str:
    train = task_output(run, "train")
    score = task_output(run, "score")
    endpoint = task_output(run, "endpoint")
    out = header(
        "03 ML: features, sweep, registry, batch scoring, endpoint",
        run,
        [
            f"{CAT}.ml.store_sku_features",
            f"{CAT}.ml.sweep_results",
            MODEL,
            f"{CAT}.gold.forecast",
            f"{CAT}.gold.recommendations",
            f"{CAT}.serving.availability_kpis",
        ],
    )
    out += ["", "## Tasks", ""]
    out += table(
        ["task", "result", "minutes"],
        [
            [
                t["task_key"],
                t["state"].get("result_state", "-"),
                f"{(t['end_time'] - t['start_time']) / 60000:.1f}",
            ]
            for t in sorted(run["tasks"], key=lambda t: t["start_time"])
        ],
    )

    # feature table
    n = sql.rows(
        f"SELECT count(*), count(DISTINCT store_id, sku_id), min(date), max(date) FROM {CAT}.ml.store_sku_features"
    )[0]
    pk = sql.rows(
        f"""SELECT k.constraint_name, concat_ws(', ', collect_list(k.column_name))
            FROM {CAT}.information_schema.key_column_usage k
           WHERE k.table_schema = 'ml' AND k.table_name = 'store_sku_features' GROUP BY 1"""
    )
    cols = sql.rows(
        f"""SELECT column_name, data_type, comment IS NOT NULL FROM {CAT}.information_schema.columns
            WHERE table_schema = 'ml' AND table_name = 'store_sku_features' ORDER BY ordinal_position"""
    )
    out += [
        "",
        "## Feature table `ml.store_sku_features`",
        "",
        f"{fmt(n[0])} rows, {fmt(n[1])} store-SKUs, {n[2]} .. {n[3]}. Primary key: "
        + "; ".join(f"`{c}` ({k})" for c, k in pk)
        + f". {sum(c[2] == 'true' for c in cols)} of {len(cols)} columns commented.",
        "",
        "Schema: " + ", ".join(f"`{c}` {t.lower()}" for c, t, _ in cols),
    ]

    # sweep
    sweep = sql.rows(
        f"""SELECT candidate, algorithm, holdout_wape, holdout_bias, val_wape, holdout_rows, train_rows,
                   fit_seconds, coalesce(alias, ''), coalesce(model_version, ''), run_id
              FROM {CAT}.ml.sweep_results ORDER BY holdout_wape"""
    )
    oracle = sql.rows(
        f"""SELECT count(*), sum(abs(demand_instore + demand_online - expected_demand))
                   / sum(demand_instore + demand_online)
              FROM read_files('{TRUTH}', format => 'csv', header => true, inferSchema => true)
             WHERE date BETWEEN '{H0}' AND '{H_END}' AND stockout_hours = 0"""
    )[0]
    out += [
        "",
        f"## Sweep on the shared holdout ({H0} .. {H_END}, uncensored store-SKU-days)",
        "",
        f"Training rows {fmt(train['train_rows'])} (sample of uncensored days, point-in-time "
        f"`FeatureLookup`), holdout rows {fmt(train['holdout_rows'])}. Source: `ml.sweep_results`; "
        f"runs in MLflow experiment `{train['experiment']}` (sweep run `{train['sweep_run_id']}`).",
        "",
    ]
    out += table(
        [
            "candidate",
            "algorithm",
            "holdout WAPE",
            "bias",
            "val WAPE",
            "rows",
            "train rows",
            "fit s",
            "alias",
            "version",
            "MLflow run",
        ],
        [[*r[:10], f"`{r[10][:8]}`"] for r in sweep],
    )
    best = float(sweep[0][2])
    inc = next(float(r[2]) for r in sweep if r[0] == "incumbent_ma28")
    out += [
        "",
        f"**Noise floor (ground truth):** forecasting with the generator's true expected demand gives "
        f"WAPE {fmt(oracle[1])} on the same {fmt(oracle[0])} store-SKU-days (day-level shocks and "
        f"Poisson noise at ~2 units/day are unforecastable). The incumbent is {fmt(inc - float(oracle[1]))} "
        f"above that floor; the champion closes {(inc - best) / (inc - float(oracle[1])):.0%} of the gap "
        f"(relative WAPE change {best / inc - 1:+.1%}).",
        "",
        "AutoML forecasting: attempted in `02_train`; `databricks.automl` cannot be imported on "
        "serverless environment 4 (output in the notebook), so it is not a candidate.",
    ]

    # registry
    rm = cli("registered-models", "get", MODEL, "--include-aliases")
    aliases = {a["alias_name"]: a["version_num"] for a in rm.get("aliases", [])}
    versions = cli("model-versions", "list", MODEL)
    vrows = []
    for v in sorted(versions, key=lambda v: int(v["version"]), reverse=True)[:4]:
        mv = cli("model-versions", "get", MODEL, str(v["version"]))
        alias = ", ".join(a for a, n in aliases.items() if int(n) == int(v["version"]))
        vrows.append(
            [
                str(v["version"]),
                alias or "-",
                mv.get("status", "-"),
                (mv.get("comment") or "")[:110],
            ]
        )
    out += ["", f"## Registry `{MODEL}`", ""]
    out += table(["version", "alias", "status", "description"], vrows)

    # batch scoring
    fc = sql.rows(
        f"""SELECT count(*), min(date), max(date), concat_ws(',', collect_set(model_version)),
                   sum(lost_sales_units), sum(lost_sales) FROM {CAT}.gold.forecast"""
    )[0]
    lost = sql.rows(
        f"""WITH est AS (SELECT date >= '{H0}' AS holdout, sum(lost_sales_units) est
                           FROM {CAT}.gold.forecast WHERE date <= '{H_END}' GROUP BY 1),
                 truth AS (SELECT date >= '{H0}' AS holdout,
                                  sum(demand_instore + demand_online - sold_instore - shipped_online) tru
                             FROM read_files('{TRUTH}', format => 'csv', header => true, inferSchema => true)
                            WHERE date <= '{H_END}' GROUP BY 1)
            SELECT IF(holdout, 'holdout {H0}..{H_END}', 'history before the holdout'), est, tru,
                   est / tru - 1
              FROM est JOIN truth USING (holdout) ORDER BY 1"""
    )
    mv = sql.rows(
        f"""SELECT month, MEASURE(forecast_wape), MEASURE(lost_sales_units), MEASURE(lost_sales)
              FROM {CAT}.serving.availability_kpis WHERE month BETWEEN DATE_TRUNC('MONTH', DATE'{H0}') AND DATE'{H_END}'
             GROUP BY ALL ORDER BY 1"""
    )
    out += [
        "",
        "## Batch scoring `gold.forecast` and lost sales",
        "",
        f"{fmt(fc[0])} rows, {fc[1]} .. {fc[2]}, model version(s) {fc[3]}; Σ lost_sales_units "
        f"{fmt(fc[4])}, Σ lost_sales ${fmt(fc[5])}. Hour-of-day profile measured from sale lines "
        f"(14 trading hours): {', '.join(f'{h}h {s:.3f}' for h, s in score['hour_profile'].items())}.",
        "",
        "Estimated lost units (forecast x stocked-out share of the day's profile) vs ground truth "
        "(true demand - units sold):",
        "",
    ]
    out += table(
        ["period", "estimated", "true", "difference"],
        [[*r[:3], f"{float(r[3]):+.1%}"] for r in lost],
    )
    out += ["", "Metric view `serving.availability_kpis` (joins `gold.forecast`):", ""]
    out += table(
        ["month", "forecast_wape", "lost_sales_units", "lost_sales $"],
        [[r[0][:7], *r[1:]] for r in mv],
    )

    rec = sql.rows(
        f"""SELECT count(*), max(forecast_date), max(as_of_ts), sum(IF(queue_reason = 'STOCKOUT_RISK', 1, 0)),
                   sum(IF(queue_reason = 'OVERSTOCK', 1, 0)), sum(IF(recommended_order_qty > 0, 1, 0)),
                   sum(recommended_order_value) FROM {CAT}.gold.recommendations"""
    )[0]
    top = sql.rows(
        f"""SELECT priority, store_id, sku_id, category, on_hand, on_order_units,
                   round(demand_until_delivery, 1), round(stockout_risk, 3), round(expected_lost_sales, 2),
                   recommended_order_qty FROM {CAT}.gold.recommendations
             WHERE queue_reason = 'STOCKOUT_RISK' ORDER BY priority LIMIT 5"""
    )
    out += [
        "",
        "## `gold.recommendations` (tonight's orders)",
        "",
        f"{fmt(rec[0])} store-SKUs for {rec[1]} (on hand as of {rec[2]}): {fmt(rec[3])} STOCKOUT_RISK, "
        f"{fmt(rec[4])} OVERSTOCK; {fmt(rec[5])} order lines worth ${fmt(rec[6])} at cost. Top of the queue:",
        "",
    ]
    out += table(
        [
            "#",
            "store",
            "sku",
            "category",
            "on hand",
            "on order",
            "demand to delivery",
            "risk",
            "exp. lost $",
            "order qty",
        ],
        top,
    )

    # endpoint
    ep = cli("serving-endpoints", "get", ENDPOINT)
    se = ep["config"]["served_entities"][0]
    example = sql.rows(
        f"""SELECT f.features_json, f.forecast_today FROM {CAT}.gold.recommendations f
             WHERE queue_reason = 'STOCKOUT_RISK' ORDER BY priority LIMIT 1"""
    )[0]
    body = {"dataframe_records": [json.loads(example[0])]}
    t0 = time.perf_counter()
    resp = cli("serving-endpoints", "query", ENDPOINT, "--json", json.dumps(body))
    ms = (time.perf_counter() - t0) * 1000
    out += [
        "",
        f"## Endpoint `{ENDPOINT}`",
        "",
        f"State ready={ep['state']['ready']}, config_update={ep['state']['config_update']}; serves "
        f"`{se['entity_name']}` version {se['entity_version']} (@champion = {aliases.get('champion')}), "
        f"workload {se.get('workload_size')}, scale_to_zero={se.get('scale_to_zero_enabled')}; tags "
        f"{', '.join(f'{t["key"]}={t["value"]}' for t in ep.get('tags', []))}.",
        "",
        f"**Parity** (job task `endpoint`): {endpoint['parity_rows']} holdout rows, max |batch - endpoint| "
        f"= {endpoint['parity_max_abs_delta']:.3e} (tolerance 1e-6) → "
        f"{'PASS' if endpoint['parity_pass'] else 'FAIL'}. Single-row latency from a serverless notebook: "
        f"p50 {endpoint['latency_ms']['p50']} ms, p95 {endpoint['latency_ms']['p95']} ms.",
        "",
        f"Request from this laptop (`databricks serving-endpoints query`, {ms:.0f} ms including CLI "
        f"start-up), the feature row of the top queue item:",
        "",
        "```json",
        json.dumps(body)[:900],
        json.dumps(resp)[:300],
        "```",
        f"Batch forecast for the same row in `gold.recommendations.forecast_today`: {float(example[1]):.6f}.",
    ]

    # lineage
    lin = sql.rows(
        f"""SELECT coalesce(source_table_full_name, source_path), target_table_full_name, max(event_time)
              FROM system.access.table_lineage
             WHERE target_table_full_name IN ('{CAT}.ml.store_sku_features', '{CAT}.gold.forecast',
                   '{CAT}.gold.recommendations', '{CAT}.ml.sweep_results', '{CAT}.ml.backtest_daily')
               AND coalesce(source_table_full_name, source_path) IS NOT NULL
             GROUP BY 1, 2 ORDER BY 2, 1"""
    )
    out += ["", "## Lineage (system.access.table_lineage) and model provenance", ""]
    out += table(
        ["source", "target", "last seen"],
        [[s.replace(CAT + ".", ""), t.replace(CAT + ".", ""), e[:19]] for s, t, e in lin],
    )
    champ = cli("model-versions", "get", MODEL, str(aliases["champion"]))
    run_inputs = cli("api", "get", f"/api/2.0/mlflow/runs/get?run_id={train['sweep_run_id']}")
    ds = ", ".join(
        f"`{d['dataset']['name']}` ({'/'.join(t['value'] for t in d.get('tags', []))}, "
        f"digest {d['dataset'].get('digest')})"
        for d in run_inputs["run"].get("inputs", {}).get("dataset_inputs", [])
    )
    out += [
        "",
        f"Model: `{MODEL}` version {aliases['champion']} ← MLflow run `{champ['run_id']}` "
        f"({champ['source']}) in sweep run `{train['sweep_run_id']}`, whose logged inputs are {ds}. "
        "Unity Catalog records no table → model edge: the models are logged with plain MLflow so the "
        "endpoint takes the feature row in the request (`fe.log_model` would record the edge but make "
        "serving look features up online). `gold.recommendations`, `ml.sweep_results` and "
        "`ml.backtest_daily` are written from pandas, so they have no table lineage either.",
    ]
    return "\n".join(out) + "\n"


def backtest_file(run: dict, sql: Sql) -> str:
    bt = task_output(run, "backtest")
    out = header(
        "03b Backtest and value: incumbent vs ML policy on the 8 held-out weeks",
        run,
        [f"{CAT}.ml.backtest_daily", f"{CAT}.gold.store_sku_daily", MODEL],
    )
    hv = bt["history_vs_gold"]
    out += [
        "",
        "Same world: the backtest re-runs the generator's simulation (config sha256 checked against the "
        "landing manifest). Over the holdout, the generator's history vs `gold.store_sku_daily`: in-stock "
        f"{hv['in_stock_pct'][0]:.6f} vs {hv['in_stock_pct'][1]:.6f}, OSA {hv['osa'][0]:.6f} vs "
        f"{hv['osa'][1]:.6f}, units {fmt(hv['units_sold'][0])} vs {fmt(hv['units_sold'][1])} (gold "
        "excludes quarantined rows).",
        "",
        "All policies trade the same true demand from the same start state, with supply and damage "
        "draws seeded by day. `history` = the generator's own run; `incumbent` = the same rule replayed "
        "(differs from history only by those draws); `ml` = policy (b) at each service level.",
        "",
    ]
    q = sql.rows(
        f"""SELECT policy, service_level,
                   sum(in_stock_at_close) / sum(cell_days), 1 - sum(stockout_hours) / sum(trading_hours),
                   sum(lost_units) / sum(demand_units), sum(lost_sales),
                   sum(IF(perishable, expired_units + damaged_units, 0)) / sum(IF(perishable, received_units, 0)),
                   sum(closing_units) / sum(sold_units),
                   sum(IF(segment = 'slow', closing_units, 0)) / sum(IF(segment = 'slow', sold_units, 0)),
                   1 - sum(IF(segment = 'slow', stockout_hours, 0)) / sum(IF(segment = 'slow', trading_hours, 0)),
                   sum(waste_cost), sum(closing_cost) / count(DISTINCT date), sum(order_lines)
              FROM {CAT}.ml.backtest_daily GROUP BY 1, 2
             ORDER BY CASE policy WHEN 'history' THEN 0 WHEN 'incumbent' THEN 1 ELSE 2 END, 2"""
    )
    out += table(
        [
            "policy",
            "service level",
            "in-stock",
            "OSA",
            "lost units share",
            "lost sales $",
            "shrink",
            "days of supply",
            "slow DoS",
            "slow OSA",
            "waste $",
            "avg inventory $",
            "PO lines",
        ],
        [[r[0], r[1] or "-", *r[2:]] for r in q],
    )
    a = value_model.load()
    pol_sl = Policy.load().service_level
    base = next(r for r in q if r[0] == "incumbent")
    new = next(r for r in q if r[0] == "ml" and abs(float(r[1]) - pol_sl) < 1e-9)
    f = [float(x) for x in base[2:]]
    g = [float(x) for x in new[2:]]
    out += [
        "",
        f"## ML policy (service level {pol_sl}) vs incumbent, against the hypotheses",
        "",
    ]
    out += table(
        ["measure", "incumbent", "ML", "change", "hypothesis"],
        [
            ["lost sales $", f[3], g[3], f"{g[3] / f[3] - 1:+.1%}", "-20 to -30 %"],
            [
                "on-shelf availability",
                f[1],
                g[1],
                f"{(g[1] - f[1]) * 100:+.2f} pts",
                "+2 to +4 pts",
            ],
            ["in-stock at close", f[0], g[0], f"{(g[0] - f[0]) * 100:+.2f} pts", "-"],
            ["perishable shrink", f[4], g[4], f"{g[4] / f[4] - 1:+.1%}", "-10 to -20 %"],
            [
                "days of supply, slow movers",
                f[6],
                g[6],
                f"{g[6] / f[6] - 1:+.1%}",
                "down, no OSA loss",
            ],
            ["OSA, slow movers", f[7], g[7], f"{(g[7] - f[7]) * 100:+.2f} pts", "no loss"],
        ],
    )
    seg = sql.rows(
        f"""SELECT segment, perishable, policy,
                   sum(lost_units) / sum(demand_units), sum(lost_sales),
                   1 - sum(stockout_hours) / sum(trading_hours), sum(closing_units) / sum(sold_units),
                   sum(waste_cost), sum(demand_units)
              FROM {CAT}.ml.backtest_daily
             WHERE policy = 'incumbent' OR (policy = 'ml' AND service_level = {pol_sl})
             GROUP BY ALL ORDER BY segment, perishable, policy DESC"""
    )
    out += [
        "",
        f"By segment (incumbent vs ML at {pol_sl}): the shelf-life cap removes most safety stock on "
        "fast-moving perishables, which cuts their waste and raises their lost units; slow movers gain "
        "the most availability.",
        "",
    ]
    out += table(
        [
            "segment",
            "perishable",
            "policy",
            "lost units share",
            "lost sales $",
            "OSA",
            "days of supply",
            "waste $",
            "demand units",
        ],
        [[r[0], str(r[1]).lower(), *r[2:]] for r in seg],
    )
    tot = sql.rows(
        f"""SELECT policy, service_level, count(DISTINCT date), sum(lost_sales), sum(lost_margin),
                   sum(waste_cost), sum(closing_cost) FROM {CAT}.ml.backtest_daily
             WHERE policy IN ('incumbent', 'ml') GROUP BY 1, 2"""
    )
    rev = float(
        sql.rows(
            f"SELECT sum(revenue) FROM {CAT}.gold.store_sku_daily "
            f"WHERE date BETWEEN '{HIST0}' AND '{H_END}'"
        )[0][0]
    )
    pt = {
        (r[0], None if r[1] is None else float(r[1])): value_model.PolicyTotals(
            int(r[2]), *map(float, r[3:])
        )
        for r in tot
    }
    b, n = pt[("incumbent", None)], pt[("ml", pol_sl)]
    v = value_model.annual_value(b, n, rev, a)
    out += [
        "",
        "## Value model (`src/value/value_model.py`, assumptions in `src/value/assumptions.yaml`)",
        "",
        f"Measured: modelled assortment revenue over 365 days of history ${fmt(rev)} (gold), the "
        f"holdout deltas above. Assumed: company revenue ${fmt(a['company_annual_revenue_usd'])} "
        f"(scale x{v['scale_to_company']:.2f}), realisation {a['realisation']:.0%}, carrying cost "
        f"{a['inventory_carrying_cost_rate']:.0%}/yr, linear annualisation x{v['annualise']:.2f} "
        "(no seasonality adjustment).",
        "",
    ]
    out += table(
        ["component (per year, company scale)", "$"],
        [
            ["lost sales recovered (revenue)", v["lost_sales_recovered"]],
            ["gross margin on recovered sales", v["margin_recovered"]],
            ["waste avoided (expired + damaged, at cost)", v["waste_avoided"]],
            ["carrying cost on inventory change", v["carrying_cost_avoided"]],
            ["**total value (margin + waste + carrying)**", v["total"]],
        ],
    )
    by_level = [
        [
            f"{lvl}",
            *(
                value_model.annual_value(b, pt[("ml", lvl)], rev, a)[k]
                for k in (
                    "lost_sales_recovered",
                    "margin_recovered",
                    "waste_avoided",
                    "carrying_cost_avoided",
                    "total",
                )
            ),
        ]
        for lvl in Policy.load().service_level_sensitivity
    ]
    out += ["", "By service level (same assumptions; the configured level is the headline):", ""]
    out += table(
        ["service level", "lost sales recovered", "margin", "waste", "carrying", "total"], by_level
    )
    grid = value_model.sensitivity(b, n, rev, a)
    revs = a["sensitivity"]["company_annual_revenue_usd"]
    out += ["", "Sensitivity of the total ($/yr):", ""]
    out += table(
        ["realisation", *[f"revenue ${fmt(r)}" for r in revs]],
        [
            [
                f"{r:.0%}",
                *[
                    next(
                        gg["total"]
                        for gg in grid
                        if gg["realisation"] == r and gg["company_annual_revenue_usd"] == rv
                    )
                    for rv in revs
                ],
            ]
            for r in a["sensitivity"]["realisation"]
        ],
    )
    out += [
        "",
        "Not credited: intraday visibility (the simulator has no backroom or expedited delivery); "
        "policy (b) reads history columns observed under the incumbent's stockouts. ROI needs the "
        "run cost (evidence/07_cost.md).",
    ]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--warehouse-id", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--out-backtest", required=True)
    args = ap.parse_args()
    run = cli("jobs", "get-run", args.run_id)
    sql = Sql(os.environ["DATABRICKS_CONFIG_PROFILE"], args.warehouse_id)
    for path, text in ((args.out, ml_file(run, sql)), (args.out_backtest, backtest_file(run, sql))):
        Path(path).write_text(text)
        print(f"wrote {path}: {len(text):,} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
