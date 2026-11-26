# Bigbox Stores: reorder the right items, today

For the COO and the Director of Operations. Every number links to its evidence file in
[`evidence/`](../evidence/INDEX.md); all results are on simulated data from a seeded generator.

---

## The outcome

Over 8 held-out weeks, on the same simulated demand and the same suppliers, the ML reorder policy
against today's nightly policy ([backtest](../evidence/03b_backtest_value.md)):

| measure | today's policy | ML policy | change |
|---|---|---|---|
| lost sales to stockouts | $5,416,201 | $3,588,351 | −33.7 % |
| on-shelf availability | 92.66 % | 94.82 % | +2.16 pts |
| in-stock at close | 90.94 % | 92.92 % | +1.98 pts |
| perishable shrink | 10.56 % | 6.98 % | −33.9 % |

- **Value (illustrative):** about **$7.1M a year** at a ~$1B retailer in the mid case ($3.5M low, $11M
  high). That is the full year's measured losses at margin (stockouts, waste, carrying) times an assumed
  capture rate per lever ([business case](../docs/BUSINESS_CASE.md)). Annualising the 8 held-out weeks
  instead gives $11.0M ([value model](../evidence/03b_backtest_value.md)).
- **Watch-outs, from the same case:** the policy holds more inventory, not less; it loses more cheap
  units while saving dearer ones; adoption is not yet measured.
- **Run cost and ROI:** $218,468 a year at company scale (modelled: a refresh every 15 minutes, the app around the clock, the endpoint and the SQL warehouse 12 hours a day; the shared Large warehouse is the largest item); **32 $ of value per $** of run
  cost in the mid case ([cost](../evidence/07_cost.md), [business case](../docs/BUSINESS_CASE.md)).
- **Time to value:** a stockout reaches the planner's queue within one 15-minute refresh; one run took
  about 8 minutes from new files to the queue ([Lakebase](../evidence/04_lakebase.md)). Today it is
  seen the next morning.

---

## What the Director of Operations gets

- **One screen:** availability, in-stock, lost sales, shrink, online fill and revenue for the last 7
  days against the 7 before, from the same governed KPI definitions everywhere.
- **Tonight's queue:** the store × SKUs at stockout risk or overstocked, most urgent first (expected
  lost sales), with the order the policy recommends.
- **What-if:** change an item's promotion or price and see its forecast in ~100 ms.
- **Decide:** approve, override (with a reason) or reject; every decision is recorded with who made it
  and flows back to the lakehouse, so adoption and overrides are measurable.
- **Ask:** questions in plain English through Genie, answered from the same KPIs, with the SQL shown.

Deployed and tested on its live URL, including a real session ([app](../evidence/06_app.md)).

---

## Decisions and trade-offs

- **Every 15 minutes, not streaming:** orders are placed nightly, so a 15-minute refresh is enough
  and far cheaper than an always-on stream; the same pipeline can switch to continuous later.
- **Learning true demand:** an empty shelf sells nothing, so the model only learns from days that
  never stocked out, and lost sales are estimated from the forecast on stocked-out hours.
- **A fair test:** both policies replay the identical simulated weeks; replaying history reproduces
  the reported KPIs exactly.
- **Service level 95 %:** set before the backtest, not tuned on it; 90 % and 98 % are shown as
  sensitivity. At 95 % the policy trades a few lost units on fast-moving fresh items for much less waste.
- **Governed once:** one definition per KPI (metric views), regional managers see only their region,
  buyer PII is masked; the app and Genie respect the same rules.
- **Fast operational reads:** the queue lives in Lakebase (Postgres), a synced copy that holds no
  personal data; decisions are written there and merged back to Delta.

---

## How AI was used to build this

- An AI coding agent built the platform end to end (generator, pipeline, governance, model, Lakebase,
  Genie, app, evidence) from a written brief, working in the workspace through the CLI.
- A human set the rules and approved every new resource and name; nothing was created outside an
  approved list, and the shared workspace's other assets were checked untouched after every session.
- The agent had to prove each claim with text copied from real runs (`evidence/`), and record its own
  failures; numbers come from queries, never typed.
- Inside the product, AI is the demand model (gradient-boosted trees chosen by an MLflow sweep) and
  Genie for natural-language questions, scored against reference answers (25 of 25 in each of 3 runs;
  64 % without the curation) ([Genie](../evidence/05_genie.md)).

---

## What went wrong

- **Checks that passed silently:** a pre-push secret/denylist check and an evidence hash both passed
  while not checking what they claimed; found by testing them, fixed.
- **A KPI with two definitions:** shrink counted only expired units in one place; fixed to the agreed
  definition (expired + damaged) everywhere.
- **Over-optimistic hypotheses:** the forecast-error target (−25 %) is impossible on this data (the
  noise floor is close to today's accuracy); the value shows up in the reorder decisions instead.
- **A claim from planning that was never true-tested** (about Lakebase and row filters): corrected to
  what holds by design.
- **Platform friction:** automatic retries despite "no retries", a CLI too old for one app binding,
  the app's first build needing grants that only exist after it is created; each fixed in the deploy.
- **Known limitation:** the app accepts an "override" equal to the recommendation (one such decision is
  recorded); left as is.

---

## 30 / 60 / 90 days to production

- **30 days:** connect the real point-of-sale, e-commerce and inventory databases with Lakeflow
  Connect (SQL Server change data capture) into the same bronze layer; run the pipeline and KPIs on
  real data alongside today's BI; validate the KPI definitions with finance and operations.
- **60 days:** train and backtest on real history; agree the service levels by category with buyers;
  pilot the queue and the decisions in a few stores per region, measuring adoption and overrides.
- **90 days:** roll out to all stores; publish adoption and realised impact from the written-back
  decisions; move the BI tools onto the metric views; add monitoring and alerting on data freshness and
  model drift.

---

## Out of scope (explicitly)

- Real SQL Server ingestion (designed as Lakeflow Connect CDC, not built).
- Sub-second streaming, RFID / IoT shelf sensors.
- Multi-echelon and distribution-centre inventory, supplier collaboration.
- Pricing and markdown optimisation, workforce tools.
- Replacing the existing BI tools (they can read the same metric views).
- Not built (later phases): an explainer agent for each recommendation, an online feature store, POS
  health monitoring, an AI/BI dashboard, a continuous-streaming demo.
