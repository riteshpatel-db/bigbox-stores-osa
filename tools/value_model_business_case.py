"""Write docs/BUSINESS_CASE.md and evidence/metrics/value_model.csv from the measured baseline.

  uv run python tools/value_model_business_case.py --refresh-run <bigbox_refresh run> \
      --train-run <bigbox_ml_train run> --warehouse-id <id>

Measured (SQL on the warehouse, nothing typed): each loss lever's annual cost over the 365 days of
history (gold tables and metric views), its reduction in the backtest (ml.backtest_daily, ML policy
vs incumbent on the 8 held-out weeks), today's KPIs, tonight's queue and the decisions recorded, and
the run cost (system.billing.usage x system.billing.list_prices, via scripts/evidence_cost.py).
Modelled (illustrative): capture rates, company revenue scales and the KPI links, all named in
src/value/business_case.yaml and src/value/assumptions.yaml.
"""

import argparse
import csv
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src" / "value"), str(ROOT / "src" / "ml")]
import evidence_cost  # noqa: E402
from evidence_governance import Sql  # noqa: E402
from evidence_ml import H0, H_END, HIST0  # noqa: E402
from write_evidence import HOST, code_hash, git_commit  # noqa: E402

import business_case as bc  # noqa: E402
import cost_model  # noqa: E402
import value_model  # noqa: E402
from bigbox_ml.policy import Policy  # noqa: E402

CAT = "bigbox_fe_bar"
DOC = ROOT / "docs" / "BUSINESS_CASE.md"
CSV = ROOT / "evidence" / "metrics" / "value_model.csv"
CODE = [
    "tools/value_model_business_case.py",
    "src/value/business_case.py",
    "src/value/business_case.yaml",
    "src/value/assumptions.yaml",
    "src/value/value_model.py",
    "src/value/cost_model.py",
    "src/value/cost_assumptions.yaml",
    "scripts/evidence_cost.py",
]
UC = [
    f"{CAT}.gold.store_sku_daily",
    f"{CAT}.gold.forecast",
    f"{CAT}.serving.availability_kpis",
    f"{CAT}.serving.sales_kpis",
    f"{CAT}.gold.replenishment_fill",
    f"{CAT}.gold.recommendations",
    f"{CAT}.gold.reorder_decisions",
    f"{CAT}.ml.backtest_daily",
    "system.billing.usage",
    "system.billing.list_prices",
]


def f(x) -> float:
    return float(x or 0)


def pct(x: float, d: int = 1) -> str:
    return f"{100 * x:.{d}f}%"


def pct2(x: float) -> str:
    """A modelled share, two significant figures."""
    return f"{bc.sig(100 * x, 2):g}%"


def pts(x: float) -> str:
    return f"{100 * x:+.1f} pts"


def table(head: list[str], rows: list[list]) -> list[str]:
    return [
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
        *("| " + " | ".join(map(str, r)) + " |" for r in rows),
    ]


def kpi_count() -> int:
    """Measures defined once in the two metric views (src/governance/03_serving.sql)."""
    sql = (ROOT / "src" / "governance" / "03_serving.sql").read_text()
    n = 0
    for view in sql.split("WITH METRICS")[1:]:
        block = view.split("measures:", 1)[1].split("$$", 1)[0]
        n += len(re.findall(r"^  - name: ", block, re.M))
    return n


