# Rubric audit: FE Bar and BUILD_PROMPT

- Audited: public repo `riteshpatel-db/bigbox-stores-osa`, `main` at `d79a4bb` (fresh anonymous clone), on 2026-11-26.
- Workspace (live, read-only): https://fevm-serverless-stable-ritesh.cloud.databricks.com.
- Yardsticks:
  - **FE Bar**: the spec as pasted by the user (section 1 of the FE Bar prompt). Sections 2–3 of that prompt are the
    scoping process; they are covered by `SCOPE.md`, which is private and not audited here.
  - **BP**: `BUILD_PROMPT.md`, sections 1–7, including every "Evidence →" line.
- Verdicts: **PASS** (proven by the cited file), **PARTIAL** (some of it proven, or proven with a deviation),
  **FAIL** (not met), **N/A** (out of scope by instruction). Strict: a claim that is only stated, with no real output
  behind it, is not a PASS.

**Update after the audit (2026-11-26).** The README now has a "How AI was used" section (G3 and the first half of
G24 for the README). The deck gaps G1, G2, G6 and G23 are addressed in a separate Google Slides deck, which is not in
this repository; `deck/deck.md` is unchanged. Every other gap stands as written.

## Method

1. **Literal greps over all history.** All of them ran on the fresh clone, over every commit's patches, commit
   messages, file names and remote branch names:
   - the private denylist term;
   - secret patterns (Databricks, GitHub and Slack tokens, AWS keys, private keys, JWTs, `password|secret|token = "…"`);
   - S3 bucket names;
   - private markers;
   - stubs (`TODO|FIXME|XXX|stub|placeholder|coming soon|NotImplementedError|tbd`).

   Every hit was read in its file, not counted.
2. **Fresh clone.** `git clone` over HTTPS with no credentials. Then `uv sync`, `ruff check`, `ruff format --check`,
   `pytest` and `scripts/check_evidence.py` ran on the clone. Every evidence header's source sha256 was recomputed
   with `scripts/write_evidence.code_hash`.
3. **Evidence reading.** Each `evidence/NN_*.md` was read in full against its BP "Evidence →" line.
4. **Live checks (read-only CLI and SQL).** These covered:
   - the pipeline (spec, tags, latest updates);
   - the jobs (schedules, tags, run triggers);
   - the endpoint state, the model aliases and the Lakebase project;
   - the synced-table state, the Genie space and the app state with its bindings and access list;
   - the service principals and the decisions in `gold.reorder_decisions`;
   - a re-listed workspace inventory, diffed against the private do-not-touch list.
5. **Not done.**
   - The Skills Navigator app page itself (go/fe-bar) is not indexed, so the validator's rubric prompt was not read.
     Read instead (section 1b): the FE Bar FAQ, two Skills Navigator validator tickets (SKNAV-707, SKNAV-805) and
     the FE Bar build kit that the pasted prompt comes from. Other people's build plans in the search results were
     deliberately not opened.
   - A replay of the deployment from an empty workspace.
   - Part 2 (the roleplay), by instruction.

## Summary

| | PASS | PARTIAL | FAIL | N/A |
|---|---|---|---|---|
| FE Bar (25 rows) | 20 | 4 | 0 | 1 |
| BUILD_PROMPT (62 rows) | 46 | 14 | 2 | 0 |

The integrated journey is real and proven end to end. All six layers are built, connected and live, and every stage
has evidence from real runs. The gaps cluster in four places:

1. **Reproducibility by a stranger.** The workspace host, warehouse name and Genie space id are hard-coded. Changing
   `.env` alone does not redeploy into another workspace, and the sequence has never been replayed from empty.
2. **Evidence-to-commit traceability.** Ten evidence headers say "none yet (first commit pending)". Of the eight
   recorded source hashes, only two reproduce from the committed code.
3. **The deck's framing for the FE Bar.** The deck has:
   - no section for the executive sponsor;
   - no mention of the FY27 outcome map;
   - no statement that this is a real customer's problem, anonymised;
   - a generic account of how AI was used.
4. **Small accuracy issues:**
   - a deck claim about app security;
   - two KPI definitions;
   - a mislabelled count in the business case;
   - stale shrink figures in 00/01.

## 1. FE Bar requirements

| # | Requirement (FE Bar spec) | Verdict | Proof | Notes |
|---|---|---|---|---|
| F1 | A **real customer problem** in a **specific industry** | PARTIAL | `README.md` "The problem and the decision improved"; `deck/deck.md` title and outcome | Retail (big-box, in-store and online) is specific and customer-facing. Nowhere does the repo or deck say the problem is drawn from a real customer engagement (anonymised); a reader sees only "Bigbox Stores is fictional" (`README.md:23`). |
| F2 | One integrated data journey **from a raw dataset** (synthetic or public) | PASS | `evidence/00_raw_data.md`, `README.md` Architecture (mermaid) | Seeded generator → UC volume → pipeline → … → app; determinism check "3862 files compared, 0 differ". |
| F3 | Lakeflow (ingest) | PASS | `evidence/01_lakeflow.md` | Serverless pipeline `bigbox_osa_pipeline`, Auto Loader bronze, expectations, quarantine; live: IDLE, last update COMPLETED 2026-11-25. |
| F4 | Unity Catalog (govern) | PASS | `evidence/02_unity_catalog.md`, `evidence/02b_catalog_metadata.md` | Personas proven by querying as each SP, row filter, PII mask, metric views = hand SQL, comments, tags, lineage. |
| F5 | Lakebase (operational serving) | PASS | `evidence/04_lakebase.md` | Synced table 28,005 = 28,005 rows, 0 differing values, p95 3.88 ms; decisions Postgres → Delta 20 → 20. Live: SYNCED_TABLE_ONLINE_NO_PENDING_UPDATE. |
| F6 | ML **or** GenAI (make it intelligent) | PASS | `evidence/03_ml.md`, `evidence/03b_backtest_value.md`, `src/ml/*.ipynb` (with outputs) | Six-candidate sweep, `@champion`/`@challenger` (live: v1/v2), batch scoring, backtest, endpoint parity 0.0. GenAI agent not built (P1). |
| F7 | A Genie agent (natural language) | PASS | `evidence/05_genie.md`, `src/genie/space.json` | 25/25 in each of 3 runs; ablation 16/25; live space "Bigbox Stores - Store Ops". |
| F8 | A Databricks App (surface it to the business) | PASS | `evidence/06_app.md` | Deployed URL smoke test PASS; real session from `apps logs`. Live: RUNNING, 4 bindings. |
| F9 | Layers **connected, not siloed** | PASS | `evidence/04_lakebase.md` (refresh tasks pipeline → features → score → sync, write_back), `evidence/06_app.md`, `evidence/05_genie.md` q23/q24, `evidence/02b_catalog_metadata.md` lineage | App reads Lakebase, calls the endpoint and embeds Genie; decisions flow back to Delta; Genie answers over the written-back decisions; lineage rows link the layers. |
| F10 | Plan for 4–8 hours | PARTIAL | `BUILD_PROMPT.md` §7 (≈8 h budget) | Hands-on time was not tracked; the calendar span is 2026-10-29 → 2026-11-26 across sessions. Not demonstrable either way. |
| F11 | Evidence it ran, **readable as text** (notebooks with outputs, logs, query results) | PASS | `evidence/*.md` (12 files), `src/ml/*.ipynb` and `src/lakebase/*.ipynb` (7 notebooks, every code cell but one import cell has output, 0 error outputs), `results/` | |
| F12 | Public GitHub repo (or folder upload) | PASS | anonymous clone of `riteshpatel-db/bigbox-stores-osa` | 167 tracked files; one branch `main`. |
| F13 | Deck as pdf / txt / md | PASS | `deck/deck.md` | No PDF (optional). |
| F14 | Deck **leads with the business outcome** | PASS | `deck/deck.md` "The outcome" (first section) | |
| F15 | Impact **quantified in the buyer's KPIs** | PASS | `deck/deck.md` outcome table (lost sales $, OSA, in-stock, shrink) and value / ROI / time to value | Each number links to evidence. |
| F16 | Value framed for **both the executive sponsor and the domain owner** | PARTIAL | `deck/deck.md` "What the Director of Operations gets"; `docs/BUSINESS_CASE.md` §4 | The domain owner has a section. The COO is named only in the deck's subtitle; no section speaks to the sponsor's KPIs (margin, working capital, run cost, consolidation). That framing exists in `BUSINESS_CASE.md` §4, but the deck does not carry it. |
| F17 | Optional: the AI assistant's conversation id | PASS | `docs/PROVENANCE.md:9-10` | Records this session's id only; the earlier scoping session (another agent, which wrote `SCOPE.md`) has no id recorded. |
| F18 | Part 2: AI roleplay | N/A | - | Pending; not audited by instruction. |
| F19 | Common failure avoided: an internal (not customer) problem | PASS | `README.md`, `deck/deck.md` | A retailer's reorder decision. |
| F20 | Common failure avoided: layers present but not connected | PASS | see F9 | |
| F21 | Common failure avoided: a narrative that skips business value | PASS | `README.md` "Outcome" and `deck/deck.md` both lead with value | |
| F22 | Tip: document decisions and trade-offs | PASS | `README.md` "Decisions and trade-offs", `deck/deck.md` same, `evidence/04_lakebase.md` "Trade-offs" | |
| F23 | Tip: put a number on the value, even if estimated | PASS | `docs/BUSINESS_CASE.md`, `evidence/03b_backtest_value.md`, `evidence/07_cost.md` | Modelled parts labelled illustrative. |
| F24 | Tip: document how you used AI (**tools, prompts, patterns**) | PARTIAL | `deck/deck.md` "How AI was used to build this"; `docs/PROVENANCE.md:9` | The deck says "an AI coding agent" without naming it; the tool is named only in PROVENANCE. No prompts or patterns are shown (the brief and the golden rules stay private). |
| F25 | Read the official FE Bar page / Skills Navigator for differences | PASS | section 1b | FAQ, validator tickets and build kit read 2026-11-26; the app page itself is not indexed. |

## 1b. Official sources: what differs from the pasted spec