def measure(sql: Sql) -> dict:
    hist = f"BETWEEN '{HIST0}' AND '{H_END}'"
    hold = f"BETWEEN '{H0}' AND '{H_END}'"
    m = {}
    r = sql.rows(
        f"""SELECT sum(revenue), sum((expired_units + damaged_units) * unit_cost),
                   sum(closing_on_hand * unit_cost) / count(DISTINCT date), count(DISTINCT date),
                   count(DISTINCT store_id), count(DISTINCT sku_id)
              FROM {CAT}.gold.store_sku_daily WHERE date {hist}"""
    )[0]
    m["revenue"], m["waste"], m["inventory"] = f(r[0]), f(r[1]), f(r[2])
    m["days"], m["stores"], m["skus"] = int(r[3]), int(r[4]), int(r[5])
    r = sql.rows(
        f"""SELECT sum(f.lost_sales), sum(f.lost_sales_units * (p.unit_price - p.unit_cost)),
                   sum(IF(f.date {hold}, f.lost_sales, 0))
              FROM {CAT}.gold.forecast f JOIN {CAT}.silver.products p USING (sku_id)
             WHERE f.date {hist}"""
    )[0]
    m["lost_sales"], m["lost_margin"], m["lost_sales_holdout_est"] = map(f, r)
    r = sql.rows(
        f"""SELECT MEASURE(on_shelf_availability), MEASURE(in_stock_pct), MEASURE(shrink_pct),
                   MEASURE(online_fill_rate), MEASURE(lost_sales_units), MEASURE(units_sold),
                   MEASURE(stockout_hours)
              FROM {CAT}.serving.availability_kpis WHERE date {hist}"""
    )[0]
    m["osa"], m["in_stock"], m["shrink"], m["online_fill"] = map(f, r[:4])
    m["lost_units_share"] = f(r[4]) / (f(r[4]) + f(r[5]))
    m["stockout_hours"] = f(r[6])
    m["avg_discount"] = f(
        sql.rows(
            f"SELECT MEASURE(avg_discount) FROM {CAT}.serving.sales_kpis WHERE sale_date {hist}"
        )[0][0]
    )
    r = sql.rows(
        f"""SELECT sum(received_qty_ea) / sum(ordered_qty), avg(IF(days_late > 0, 1, 0))
              FROM {CAT}.gold.replenishment_fill WHERE due_date {hist}"""
    )[0]
    m["supplier_fill"], m["late_share"] = map(f, r)
    r = sql.rows(
        f"""SELECT count(*), sum(IF(queue_reason IS NOT NULL, 1, 0)), max(as_of_ts)
              FROM {CAT}.gold.recommendations"""
    )[0]
    m["ranged"], m["queue"], m["queue_as_of"] = int(r[0]), int(r[1]), r[2]
    m["decisions"] = {
        (x[0], x[1]): int(x[2])
        for x in sql.rows(
            f"""SELECT IF(decided_by = 'stage-d-evidence', 'stage-D check', 'app session'), action,
                       count(*) FROM {CAT}.gold.reorder_decisions GROUP BY 1, 2"""
        )
    }
    sl = Policy.load().service_level
    m["service_level"] = sl
    bt = sql.rows(
        f"""SELECT policy, 1 - sum(stockout_hours) / sum(trading_hours),
                   sum(in_stock_at_close) / sum(cell_days), sum(lost_units) / sum(demand_units),
                   sum(IF(perishable, expired_units + damaged_units, 0)) / sum(IF(perishable, received_units, 0)),
                   sum(IF(segment = 'slow', closing_units, 0)) / sum(IF(segment = 'slow', sold_units, 0)),
                   sum(lost_sales), sum(lost_margin), sum(waste_cost), sum(closing_cost),
                   count(DISTINCT date), sum(IF(perishable AND segment = 'other', lost_units, 0))
                     / sum(IF(perishable AND segment = 'other', demand_units, 0))
              FROM {CAT}.ml.backtest_daily
             WHERE policy IN ('history', 'incumbent') OR (policy = 'ml' AND service_level = {sl})
             GROUP BY 1"""
    )
    keys = ["osa", "in_stock", "lost_units_share", "shrink", "slow_dos", "lost_sales"]
    keys += ["lost_margin", "waste", "closing_cost", "days", "fast_perishable_lost_share"]
    m["bt"] = {x[0]: dict(zip(keys, map(f, x[1:]), strict=True)) for x in bt}
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-run", required=True)
    ap.add_argument("--train-run", required=True)
    ap.add_argument("--warehouse-id", required=True)
    args = ap.parse_args()
    sql = Sql(os.environ["DATABRICKS_CONFIG_PROFILE"], args.warehouse_id)
    m = measure(sql)
    cost = evidence_cost.measure(sql, args.warehouse_id, args.refresh_run, args.train_run)
    a, va, ca = bc.load(), value_model.load(), cost_model.load()
    inc, ml, hist = m["bt"]["incumbent"], m["bt"]["ml"], m["bt"]["history"]

    def red(k: str) -> float:
        return 1 - ml[k] / inc[k]

    annual = {
        "lost_margin": m["lost_margin"],
        "waste": m["waste"],
        "carrying": m["inventory"] * va["inventory_carrying_cost_rate"],
    }
    levers = bc.levers(
        a, annual, {k: red(k) for k in ("lost_margin", "waste")} | {"carrying": red("closing_cost")}
    )
    lv = {x.key: x for x in levers}
    rev0 = va["company_annual_revenue_usd"]
    scale = rev0 / m["revenue"]
    revenues = va["sensitivity"]["company_annual_revenue_usd"]
    sens = bc.sensitivity(levers, m["revenue"], revenues)
    run = {
        r: cost_model.monthly_cost(cost["units"], ca, revenue_scale=r / m["revenue"])["total"] * 12
        for r in revenues
    }
    run_slice = cost_model.monthly_cost(cost["units"], ca)["total"] * 12
    mid = bc.total(levers, "mid", scale)
    k_m, k_w, k_c = (lv[k].kept["mid"] for k in ("lost_margin", "waste", "carrying"))
    hold_days = int(inc["days"])
    # The value model's headline (03b) on the same inputs, for the reconciliation.
    pt = {
        p: value_model.PolicyTotals(
            hold_days,
            m["bt"][p]["lost_sales"],
            m["bt"][p]["lost_margin"],
            m["bt"][p]["waste"],
            m["bt"][p]["closing_cost"],
        )
        for p in ("incumbent", "ml")
    }
    v03 = value_model.annual_value(pt["incumbent"], pt["ml"], m["revenue"], va)
    est_vs_truth = m["lost_sales_holdout_est"] / hist["lost_sales"]
    per_year = va["annualise_from_days"] / hold_days
    holdout_vs_year = m["lost_sales_holdout_est"] * per_year / m["lost_sales"]

    rows: list[list] = []  # CSV: section, metric, case, value, unit, basis, source

    def out(section, metric, case, value, unit, basis, source, n: int | None = 3):
        """n significant figures; None keeps a measured count or billed amount exact."""
        v = value if n is None else bc.sig(value, n)
        rows.append([section, metric, case, f"{v:.10g}", unit, basis, source])

    lever_src = {
        "lost_margin": f"gold.forecast lost units x (price - cost), {m['days']} days",
        "waste": f"gold.store_sku_daily (expired + damaged) x cost, {m['days']} days",
        "carrying": "gold.store_sku_daily mean inventory at cost x carrying rate",
    }
    for x in levers:
        basis = "measured x assumed rate" if x.key == "carrying" else "measured"
        out(
            "lever",
            f"{x.key} annual cost (slice)",
            "",
            x.annual_cost,
            "usd/yr",
            basis,
            lever_src[x.key],
        )
        out(
            "lever",
            f"{x.key} backtest reduction",
            "",
            x.backtest_reduction,
            "share",
            "measured",
            "ml.backtest_daily",
        )
        for c in bc.CASES:
            out(
                "lever",
                f"{x.key} capture rate",
                c,
                x.capture(c),
                "share",
                "illustrative",
                "kept x backtest reduction",
                2,
            )
            out(
                "lever",
                f"{x.key} value at {bc.usd(rev0)}",
                c,
                x.value(c, scale),
                "usd/yr",
                "illustrative",
                "capture x annual cost x revenue scale",
                2,
            )
    out(
        "revenue",
        "slice revenue",
        "",
        m["revenue"],
        "usd/yr",
        "measured",
        f"gold.store_sku_daily, {m['days']} days",
    )
    for c in bc.CASES:
        out(
            "total",
            "value as share of revenue",
            c,
            bc.share_of_revenue(levers, c, m["revenue"]),
            "share",
            "illustrative",
            "levers / slice revenue",
            2,
        )
    for s in sens:
        for c in bc.CASES:
            out(
                "sensitivity",
                f"value at {bc.usd(s['revenue'])}",
                c,
                s[c],
                "usd/yr",
                "illustrative",
                "linear in revenue",
                2,
            )
        out(
            "sensitivity",
            f"run cost at {bc.usd(s['revenue'])}",
            "",
            run[s["revenue"]],
            "usd/yr",
            "illustrative",
            "measured unit costs x cost_assumptions.yaml",
            2,
        )
    out(
        "cost",
        "build cost to date",
        "",
        round(cost["total"], 2),
        "usd",
        "measured",
        "system.billing.usage x list_prices",
        None,
    )
    out(
        "cost",
        "one refresh run",
        "",
        round(cost["refresh_usd"], 2),
        "usd",
        "measured",
        "system.billing.usage x list_prices",
        None,
    )

    # Stakeholder KPIs, mid case at the headline revenue. Rates are shown before and after, with
    # the change computed from the rounded values so the row reads consistently.
    def move(today: float, after: float) -> str:
        t, a_ = round(100 * today, 1), round(100 * after, 1)
        return f"{a_:.1f}% ({a_ - t:+.1f} pts)"

    rd = m["decisions"]
    app_n = sum(v for (who, _), v in rd.items() if who == "app session")
    app_ok = rd.get(("app session", "approve"), 0)
    chk_n = sum(v for (who, _), v in rd.items() if who == "stage-D check")
    lost_units_red = 1 - ml["lost_units_share"] / inc["lost_units_share"]
    rates = [  # label, today (measured), mid (illustrative), link
        ("on-shelf availability", m["osa"], m["osa"] + (ml["osa"] - inc["osa"]) * k_m, "link 1"),
        (
            "in-stock at close",
            m["in_stock"],
            m["in_stock"] + (ml["in_stock"] - inc["in_stock"]) * k_m,
            "link 1",
        ),
        (
            "lost units share of demand",
            m["lost_units_share"],
            m["lost_units_share"] + (ml["lost_units_share"] - inc["lost_units_share"]) * k_m,
            "link 1",
        ),
        (
            "perishable shrink",
            m["shrink"],
            m["shrink"] + (ml["shrink"] - inc["shrink"]) * k_w,
            "link 1",
        ),
        (
            "online fill rate",
            m["online_fill"],
            1 - (1 - m["online_fill"]) * (1 - lost_units_red * k_m),
            "links 1, 4",
        ),
    ]
    r_ = {x[0]: x for x in rates}
    for label, today, after, link in rates:
        out(
            "kpi",
            label,
            "today",
            today,
            "share",
            "measured",
            f"serving.availability_kpis, {m['days']} days",
        )
        out("kpi", label, "mid", after, "share", "illustrative", link)
    loss0 = sum(annual.values()) * scale
    w_chg = -lv["waste"].value("mid", scale)
    c_chg = -lv["carrying"].value("mid", scale)
    i0 = m["inventory"] * scale
    di = -lv["carrying"].capture("mid") * i0
    so_chg = m["stockout_hours"] * ((1 - ml["osa"]) / (1 - inc["osa"]) - 1) * k_m
    rec_rev = m["lost_sales"] * lv["lost_margin"].capture("mid") * scale
    at = f"at {bc.usd(rev0)}"
    kp = [  # stakeholder, KPI, today (measured), mid case (illustrative), assumption
        [
            "Executive sponsor (COO)",
            "Gross margin",
            f"the three levers cost {bc.usd(sum(annual.values()), 3)}/yr in the slice ({bc.usd(loss0)} {at})",
            f"+{bc.usd(mid)}/yr ({bc.sig(1e4 * mid / rev0, 2):g} bps of revenue)",
            "links 1-3",
        ],
        [
            "",
            "Revenue recovered (top line, at list price)",
            f"{bc.usd(m['lost_sales'], 3)}/yr lost to stockouts in the slice",
            f"+{bc.usd(rec_rev)}/yr; its margin is in the line above",
            "links 1-3",
        ],
        [
            "",
            "Cost line: goods written off (at cost)",
            f"{bc.usd(m['waste'], 3)}/yr in the slice",
            f"{bc.usd(w_chg)}/yr",
            "links 1-3",
        ],
        [
            "",
            "Cost line: inventory carrying cost",
            f"{bc.usd(annual['carrying'], 3)}/yr in the slice",
            f"+{bc.usd(c_chg)}/yr" if c_chg > 0 else f"{bc.usd(c_chg)}/yr",
            "links 2, 3, 6",
        ],
        [
            "",
            "Working capital (average inventory at cost)",
            f"{bc.usd(m['inventory'], 3)} in the slice ({bc.usd(i0)} {at})",
            (f"+{bc.usd(di)}: more stock held, not less" if di > 0 else bc.usd(di)),
            "links 3, 6",
        ],
        [
            "",
            "Run cost and return",
            f"{bc.usd(cost['total'], 3)} to build so far (list price)",
            f"{bc.usd(run[rev0])}/yr to run {at}; {bc.sig(mid / run[rev0], 2):g} $ of value per $",
            "cost_assumptions.yaml",
        ],
        [
            "",
            "Platform consolidation (two BI tools)",
            "two sets of KPI logic",
            "one definition per KPI; licence and effort savings not valued (no data)",
            "-",
        ],
        [
            "Domain owner (Director of Operations)",
            "On-shelf availability",
            pct(m["osa"]),
            move(*r_["on-shelf availability"][1:3]),
            "link 1",
        ],
        [
            "",
            f"Service level: in-stock at close (policy target {m['service_level']:g})",
            pct(m["in_stock"]),
            move(*r_["in-stock at close"][1:3]),
            "link 1",
        ],
        [
            "",
            "Stockout hours, store-SKU (slice)",
            f"{bc.sig(m['stockout_hours'], 3):,.0f}/yr",
            f"{bc.sig(so_chg, 2):+,.0f}/yr",
            "link 1",
        ],
        [
            "",
            "Lost units, share of demand",
            pct(m["lost_units_share"]),
            move(*r_["lost units share of demand"][1:3])
            + ": cheaper units lost, dearer ones saved",
            "link 1",
        ],
        ["", "Perishable shrink", pct(m["shrink"]), move(*r_["perishable shrink"][1:3]), "link 1"],
        [
            "",
            "Online fill rate",
            pct(m["online_fill"]),
            move(*r_["online fill rate"][1:3]),
            "links 1, 4",
        ],
        [
            "",
            "Supplier fill (received / ordered eaches)",
            pct(m["supplier_fill"]),
            "unchanged: the solution does not act on suppliers, which caps capture",
            "-",
        ],
        ["", "Penalties (supplier or customer)", "not in the synthetic data", "not valued", "-"],
        [
            "",
            "Decision coverage",
            f"{m['queue']:,} queue items tonight ({pct(m['queue'] / m['ranged'], 0)} of {m['ranged']:,} store-SKUs); "
            f"decisions so far: {app_n} in a real app session ({app_ok} approved as recommended), {chk_n} from the stage-D check",
            f"about {bc.sig(m['queue'] * k_m, 2):,.0f} items a night actioned as recommended "
            f"(~{bc.sig(m['queue'] * k_m / m['stores'], 2):g} per store)",
            "link 5",
        ],
        [
            "Platform owner (Head of Data)",
            "KPI definitions",
            f"{kpi_count()} measures in 2 metric views",
            "the same definitions behind Genie and the app",
            "-",
        ],
        [
            "",
            "Freshness",
            "nightly batch before the build",
            f"every {1440 // ca['refresh_runs_per_day']} minutes (the refresh schedule)",
            "-",
        ],
        [
            "",
            "Run cost",
            f"{bc.usd(cost['refresh_usd'], 2)} per refresh",
            f"{bc.usd(run_slice)}/yr for the slice, {bc.usd(run[rev0])}/yr {at}",
            "cost_assumptions.yaml",
        ],
        [
            "",
            "Cost attribution by tag",
            f"{pct(cost['tagged'] / cost['total'], 0)} of build cost carries the project tag",
            "all of it once a serverless usage policy carries the tag",
            "-",
        ],
    ]
    out(
        "kpi",
        "queue items tonight",
        "today",
        m["queue"],
        "items",
        "measured",
        "gold.recommendations",
        None,
    )
    out(
        "kpi",
        "decisions recorded",
        "today",
        sum(rd.values()),
        "decisions",
        "measured",
        "gold.reorder_decisions",
        None,
    )
    out("kpi", f"gross margin {at}", "mid", mid, "usd/yr", "illustrative", "levers", 2)
    out("kpi", f"working capital change {at}", "mid", di, "usd", "illustrative", "link 6", 2)
    out(
        "kpi",
        f"value per $ of run cost {at}",
        "mid",
        mid / run[rev0],
        "ratio",
        "illustrative",
        "levers / run cost",
        2,
    )

    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    commit = git_commit()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", *CODE], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    md = [
        "# Business case: Bigbox Stores near-real-time on-shelf availability",
        "- Command: `uv run python tools/value_model_business_case.py --refresh-run "
        f"{args.refresh_run} --train-run {args.train_run} --warehouse-id {args.warehouse_id}`",
        f"- Run at: {now} (UTC); billing data through {cost['latest'][0]}",
        f"- Workspace: {HOST}",
        "- UC objects: " + ", ".join(f"`{x}`" for x in UC),
        f"- Git commit: `{commit}`"
        + (" plus uncommitted changes" if dirty else "")
        + f"; source sha256 `{code_hash([str(ROOT / c) for c in CODE])}` over {', '.join(CODE)}",
        "",
        "Generated by the command above: nothing here is typed. **Measured** numbers come from the "
        f"synthetic data ({m['days']} days of history in the gold tables, the backtest on the {hold_days // 7} held-out weeks) "
        "and from billing. Everything marked **illustrative** is modelled: a measured number times "
        "an assumption named in `src/value/business_case.yaml` or `src/value/assumptions.yaml`. "
        "Modelled figures are rounded to two significant figures and measured ones to three. The "
        "machine-readable copy is `evidence/metrics/value_model.csv`.",
        "",
        "## 1. The loss levers and what they cost today (measured)",
        "",
        f"The modelled slice is {m['stores']} stores x {m['skus']} SKUs, with "
        f"{bc.usd(m['revenue'], 3)} revenue over {m['days']} days ({HIST0} to {H_END}). At "
        f"{bc.usd(rev0)} company revenue every slice dollar scales by x{bc.sig(scale, 3):g} "
        "(illustrative, link 3).",
        "",
    ]
    md += table(
        [
            "lever",
            "annual cost, slice (measured)",
            "share of slice revenue",
            f"at {bc.usd(rev0)} (illustrative)",
            "how it is measured",
        ],
        [
            [
                lv["lost_margin"].name,
                bc.usd(annual["lost_margin"], 3),
                pct(annual["lost_margin"] / m["revenue"]),
                bc.usd(annual["lost_margin"] * scale),
                "`gold.forecast` lost units x (list price - unit cost)",
            ],
            [
                lv["waste"].name,
                bc.usd(annual["waste"], 3),
                pct(annual["waste"] / m["revenue"]),
                bc.usd(annual["waste"] * scale),
                "`gold.store_sku_daily` (expired + damaged units) x unit cost",
            ],
            [
                lv["carrying"].name,
                bc.usd(annual["carrying"], 3),
                pct(annual["carrying"] / m["revenue"]),
                bc.usd(annual["carrying"] * scale),
                f"mean daily closing inventory at cost {bc.usd(m['inventory'], 3)} x assumed "
                f"{va['inventory_carrying_cost_rate']:.0%}/yr",
            ],
        ],
    )
    md += [
        "",
        f"Lost sales at revenue (list price) are {bc.usd(m['lost_sales'], 3)} a year in the slice; "
        "the case values them at margin only. Online short shipments are not a separate lever: "
        "online orders ship from store stock, so they sit inside the stockout lever already.",
        "",
        "## 2. Capture rate per lever (illustrative)",
        "",
        f"Capture = measured backtest reduction (ML policy at service level {m['service_level']:g} vs "
        "the incumbent, same true demand and supplier draws) x the share of it production keeps "
        "(assumed).",
        "",
    ]
    md += table(
        [
            "lever",
            "backtest reduction (measured)",
            "case",
            "kept (assumed)",
            "capture",
            f"value at {bc.usd(rev0)}/yr",
            "why",
        ],
        [
            [
                x.name if c == "low" else "",
                pct(x.backtest_reduction) if c == "low" else "",
                c,
                f"{x.kept[c]:.0%}",
                pct2(x.capture(c)),
                bc.usd(x.value(c, scale)),
                x.why[c],
            ]
            for x in levers
            for c in bc.CASES
        ],
    )
    md += [
        "",
        "The carrying lever is negative: at this service level the ML policy holds "
        f"{pct(-red('closing_cost'))} more inventory at cost than the incumbent. Its lower waste "
        "comes from perishables, and its availability gain needs more stock on slow movers.",
        "",
        "## 3. Total, as a share of revenue, and sensitivity (illustrative)",
        "",
    ]
    md += table(
        ["case", "total as share of revenue", f"total at {bc.usd(rev0)}"],
        [
            [
                c,
                f"{pct2(bc.share_of_revenue(levers, c, m['revenue']))} "
                f"({bc.sig(1e4 * bc.share_of_revenue(levers, c, m['revenue']), 2):g} bps)",
                bc.usd(bc.total(levers, c, scale)),
            ]
            for c in bc.CASES
        ],
    )
    md += [
        "",
        "At assumed company revenue scales (link 3: losses are the same share of revenue at "
        "every size; run cost from measured unit costs x `cost_assumptions.yaml`):",
        "",
    ]
    md += table(
        ["company revenue", "low", "mid", "high", "run cost/yr", "mid, net of run cost"],
        [
            [
                bc.usd(s["revenue"]),
                bc.usd(s["low"]),
                bc.usd(s["mid"]),
                bc.usd(s["high"]),
                bc.usd(run[s["revenue"]]),
                bc.usd(s["mid"] - run[s["revenue"]]),
            ]
            for s in sens
        ],
    )
    md += [
        "",
        "## 4. The mid case in each stakeholder's KPIs (illustrative)",
        "",
        f"Mid case at {bc.usd(rev0)} revenue. KPIs that are rates are the same at any scale; "
        f'"today" is measured over the {m["days"]} days of history.',
        "",
    ]
    md += table(
        ["stakeholder", "KPI", "today (measured)", "mid case (illustrative)", "assumption"], kp
    )
    md += ["", "Assumptions that link a dollar lever to a KPI (`business_case.yaml`, `links`):", ""]
    md += [f"{i}. {t}" for i, t in enumerate(a["links"], 1)]
    md += [
        "",
        "## 5. Run cost (measured)",
        "",
        "`system.billing.usage` x `system.billing.list_prices` (list price) for this build's resources, "
        "attributed by resource id (see `evidence/07_cost.md`):",
        "",
    ]
    md += table(
        ["component", "list $ to date"],
        [[c[0], evidence_cost.money(c[3])] for c in cost["comp"]]
        + [["**total**", f"**{evidence_cost.money(cost['total'])}**"]],
    )
    md += [
        "",
        f"Most of it is build-time querying on the shared Large warehouse. One 15-minute refresh costs "
        f"{bc.usd(cost['refresh_usd'], 2)} (measured, run `{args.refresh_run}`). Running it costs "
        f"{bc.usd(run_slice)}/yr at the slice and {bc.usd(run[rev0])}/yr at {bc.usd(rev0)} "
        "(illustrative: measured unit costs x `cost_assumptions.yaml`).",
        "",
        "## 6. Reconciliation with the value model in 03b",
        "",
        f"`evidence/03b_backtest_value.md` reports {bc.usd(v03['total'])}/yr. It annualises the "
        f"backtest's dollar deltas from the {hold_days // 7} held-out weeks (x{bc.sig(per_year, 3):g}) using the generator's "
        f"true lost sales, and keeps {va['realisation']:.0%} of every lever. This case reports "
        f"{bc.usd(mid)}/yr. It applies the backtest's percentage reductions to the full year's "
        "pipeline-measured cost and keeps "
        f"{k_m:.0%} of lost margin, {k_w:.0%} of waste and {k_c:.0%} of carrying. The value per $ of "
        f"run cost is {bc.sig(mid / run[rev0], 2):g} here against {bc.sig(v03['total'] / run[rev0], 2):g} in "
        "`evidence/07_cost.md`. Three things account for the gap:",
        "",
        f"- Over the holdout, the pipeline's lost-sales estimate in dollars is {pct(est_vs_truth, 0)} of the true "
        f"lost sales in the backtest's replay of the generator's own run (`03_ml.md` compares the same in units; "
        f"here {bc.usd(m['lost_sales_holdout_est'], 3)} vs {bc.usd(hist['lost_sales'], 3)}).",
        f"- The held-out weeks lose more than the average week: annualised, they come to "
        f"{pct(holdout_vs_year, 0)} of the full year's estimate.",
        f"- Waste is kept at {k_w:.0%}, not {va['realisation']:.0%}.",
        "",
        "## 7. What would make these numbers wrong",
        "",
        "- **The world is synthetic.** The baseline, the backtest and the policy share one generator, so "
        "real demand will be noisier, and real stockouts will have causes the simulator lacks "
        "(phantom inventory, backroom stock, planogram gaps).",
        f"- **The lost-sales baseline is an estimate.** Where truth exists (the holdout), the dollar estimate "
        f"is {pct(1 - est_vs_truth, 0)} below it, which makes this case conservative. In production there "
        "is no truth to calibrate against.",
        f"- **Margin is at list price.** The measured average discount is {pct(m['avg_discount'])}. At "
        f"net price the lost-margin lever is {pct(m['avg_discount'] * m['lost_sales'] / m['lost_margin'], 0)} smaller.",
        f"- **{hold_days // 7} weeks stand for a year.** The percentage reductions come from {hold_days} days "
        f"({H0} to {H_END}), with no peak season and no assortment change.",
        f"- **Linear scaling.** From {bc.usd(min(revenues))} to {bc.usd(max(revenues))}, the case assumes a bigger retailer loses the same share "
        "of revenue, with the same mix of slow movers and perishables as the slice.",
        f"- **The kept shares are guesses.** Adoption has not been measured: {app_n} app-session "
        f"decisions, {app_ok} of them approved as recommended. The mid case needs about half of "
        "tonight's queue actioned as recommended every night (link 5).",
        f"- **Planners may undo the waste gain.** On fast-moving perishables the ML policy's lost-units "
        f"share rises from {pct(inc['fast_perishable_lost_share'])} to {pct(ml['fast_perishable_lost_share'])} "
        "in the backtest. Planners who see those stockouts will override upward, which is why waste is kept at less than half.",
        f"- **Units and dollars move in opposite directions.** The lost-units share rises "
        f"({pts(ml['lost_units_share'] - inc['lost_units_share'])} in the backtest) while lost dollars "
        "fall, so the online fill rate, which counts units, drops slightly under link 4. A KPI owner who "
        "tracks units will see it get worse.",
        f"- **Working capital rises.** At service level {m['service_level']:g} the policy holds more "
        "inventory, not less. A lower service level trades availability for inventory (03b shows the levels side by side).",
        f"- **Suppliers.** The backtest replays today's supplier draws (measured fill {pct(m['supplier_fill'])}, "
        f"{pct(m['late_share'], 0)} of lines late). Extra orders that suppliers cannot fill lower capture.",
        "- **Not valued (upside, or zero):** consolidating the two BI tools, intraday expediting, markdowns, "
        "planner labour and penalties. None of them is in the synthetic data.",
        "- **Run cost is at list price, on a shared Large warehouse,** with cost_assumptions.yaml hours. "
        "Discounts lower it; heavier Genie use raises it.",
    ]
    DOC.write_text("\n".join(md) + "\n")
    CSV.parent.mkdir(parents=True, exist_ok=True)
    with CSV.open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["section", "metric", "case", "value", "unit", "basis", "source"])
        w.writerows(rows)
    print(
        f"wrote {DOC.relative_to(ROOT)} ({DOC.stat().st_size:,} bytes), "
        f"{CSV.relative_to(ROOT)} ({len(rows)} rows, {CSV.stat().st_size:,} bytes)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