Read 2026-11-26 through internal search:
- [FE Bar FAQ](https://docs.google.com/document/d/1QNSjA40GGpwrdmV8KxtnvDAN7_eQe5DgsaObpZvehnE), updated 2026-11-19;
- the Skills Navigator validator tickets SKNAV-707 (released in 1.16.0 on 2026-11-02) and SKNAV-805 (released in
  1.18.0 on 2026-11-24);
- the FE Bar build kit ("prompts from zero to submission"), which the pasted prompt is taken from.

| # | Source | What it adds or changes | Effect on this build |
|---|---|---|---|
| O1 | FAQ | **Deadline November 30** for most FEs; the AI Beta group has until **January 31, 2027**. | Four days from this audit unless you are in the Beta group. |
| O2 | FAQ | FE Bar = **one Databricks certification** + build + roleplay. A pass needs **every domain at Meets or Exceeds**; the roleplay passes at **75 %**. Resubmission is unlimited, with feedback in minutes. | The certification is outside this repo. A resubmission after fixes costs nothing. |
| O3 | FAQ | Submit a GitHub link **and** a local folder upload, plus the deck. Secrets are scanned automatically before scoring. An **attestation** of original work is required. Integrity checks include **commit-authorship verification**. AI tools are allowed if you can explain the work. | Secret scan: history is clean (B4). Authorship: all 4 commits are by `riteshpatel-db` with your work email, and each carries a `Co-authored-by: Isaac` trailer (AI assistance, which is allowed). The personal GitHub account is the only identity mismatch a check could flag; the work email ties it to you. |
| O4 | SKNAV-707 | The validator reads about **90 KB** of the repo, with about **40 KB reserved for evidence**. Evidence files rank above source code; long files keep their head and tail. Evidence folders are detected by name; `.md`, `.json`, `.jsonl`, `.txt`, `.log`, `.out` and PDF count as evidence. | `evidence/` is 78 KB, so the grader likely reads only about half of it. What it sees first matters: `INDEX.md`, then the stage files. |
| O5 | SKNAV-805 | Missing run evidence **no longer fails** a build. It lowers Build + AI Mindset, with a floor at Meets, and the scorecard shows "Run evidence: Found / Not found". | Evidence lifts the score rather than gating the pass; ours should read as "Found". |
| O6 | Build kit | README order: outcome and value, problem, connected journey, decisions and trade-offs, **how AI was used**, **evidence index**, how to run, limitations; every relative link resolves. | Links: all resolve (checked on the clone). The README has **no "How AI was used" section** (it is only in the deck), and it links the evidence index only from the stage table. |
| O7 | Build kit | Commit notebooks as `.ipynb` with outputs **plus a markdown export**. | No markdown exports: the 7 notebooks are `.ipynb` only. |
| O8 | Build kit | Deck of about 18 slides with one-line action titles. It includes the challenge in the buyer's words, where the money goes (a chart), answer first, what the executive sees (an app screenshot and the screen list), architecture, why Databricks, a demo section, results (**sponsor's KPIs, owner's KPIs**, assumptions and scale, honest limits, a 12-week pilot, **the ask**) and an appendix (evidence map, technical decisions). Numbers come from `BUSINESS_CASE.md`, labelled illustrative, in native tables. | `deck/deck.md` has 8 sections. Missing: the buyer's-words challenge, where the money goes, why Databricks, the sponsor's KPIs, the ask, the evidence-map appendix and an app screenshot. |
| O9 | Build kit | Package the upload folder with `git archive HEAD` (no `.venv`, caches or secrets). Draft the form answers outcome-first with traceable numbers. **Do not tick "AI Customer Challenge build"** unless it is one. | Not done yet; the form and upload come at submission. |
| O10 | Build kit | Traps: evidence that overclaims (for example, a point-in-time join the code didn't do); Genie scored by eye; the deployed app untested over HTTP. | Point-in-time join verified in code (`FeatureLookup(..., timestamp_lookup_key="date")` in `src/ml/02_train.ipynb`); Genie scored against reference SQL ×3; smoke test on the deployed URL. |

### By FE Bar domain (what the evidence supports; not a predicted rating)

- **Product.** All six products are used for what each is best at, with live proof: F3–F9.
  - Stronger than the minimum: personas proven as service principals, endpoint parity, a triggered synced table,
    Genie scored on 25 questions × 3 runs with an ablation.
- **Industry.** A retail decision (what to reorder, for which store and SKU, today), with retail KPIs and
  definitions.
  - Weaker: the FY27 Retail outcome map is missing from the README and the deck (in BP §3, not published), and the
    repo never says the problem is real (F1).
- **Build + AI mindset.** Evidence as text everywhere, failures recorded, honest negative findings (the WAPE
  hypothesis missed; inventory rises).
  - Weaker: the AI-usage story is thin (F24); evidence-to-commit traceability is incomplete (B1); redeploy by a
    stranger is unproven (B5).
- **Customer skills.** The deck leads with the outcome, quantifies it and has a domain-owner section.
  - Weaker: no executive-sponsor framing in the deck (F16), and one security overclaim a technical stakeholder
    would catch (G6).

## 2. BUILD_PROMPT requirements

### §1 Hard constraints

| # | Requirement | Verdict | Proof | Notes |
|---|---|---|---|---|
| B1 | Evidence is text, real output, with the header (command, run at, workspace, UC objects, **git commit**); limits ≤30 files, ≤9,000 chars each, ≤90,000 total | PARTIAL | `scripts/check_evidence.py` on the clone: 13 files, 78,043 chars, largest 8,721 | Content and limits PASS. See the traceability table below. |
| B2 | No stubs, placeholders, TODO modules, empty resources | PASS | stub grep on the clone | 6 hits, all benign: HTML input `placeholder=` hints (3), SQL `${…}` template placeholders (2), an oxlint rule name (1). |
| B3 | One seeded generator, fixed dates, byte-identical re-runs; never real data | PASS | `evidence/00_raw_data.md` "determinism check: 3862 files compared, 0 differ"; `tests/test_generator.py` | |
| B4 | No secrets; named profiles; `.env` untracked; `.env.example` empty; tokens at runtime | PASS | history secret scan: 0 hits; `git ls-files` has no `.env`; `.env.example` has 3 keys, all empty; `scripts/smoke_test_app.sh` mints its token at runtime | |
| B5 | Public, clone-readable; a stranger **redeploys with one command by changing `.env` only** | FAIL | `databricks.yml:31`, `databricks.yml:18`, `databricks.yml:23` | Readability PASS. Redeploy does not work from `.env` alone: (1) target host hard-coded (`databricks.yml:31`); (2) warehouse looked up by the name `FE_BAR_Ritesh` (`databricks.yml:18`, `scripts/smoke_test_app.sh:32`, defaults in `src/genie/score.py:209`, `src/genie/space.py:158`); (3) `genie_space_id` defaults to this workspace's space (`databricks.yml:23`) and `deploy.sh` never passes the id `space.py` creates, so the app's genie binding would point at a missing space; (4) the run order is 9 commands, not one; (5) `README.md` "How to reproduce" says the sequence "has not been replayed from an empty workspace". |
| B6 | The customer name appears nowhere | PASS | denylist grep: 0 hits in all patches and messages, 0 in file names, 0 in branch names, 0 in the clone tree | Genie and app text are in the repo (`src/genie/space.json`, `src/app/`), so they are covered; the live space title matches. |
| B7 | Every number traces; modelled numbers name their assumption; **generated, never typed** | PARTIAL | evidence files, `docs/BUSINESS_CASE.md`, `evidence/metrics/value_model.csv` (generated) | Prose copies in the README, deck and HANDOFF are hand-copied; the headline ones were checked against evidence today and match. Three issues: (a) drift is real: HANDOFF quoted $176.11 until 2026-11-26; (b) `BUSINESS_CASE.md` says "7 in a real app session", but live data shows 5 session decisions plus 2 smoke-test rejects; (c) `00_raw_data.md` and `01_lakeflow.md` report shrink as expired / received (9.41%), the definition fixed later to expired + damaged. |
| B8 | Record failures; they feed the deck's "what went wrong" | PASS | `working/BUILD_LOG.md` (private), `README.md` "What went wrong", `deck/deck.md` "What went wrong" | Except the calibration limitation the log says must be in the deck: see B57. |
| B9 | Verify, don't trust; test the deployed thing | PASS | `evidence/06_app.md` smoke test on the deployed URL; `evidence/03_ml.md` parity; `evidence/02_unity_catalog.md` persona queries | |
| B10 | Ask before committing, pushing, deleting, sharing, creating unlisted resources | PASS | `docs/PROVENANCE.md` (every resource with its approval), `working/BUILD_LOG.md` | A process requirement; its trail is in PROVENANCE. |
| B11 | Git author as configured; `prepush_check.sh` passes before every push | PASS | `git log --all`: 4 commits by `riteshpatel-db`; `prepush_check.sh` passed (denylist, secrets, authors) before `d79a4bb` | Author changed from BP's `ritesh-patel_data` to `riteshpatel-db` at the user's direction (public personal account). |

**Evidence-to-commit traceability (B1 detail).** The headers of 00, 00b, 01, 02, 02b, 03, 03b, 04, 05 and 06 say
`Git commit: none yet (first commit pending)` (07 and `BUSINESS_CASE.md` cite a commit). Recomputing each recorded
source sha256 over the clone:

| file | recorded | from the clone | verdict |
|---|---|---|---|
| 00_raw_data.md, 00b_live_drip.md | `dc83a4081880`, `73011715590b` | `fdf6393860e1` | differs (00 itself says `drip.py` changed afterwards) |
| 01_lakeflow.md, 02_unity_catalog.md, 02b_catalog_metadata.md | none | - | not verifiable |
| 03_ml.md, 03b_backtest_value.md | `c85c2a625f31` | `b192a510723a` | differs (`src/value` gained files later) |
| 04_lakebase.md | `7e2bd237dba9` | `048007680c2d` | differs |
| 05_genie.md | `710317e78b64` | `d67f10e20a5b` | differs |
| 06_app.md | `98b87a03c274` | `98b87a03c274` | matches |
| 07_cost.md | `853a5ea93a34` | `853a5ea93a34` | matches |
| docs/BUSINESS_CASE.md | `21ff2bf39ca1` | `4addcb0a35c8` | differs: the tool hashed **absolute** paths, so its hash depends on the machine (bug; relative paths give `4addcb0a35c8` locally and in the clone) |

The code under `src/generator`, `src/ml`, `src/lakebase` and `src/genie` has not changed since the first commit
`b0861fe`. The mismatches therefore mean the code changed between the evidence runs and that first commit, and no
commit reproduces the exact code those runs used.

### §2 Target workspace

| # | Requirement | Verdict | Proof | Notes |
|---|---|---|---|---|
| B12 | Only approved names created | PASS | live listing; `docs/PROVENANCE.md:53-56` | Extra resources (`bigbox_ml_train`, `bigbox_lakebase_check`, the MLflow experiment, helper tables) each have a recorded approval. |
| B13 | Do-not-touch inventory unchanged | PASS | `working/list_inventory.sh` re-run today vs `working/do_not_touch.private.txt` | Diff: 3 catalogs added by other users, 0 removed or renamed. The listing compares names, not grants or settings. |
| B14 | Serverless only; no clusters | PASS | live pipeline `serverless: true`; job tasks on serverless (`evidence/00`, `03`) | |
| B15 | `project=bigbox-stores-osa` tag on every job, pipeline and endpoint | PASS | live: all 5 jobs, the pipeline and the endpoint carry it; Lakebase per `evidence/04_lakebase.md` | |

### §3 Business problem and KPIs

| # | Requirement | Verdict | Proof | Notes |
|---|---|---|---|---|
| B16 | Problem, decision improved, outcome-map mapping | PARTIAL | `README.md` problem section | Problem and decision PASS. The FY27 outcome-map mapping (BP §3) appears in no committed file (`git grep "outcome map\|FY27"`: 0 hits). |
| B17 | KPIs implemented **once, in metric views**, with the exact definitions | PARTIAL | `src/governance/03_serving.sql`; `evidence/02_unity_catalog.md` (metric views = hand SQL) | 24 measures in 2 metric views. Two deviations: (a) `replenishment_fill_rate` is not in a metric view; Genie computes it on `gold.replenishment_fill` by instruction (`src/genie/space.yaml:22-24`); (b) `days_of_supply` is period average closing on hand / average daily units (`03_serving.sql:202-204`), not "closing on hand / trailing-28-day mean on uncensored days". |
| B18 | Baselines measured by committed queries | PASS | `evidence/03b_backtest_value.md`, `evidence/03_ml.md` (incumbent WAPE 0.4790), `docs/BUSINESS_CASE.md` §1 | |
| B19 | Hypotheses tested, not assumed | PASS | `evidence/03b_backtest_value.md` hypothesis table | WAPE −25 % missed (−4.8 %), reported. |
| B20 | Ground truth validates lost sales | PASS | `evidence/03_ml.md` (estimate vs truth: −12.1 % before the holdout, −20.0 % on it); `evidence/01_lakeflow.md` gold vs truth | |

### §4 Data

| # | Requirement | Verdict | Proof | Notes |
|---|---|---|---|---|
| B21 | Entities and grain | PASS | `evidence/00_raw_data.md` entity table | 12 entities (stores, products, assortment, buyers, promotions, POS and online lines, returns, snapshots, POs, receipts, write-offs). |
| B22 | Timeline (history, holdout, live window) | PASS | `evidence/00_raw_data.md`, `evidence/00b_live_drip.md` | |
| B23 | Scale targets and ≤15 min generation | PASS | `evidence/00_raw_data.md` | 38.3M order lines (target 20–60M), 152M snapshots, generate task 6.5 min. |
| B24 | Every defect injected at a known rate, with manifest counts | PASS | `evidence/00_raw_data.md` "Injected defects" | 14 defect types. |
| B25 | Censored demand emerges from the incumbent policy | PASS | `evidence/00_raw_data.md` "Censored demand vs ground truth" | |

### §5 Stages: Builds and "Evidence →"

| # | Requirement | Verdict | Proof | Notes |
|---|---|---|---|---|
| B26 | 0 Builds: generator, config, tests, two jobs | PASS | `src/generator/`, `tests/test_generator.py`, `resources/bigbox_generate_data.job.yml`, `resources/bigbox_live_drip.job.yml` | |
| B27 | 0 Evidence: files and bytes per entity, rows, date ranges, manifest, determinism, censored share | PASS | `evidence/00_raw_data.md` | Determinism shown as "0 differ" rather than two hash lists. |
| B28 | A Builds: SDP bronze / silver / gold, Auto Loader, expectations, quarantine, 5 gold tables | PASS | `src/pipeline/`, `evidence/01_lakeflow.md` gold table list | |
| B29 | A: triggered **every 15 minutes** by `bigbox_refresh` | PARTIAL | live: `bigbox_refresh` cron `0 0/15 * * * ?`, **PAUSED** | Last 25 runs: 10, all `ONE_TIME`. The schedule is declared but has never run; `README.md` says "paused by default". |
| B30 | A Evidence: update id, state, duration; per-expectation counts from the event log vs the manifest; quarantine counts; incremental second update; late-files count | PARTIAL | `evidence/01_lakeflow.md` | All present and reconciled (every defect "yes"). The late count is in rows (640,889 POS, 29,212 online), not files. |
| B31 | B: comments on every gold / serving table and column | PASS | `evidence/02b_catalog_metadata.md` | All 100 % except `serving.recommendations_synced` (UC forbids comments on a synced table; documented). |
| B32 | B: tags `domain`, `pii`, `kpi`, `layer` | PARTIAL | `evidence/02b_catalog_metadata.md` | Governed tag policies forced `pii_type` and `sensitivity` instead of `pii`, and no `layer` on ml / serving; documented. |
| B33 | B: personas as service principals, each with its own CLI profile; grants per persona | PASS | `evidence/02_unity_catalog.md` personas and grants tables | Live: the 3 persona SPs and the app SP exist. |
| B34 | B: row filter driven by `serving.region_access` | PASS | `evidence/02_unity_catalog.md` queries A, B, C, G; filters attached on 5 gold tables | |
| B35 | B: column mask on buyer email / phone, proven per persona | PARTIAL | `evidence/02_unity_catalog.md` query D | Masked output is shown only for the ops director. East and analyst are **denied** on `silver.buyers` (stricter than "PII masked", but the mask itself is shown for one persona). |
| B36 | B: the app's SP least privilege | PASS | `evidence/06_app.md` "Least privilege" | |
| B37 | B: metric views; a `MEASURE()` query equals hand SQL | PASS | `evidence/02_unity_catalog.md` | See B17 for the definition gaps. |
| B38 | B: Lakebase/mask trade-off documented | PASS | `evidence/04_lakebase.md` "Trade-offs"; `README.md` "Decisions and trade-offs" | Reworded from the untested planning claim. |
| B39 | B Evidence: lineage from the raw volume to gold, serving and the model (system tables) | PARTIAL | `evidence/02b_catalog_metadata.md`, `evidence/03_ml.md` "model provenance" | Silver → gold → serving → synced: PASS. Raw volume → bronze is not captured by `system.access` (documented). Model lineage comes from MLflow logged inputs, not system tables. |
| B40 | C: features in UC Feature Engineering, `FeatureLookup` point-in-time | PASS | `evidence/03_ml.md` feature table and sweep note; `src/ml/01_features.ipynb`, `02_train.ipynb` | |
| B41 | C: one holdout; six candidates; Optuna on the boosters; WAPE + bias | PASS | `evidence/03_ml.md` sweep table | |
| B42 | C: AutoML tried once or recorded why not | PASS | `evidence/03_ml.md` ("cannot be imported on serverless environment 4") | |
| B43 | C: registry `@champion` / `@challenger` | PASS | `evidence/03_ml.md`; live aliases champion=1, challenger=2 | |
| B44 | C: batch scoring → `gold.forecast`; recommendations with risk, overstock, order qty | PASS | `evidence/03_ml.md` | |
| B45 | C: backtest of (a) incumbent vs (b) ML forecast **+ intraday visibility**; value with sensitivity | PARTIAL | `evidence/03b_backtest_value.md` | Backtest and value PASS. Intraday visibility is "not credited" (the simulator has no backroom or expediting), stated in 03b. |
| B46 | C: endpoint `@champion`, scale-to-zero; request / response with latency; parity ≤1e-6 on 500 rows | PASS | `evidence/03_ml.md` (max diff 0.0; p50 69.2 ms); live READY, Small, scale_to_zero | |
| B47 | D: project, CDF, triggered synced table, OLTP decisions, UC registration, write-back MERGE | PASS | `evidence/04_lakebase.md` | |
| B48 | D Evidence: sync status, source vs synced counts, p50 / p95, decisions Postgres → Delta with matching ids | PASS | `evidence/04_lakebase.md` | |
| B49 | E: space over metric views + gold; KPI definitions verbatim; synonyms; 6–8 example SQL; joins; exported config recreated by a script | PASS | `src/genie/space.json` (8 example SQL, 3 join specs, 5 sample questions, 7 tables), `src/genie/kpi_definitions.md`, `src/genie/space.py` | |
| B50 | E: ≥20 questions with reference SQL, Conversation API, compared, 3 runs | PASS | `src/genie/questions.yaml` (25), `src/genie/score.py`, `results/genie/` | |
| B51 | E Evidence: space id and config, per-question table per run, accuracy, flips, a worked conversation; before/after fixes | PASS | `evidence/05_genie.md` | Caveat on generalisation stated. |
| B52 | F: KPI header, Lakebase queue, what-if on the endpoint, approve / override / reject, Genie embedded; bindings in the bundle; runs as its SP | PASS | `evidence/06_app.md`; live 4 bindings | Known limitation (override equal to the recommendation) accepted by the user. |
| B53 | F Evidence: app.yaml and bindings; deployment; real session from `apps logs`; smoke test of the deployed URL with pre/post rows in Postgres and Delta | PASS | `evidence/06_app.md` | |
| B54 | Cost Evidence: DBUs and $ per refresh, scoring, endpoint, app from billing x list prices **filtered on the project tag**; per refresh and per month | PARTIAL | `evidence/07_cost.md` | Everything present, but attributed by resource id because the tag reaches billing for only ~4 % of the cost (serverless pipelines, the shared warehouse and the app carry no tag); documented. |

### §6 Repo, README, index, deck

| # | Requirement | Verdict | Proof | Notes |
|---|---|---|---|---|
| B55 | Repo layout | PASS | clone tree | Adds `tools/`, `results/`, `docs/`; `src/agent/` correctly absent. |
| B56 | README: 9 sections in order, outcome numbers linked, architecture diagram | PASS | `README.md` headings; mermaid flowchart | |
| B57 | Deck: outcome, decisions and trade-offs, how AI was used, what went wrong, 30/60/90, out of scope; **says the generator is calibrated with plausible industry values** | PARTIAL | `deck/deck.md` | All sections present. Missing: the calibration statement (BP §4; only in the README) and the calibration limitation the build log says "must be stated in the deck" (inventory turns ~74 a year, days of supply ~4.7). |
| B58 | `evidence/INDEX.md` with totals | PASS | `evidence/INDEX.md` | Lists the CSV too. |
| B59 | Tests: generator determinism, recommendation logic, KPI SQL | PARTIAL | `tests/` (43 pass in the clone) | Determinism and policy logic tested. KPI SQL has no unit test; it is checked in evidence instead (`02`: metric view = hand SQL). |

### §7 P0 and final checklist

| # | Requirement | Verdict | Proof | Notes |
|---|---|---|---|---|
| B60 | Every P0 item shipped with evidence | PARTIAL | B26–B54 | All built and evidenced; "triggered every 15 minutes" (B29) and "one-command deploy" (B5) fall short. |
| B61 | Checklist: lint, format, tests pass | PASS | clone: `ruff check` and `ruff format --check` clean, `pytest` 43 passed | App lint not re-run in this audit. |
| B62 | Checklist: endpoint warmed before any demo | FAIL | - | No demo since the restart; the app was restarted 2026-11-26 and no what-if has been sent (first call after scale-to-zero ~58 s). Fix: one what-if before the roleplay. |

The other checklist items map to rows above: B1, B2, B3, B4, B6, B13, B24, B33, B46, B50, B53, B7 and B8.

## 3. Gaps by severity, with effort

Effort: **S** < 1 h, **M** 1–3 h, **L** > 3 h (includes re-running evidence where needed).

### High (could cost a domain rating)

| # | Gap | Row | Required by | Effort | Fix |
|---|---|---|---|---|---|
| G1 | The deck does not frame value for the **executive sponsor**. | F16 | FE Bar | S | A COO slide from `BUSINESS_CASE.md` §4: margin, cost lines, working capital, run cost, consolidation. |
| G2 | The repo never says the problem is a **real customer's** (anonymised), and the **FY27 outcome map** is absent. | F1, B16 | FE Bar (real problem); BP (outcome map) | S | One sentence each in the README and the deck: "drawn from a real retail engagement, anonymised" and "FY27 Retail: Collaborative Supply Chain → Smarter Demand and Inventory Decisions → …". |
| G3 | **How AI was used** is generic: no tool named in the deck, no prompts or patterns. | F24 | FE Bar (tip) | S | Name the tool and session; show the pattern (written brief → golden rules → evidence-as-text → approval gates → self-recorded failures), plus 2–3 sanitised prompt excerpts. |
| G4 | **Redeploy by changing `.env` only** fails (host, warehouse name, Genie space id hard-coded); never replayed from empty. | B5, B60 | BP | M (variables) + L (replay) | Drop the target host (or take it from the profile); make the warehouse a variable from `.env`; have `deploy.sh` pass `space.py`'s id as `BUNDLE_VAR_genie_space_id`. The replay needs a second workspace and ~3 h of runs. |

### Medium

| # | Gap | Row | Required by | Effort | Fix |
|---|---|---|---|---|---|
| G5 | **Evidence-to-commit traceability**: 10 headers say "none yet"; 6 of 8 hashes do not reproduce from any commit; 3 files have no hash. | B1 | BP (FE Bar needs only "evidence it ran") | S (honest note) or L (re-run) | S: one line per header ("code first committed in `b0861fe`; the run used an earlier working tree, hash shown"). L: re-run the stage evidence on committed code. |
| G6 | Deck overclaim: "regional managers see only their region … the app and Genie respect the same rules". Genie runs as the user (true); the app runs as its SP with all regions, and its region control is a UI filter. | F16 / B52 | Both (accuracy; roleplay security pushback) | S | Reword: the app is for the all-region Director of Operations; regional managers get region-filtered data through Genie and SQL. |
| G7 | 15-minute schedule declared but never run (10 of 10 refresh runs are one-time; paused). | B29 | BP | S (+ ~$3–5 spend) | Unpause for one hour, capture the 4 scheduled runs in 01 or 04, pause again. Needs a cost go-ahead. |
| G8 | KPI definitions: `replenishment_fill_rate` not in a metric view; `days_of_supply` differs from its stated definition. | B17 | BP | M | Either add a third metric view on `gold.replenishment_fill` and align `days_of_supply`, then re-run 02 and the Genie score; or document both deviations in the README and the KPI file. |
| G9 | Deck lacks the calibration statement and the calibration limitation from the build log. | B57 | BP | S | Two bullets in the deck. |

### Low

| # | Gap | Row | Required by | Effort | Fix |
|---|---|---|---|---|---|
| G10 | `BUSINESS_CASE.md` counts 7 "real app session" decisions; live data shows 5 plus 2 smoke-test rejects. | B7 | BP | S | Classify `reason LIKE '%smoke%'` in the tool and regenerate. |
| G11 | `BUSINESS_CASE.md` source hash uses absolute paths (machine-specific). | B1 | BP | S | Pass relative paths in `CODE`; regenerate. |
| G12 | `00_raw_data.md` and `01_lakeflow.md` show shrink with the pre-fix definition (expired only). | B7 | BP | S (note) or M (re-run) | A one-line note in each file, or re-run the evidence scripts. |
| G13 | Late data counted in rows, not files. | B30 | BP | S | Add a file count (`_metadata.file_path` with `is_late`) to `evidence_lakeflow.py`, or reword the claim. |
| G14 | Mask proven for one persona only (others denied). | B35 | BP | S | Accept and say so in 02, or grant the analyst SELECT on `silver.buyers` and re-run 02. |
| G15 | Lineage: raw volume → bronze not captured; model lineage only via MLflow. | B39 | BP | - | Accept (platform behaviour, documented). |
| G16 | Cost attributed by resource id, not the tag. | B54 | BP | - | Accept (documented); production fix is a serverless usage policy carrying the tag. |
| G17 | Intraday visibility not credited in the backtest. | B45 | BP | - | Accept (documented in 03b). |
| G18 | Hands-on time not tracked against the 4–8 h plan. | F10 | FE Bar (guidance) | S | State the elapsed span and what took longest in the deck's "How AI was used". |
| G19 | `docs/HANDOFF.md:26` still says the denylist "doesn't exist yet"; the 2026-11-26 app-restart edit to HANDOFF is uncommitted. | - | - | S | Fix the line; commit on request. |
| G20 | Endpoint not warmed since the restart. | B62 | BP | S | One what-if before the roleplay. |
| G21 | Scoping-session conversation id not recorded. | F17 | FE Bar (optional) | S | Add it to PROVENANCE if available. |
| G22 | Deadline: FE Bar due **November 30** (or January 31 for the AI Beta group). | O1 | FE Bar (FAQ) | - | Decide which fixes fit before the deadline. |
| G23 | The deck lacks the build kit's results slides: sponsor's KPIs, owner's KPIs, where the money goes, why Databricks, the ask, the evidence-map appendix, an app screenshot. | O8 | Build kit | M | Extend `deck/deck.md` from `BUSINESS_CASE.md` (overlaps G1). |
| G24 | The README has no "How AI was used" section and no evidence-index section, as the kit's README order expects. | O6 | Build kit | S | Add both sections (overlaps G3). |
| G25 | Only about 40 KB of the 78 KB of evidence is likely to be read by the validator. | O4 | FE Bar (validator) | S | Keep `evidence/INDEX.md` first and make it carry the headline proof per stage (one line of real output each); consider trimming the largest files. |
| G26 | No markdown exports of the notebooks. | O7 | Build kit | S | Export each `.ipynb` to `.md` with outputs (for example `jupyter nbconvert --to markdown`), committed beside it. |

## 4. FE Bar versus your build prompt only

**Required by the FE Bar (prioritise these):**

- G22: the deadline (FAQ).
- G25: what the validator actually reads (validator behaviour; affects Build + AI Mindset).

- G1: executive-sponsor framing in the deck.
- G2 (first half): say the problem is a real customer's, anonymised.
- G3: how AI was used (tools, prompts, patterns); an FE Bar tip, scored under Build + AI mindset.
- G6: the app-security overclaim. Not an FE Bar rule as such, but the roleplay expects security pushback from the
  technical stakeholder.
- G18, G21 and F25: guidance or optional, low effort.

Every FE Bar build requirement (F2–F9, F11–F15, F19–F23) is a PASS.

**Recommended by the FE Bar build kit (the guide your prompt comes from; not the official rubric):**

- G23: the deck's results slides and appendix.
- G24: README sections on how AI was used and the evidence index.
- G26: markdown exports of the notebooks.
- O9 at submission: upload with `git archive`, the attestation, and leaving the AI Customer Challenge box unticked.

**Required only by `BUILD_PROMPT.md` (your own bar, above the FE Bar):**

- G4: one-command redeploy by changing `.env` only. The FE Bar asks for evidence it ran, not for redeployability.
- G5: git commit in every evidence header. The FE Bar asks only for readable evidence.
- G2 (second half): the FY27 outcome map. Your scoping prompt asked for it and BP §3 names it; it also supports the
  FE Bar's Industry domain.
- G7 to G17 and G19 to G20: the 15-minute schedule, KPI definitions, deck calibration notes, the business-case
  label and hash, stale shrink rows, late-file wording, the mask demonstration, lineage, tag-based cost, intraday
  visibility, HANDOFF hygiene, endpoint warm-up.

Suggested order, cheapest high-value first: G1, G2, G3, G6, G9, G23 and G24 (deck and README text, about 2–3 h together), then G25 and G26. Then
G10, G11, G19 and G20 (small fixes), then G5 (honest header notes). G4, G7 and G8 last, since they need code changes,
spend or re-runs.
