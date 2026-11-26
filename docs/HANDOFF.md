# HANDOFF

Last updated: 2026-11-26 UTC, all P0 stages done (cost, README, evidence index, deck) (session `bf191158-6010-4280-a63c-eedf77cd5b33`).
Keep this file current: update it at the end of every session, and delete anything no longer true.

## Read these first, in this order

1. **This file.**
2. **The build brief**: `/Workspace/Users/ritesh.patel@databricks.com/BUILD_PROMPT.md`. It covers the constraints, KPI
   definitions, data spec and every stage's "Builds" / "Evidence →". Where it differs from SCOPE.md, the brief wins.
3. **The scope**: `/Workspace/Users/ritesh.patel@databricks.com/SCOPE.md`. Agreed scope and decisions (sections 8 and 10).
   Section 9 is private; never copy it anywhere.
4. **The build log**: `/Workspace/Users/ritesh.patel@databricks.com/BUILD_LOG.md`. Dated notes, failures included.

Local copies of 2–4 live in `~/Projects/fe_bar_ritesh/working/` (outside the repo). Keep the workspace and local copies
in sync: upload with `workspace import --overwrite`, then export and `cmp` to verify.

## Ground rules that apply every session

- Profile **`fe-vm-serverless-stable-ritesh`**, always passed explicitly (`-p`). On this laptop `DEFAULT` is a different workspace.
- **CLI 1.27** (`/opt/homebrew/bin/databricks`, pinned as `DATABRICKS_CLI` in `.env`) for every bundle command since stage F;
  `~/.local/bin/databricks` (0.292) is first on PATH and must not run bundle commands any more (trap 49).
- Ask before committing, pushing, deleting or overwriting resources, sharing, or creating anything not listed in
  `docs/PROVENANCE.md`.
- **Nothing is committed yet.** The user said to hold the first commit until they say so. The private denylist for
  `scripts/prepush_check.sh` (`../working/denylist.private.txt`) will come from the user; it doesn't exist yet.
- The customer is described by industry only. The public name is "Bigbox Stores".
- **Repo:** https://github.com/riteshpatel-db/bigbox-stores-osa (public, personal account; the EMU account can't own
  public repos). Commit as `riteshpatel-db <ritesh.patel@databricks.com>` (repo-local git config); remote `origin` =
  `git@github-personal:riteshpatel-db/bigbox-stores-osa.git` (SSH key `~/.ssh/github_personal`). Run
  `scripts/prepush_check.sh` before every push; push only when the user asks.
- **`uv.lock` is gitignored** (user's decision, 2026-11-26): it records an internal package-proxy host for every
  download. Dev tool versions resolve from `pyproject.toml`; the jobs pin their own versions in the bundle and the app
  has its own `package-lock.json` (public npm registry). The private denylist exists: `../working/denylist.private.txt`.

## Stage status

| Stage | State | Evidence |
|---|---|---|
| Scaffold (repo, bundle, catalog/schemas/volume) | **built**, verified in the workspace | none (not a stage; see `docs/PROVENANCE.md`) |
| Preflight (auth, permissions, compute, collisions) | **done** 2026-10-30 | `docs/PROVENANCE.md` § Preflight results |
| 0 Raw data (generator) | **built**, run on serverless, evidence written | `evidence/00_raw_data.md`, `evidence/00b_live_drip.md` |
| A Lakeflow | **built**: 2 triggered updates, 14/14 defect types reconciled, gold = ground truth | `evidence/01_lakeflow.md` |
| B Unity Catalog | **built**: 3 persona SPs proven by querying as each; row filter + PII mask; 2 metric views = hand SQL; full comment coverage; lineage | `evidence/02_unity_catalog.md`, `evidence/02b_catalog_metadata.md` |
| C ML (P0) | **built**: features, 6-candidate sweep, `@champion`/`@challenger`, batch scoring, recommendations, backtest + value, endpoint with exact parity; notebooks committed with outputs of run `311784219823432` | `evidence/03_ml.md`, `evidence/03b_backtest_value.md` |
| C refresh path | **tested**: `bigbox_refresh` run `123666218097337` (pipeline → incremental features → incremental score) SUCCESS in ~7.3 min; idempotent with no new files | `docs/HANDOFF.md` (not an evidence stage) |
| C P1 agent `bigbox-reorder-agent` | not started (P1: only after every P0 has evidence) | - |
| D Lakebase | **built**: project `bigbox-ops`, synced table (TRIGGERED, `sync` task after `score`), `app.reorder_decisions`, write-back to `gold.reorder_decisions`; 20 evidence decisions round-tripped, idempotent; check run `909089715190901`, refresh run `387755722703731` | `evidence/04_lakebase.md` |
| E Genie | **built**: space "Bigbox Stores - Store Ops", 25 questions with reference SQL, 3 scored runs 25/25 each (ablation without curation 16/25) | `evidence/05_genie.md`, raw runs `results/genie/` |
| F App | **built and deployed**: `bigbox-ops-app` (AppKit), 4 bundle bindings, least-privilege SP, real browser session (5 decisions, 4 Genie questions), HTTP smoke test PASS | `evidence/06_app.md`, `results/app/smoke_test.json` |
| Cost | **built**: billing × list price, attribution by resource id (tag alone catches 4 %), unit costs, monthly model, ROI | `evidence/07_cost.md` |
| Business case | **built**: `tools/value_model_business_case.py` writes `docs/BUSINESS_CASE.md` + `evidence/metrics/value_model.csv` (measured levers, low/mid/high capture, stakeholder KPIs, run cost, risks) | `docs/BUSINESS_CASE.md`, `evidence/metrics/value_model.csv` |
| README / evidence index / deck | **written**: README outcome-first (9 sections + stage details), `evidence/INDEX.md` generated, `deck/deck.md` | `README.md`, `evidence/INDEX.md`, `deck/deck.md` |

## Live resources

Workspace `https://fevm-serverless-stable-ritesh.cloud.databricks.com`, id `7474657773731312`, expires 2027-01-13.

| Resource | Name | Id |
|---|---|---|
| Catalog | `bigbox_fe_bar` (owner ritesh.patel@databricks.com, `prevent_destroy`) | created 2026-10-30 03:39 UTC (no catalog id field returned) |
| Schema | `bigbox_fe_bar.raw` | `049b29bc-fcfe-4472-afda-c9a170466b9b` |
| Schema | `bigbox_fe_bar.bronze` | `cce4cd56-6860-423f-a372-dd9e4c181459` |
| Schema | `bigbox_fe_bar.silver` | `82634d81-ebc3-4316-9425-accbd43a0a7f` |
| Schema | `bigbox_fe_bar.gold` | `cce6ae9c-a739-4be1-9f3d-fa8a766ccd06` |
| Schema | `bigbox_fe_bar.ml` | `a8f9c55f-bd5f-4472-b74f-dabdd4b5b81e` |
| Schema | `bigbox_fe_bar.serving` | `b0546b01-2e81-47d5-aa84-0dbdaadd8604` |
| Volume | `/Volumes/bigbox_fe_bar/raw/landing`: 1.64 GB of gzipped extracts from run `367799309166838`; live batches released up to 2026-10-01 14:00 (`_manifest/drip_cursor.json`), 1,268 files still staged in `_staging/`. `_manifest/injected_defects_by_file.json` added 2026-11-23 (hash-identical re-run, see trap 19) | `a15f1990-b0ba-402f-949a-5a578f1d7c39` |
| Job | `bigbox_generate_data` (generate → validate + determinism_check) | `779275887426580` |
| Job | `bigbox_live_drip` (schedule every 15 min, **PAUSED**) | `995706476776113` |
| Pipeline | `bigbox_osa_pipeline` (serverless, triggered; catalog `bigbox_fe_bar`, default schema `bronze`) | `d84b1f86-3828-4676-87bb-43c03022e65e` |
| Job | `bigbox_refresh` (pipeline → features → score → sync, write_back in parallel; schedule every 15 min, **PAUSED**) | `253060125385282` |
| Tables | bronze: 12 Auto Loader STs; silver: 5 master MVs, POS + online MVs and their `quarantine_*` MVs, 5 STs; gold: `store_sku_daily`, `inventory_position`, `kpi_store_daily`, `online_fill`, `replenishment_fill` (all MVs) | latest update `232d9ca3-90db-49d5-b1b5-d833edb056be` |
| Bundle | `bigbox-stores-osa`, target `dev`, root `/Workspace/Users/ritesh.patel@databricks.com/.bundle/bigbox-stores-osa/dev` | direct-engine state in `state/` |
| SQL warehouse (shared, not owned by the bundle) | `FE_BAR_Ritesh` (serverless PRO Large, auto-stop 10 min); CAN_USE granted to the 3 personas | `d5b43df809d40fcf` |
| Persona SPs (each with a same-named profile in `~/.databrickscfg`; backup `~/.databrickscfg.bak-2026-11-23`) | `bigbox-sp-ops-director` / `bigbox-sp-region-east` / `bigbox-sp-analyst` | `bca34f6d-…de2` / `3c86153e-…af46` / `7043dc63-…0da5` |
| Governance objects | `serving.region_access` (table), `serving.region_allowed` + `serving.mask_pii` (functions), `serving.sales_lines` (view), `serving.sales_kpis` + `serving.availability_kpis` (metric views; the latter joins `gold.forecast`); row filter on gold `store_sku_daily`, `kpi_store_daily`, `inventory_position`, `forecast`; masks on `silver.buyers` name/email/phone; gold granted table by table | `src/governance/*.sql` |
| Job | `bigbox_ml_train` (features → train → score / backtest → endpoint) | `486211536028653`; evidence run `311784219823432` (repaired once) |
| MLflow experiment | `/Users/ritesh.patel@databricks.com/bigbox_demand_forecast` (bundle-managed) | `3164772271447205` |
| Feature table | `bigbox_fe_bar.ml.store_sku_features` (PK store_id, sku_id, date; timeseries `date`) | 10,108,926 rows at 2026-11-24 |
| UC model | `bigbox_fe_bar.ml.demand_lgbm`: v1 LightGBM `@champion`, v2 XGBoost `@challenger` | registered by run `311784219823432` |
| Serving endpoint | `bigbox-demand-forecast` (v1, Small CPU, scale-to-zero, tag project) | `703553fdc99c4070a041b589c913e522` |
| Tables (stage C) | `gold.forecast` (row filter), `gold.recommendations` (CDF on, no filter, no PII), `ml.sweep_results`, `ml.backtest_daily` | DDL `src/governance/02_ml_tables.sql` |
| Lakebase project | `bigbox-ops` (bundle resource, Autoscaling, Postgres 17, `prevent_destroy`); branch `production`, endpoint `primary` 0.5–2 CU, suspend 300 s | uid `6802ba52-d611-4608-94c2-aaa97a9ae416` |
| Lakebase database + UC catalog | Postgres database `bigbox_ops` (resource id `bigbox-ops`), registered as UC catalog `bigbox_ops_pg` | created by `scripts/setup_lakebase.py` |
| Synced table | `bigbox_fe_bar.serving.recommendations_synced` ← `gold.recommendations` (TRIGGERED, PK store_id + sku_id; Postgres `serving.recommendations_synced` + 2 queue indexes) | sync pipeline `e1d1b737-4300-4602-80c8-dabb0e38df80` (its event log table sits in `bigbox_fe_bar.serving`) |
| Decisions | Postgres `app.reorder_decisions` (insert-only, CHECKs) → Delta `gold.reorder_decisions` (row filter); 20 rows `decided_by = 'stage-d-evidence'` | DDL `src/lakebase/01_app_schema.sql`, `src/governance/02b_lakebase_tables.sql` |
| Job | `bigbox_lakebase_check` (seed → write_back → verify → write_back_again; no schedule) | `224787984707293` |
| Genie space | "Bigbox Stores - Store Ops" on `FE_BAR_Ritesh` (owner's space; config `src/genie/space.json`) | `01f1e884bece1d39994e9ba5a98ab5f1` |
| App | `bigbox-ops-app`, https://bigbox-ops-app-7474657773731312.aws.databricksapps.com (**RUNNING** since 2026-11-26 07:43 UTC, at the user's request; it bills while running. After a stop, `databricks apps start bigbox-ops-app` brings the compute back with no active deployment ("App has not been deployed yet"), so follow it with `databricks bundle run bigbox_ops_app`) | SP `app-2pidc0 bigbox-ops-app` = `3bb6052f-81da-45ab-9170-e84a4eef772e`; deployment `01f1e96d0b7c1a069457b0acd2746ec2` (2026-11-26; the evidence run's was `01f1e88ea44818f3bb030b4b21ab7e58`) |

**Not created yet:** agent endpoint (P1). Their approved names are in
`docs/PROVENANCE.md`. Add each to the table above, with its id (and the URL, for the app), as soon as it exists.

## How to run

```bash
cd ~/Projects/fe_bar_ritesh/bigbox-stores-osa
cp .env.example .env        # only if .env is missing (see trap 3 for the storage-root value)
./scripts/deploy.sh         # validate --strict + deploy, direct engine
uv run ruff check . && uv run ruff format --check .
DENYLIST=../working/denylist.private.txt ./scripts/prepush_check.sh   # before any push
```

Stage 0:

```bash
uv run pytest -q                                # generator tests on a tiny config (seconds)
set -a; source .env; set +a; export DATABRICKS_BUNDLE_ENGINE=direct
databricks bundle run bigbox_generate_data      # ~10 min; refuses to run unless landing is empty
databricks bundle run bigbox_live_drip          # releases the next 4 simulated hours
uv run python scripts/write_evidence.py --run-id <run> --title "..." --out evidence/NN_x.md \
    --command "..." --uc <objects> --code <source dirs> [--markdown-task <task>]
uv run python scripts/check_evidence.py         # <=30 files, <=9k chars each, <=90k total, header
```

Re-running `bigbox_generate_data` needs an empty landing volume. Clearing it is a deletion, so ask the user
first. Delete entry by entry (`databricks fs ls ... | while read e; do databricks fs rm -r ...; done`; see trap 16).
Stage A:

```bash
databricks bundle run bigbox_refresh            # one triggered pipeline update (~5 min backfill, ~3 min after)
databricks -p fe-vm-serverless-stable-ritesh pipelines start-update <pipeline_id> --validate-only   # graph check
uv run python scripts/evidence_lakeflow.py --pipeline-id d84b1f86-3828-4676-87bb-43c03022e65e \
    --updates <first update> <latest update> --warehouse-id d5b43df809d40fcf \
    --out evidence/01_lakeflow.md --command "..."
```

Stage B (all of it is inside `./scripts/deploy.sh`):

```bash
uv run python scripts/create_personas.py --warehouse-id d5b43df809d40fcf     # idempotent
uv run python scripts/apply_governance.py --warehouse-id d5b43df809d40fcf     # all src/governance/*.sql
uv run python scripts/evidence_governance.py --warehouse-id d5b43df809d40fcf \
    --out evidence/02_unity_catalog.md --out-meta evidence/02b_catalog_metadata.md
```

Order: `01_access_model.sql` before any pipeline update (the pipeline references the filter and mask functions),
then `02_ml_tables.sql` (stage-C tables); `03`–`05` after gold exists. Re-run `03`–`05` together: re-creating a
view can drop its tags and grants.

Stage C:

```bash
databricks bundle run bigbox_ml_train            # ~70 min; train ~38 min, endpoint ~15 min on first create
DATABRICKS_CONFIG_PROFILE=fe-vm-serverless-stable-ritesh uv run python scripts/export_notebook.py --run-id <run>
uv run python scripts/evidence_ml.py --run-id <run> --warehouse-id d5b43df809d40fcf \
    --out evidence/03_ml.md --out-backtest evidence/03b_backtest_value.md
```

Notebook sources are authored in `../working/nb_src/*.py` (percent format) and built with
`python3 ../working/nb_build.py ../working/nb_src src/ml`. After an evidence run, `export_notebook.py`
overwrites `src/ml/*.ipynb` with the same source plus outputs (it refuses if the source differs). Rebuilding from
`nb_src` drops the outputs again, so rebuild only before a new run.

Stage D (setup is inside `./scripts/deploy.sh`; it needs `uv run --with 'psycopg[binary]>=3.2'`, not a project dependency):

```bash
uv run --with 'psycopg[binary]>=3.2' python scripts/setup_lakebase.py   # idempotent: db, catalog, synced table, app schema
databricks bundle run bigbox_refresh             # ... score -> sync (~1 min), write_back in parallel
databricks bundle run bigbox_lakebase_check      # ~5 min; re-run reuses the evidence decisions of the same snapshot
DATABRICKS_CONFIG_PROFILE=fe-vm-serverless-stable-ritesh uv run python scripts/export_notebook.py --run-id <check run>
uv run python scripts/evidence_lakebase.py --check-run <run> --refresh-run <run> --warehouse-id d5b43df809d40fcf \
    --out evidence/04_lakebase.md
```

Connect to Postgres from the laptop (no psql installed): `cd src/lakebase && uv run --no-project --with
'psycopg[binary]>=3.2' --with databricks-sdk==0.170.0 python -c "from bigbox_lakebase import connect; ..."`.

Stage E (the space is not a bundle resource; `space.py` finds it by title, so never create a second space with that title):

```bash
uv run python src/genie/space.py deploy          # build from space.yaml + kpi_definitions.md, create/update, export space.json
uv run python src/genie/score.py --runs 3 --label final      # ~6 min per run of 25 questions
uv run python scripts/evidence_genie.py --label final --worked q02 \
    --baseline "v0:data sources only (ablation)" "v1:full configuration, first run" --out evidence/05_genie.md
```

`space.py deploy --bare` replaces the live config with the data sources only (ablation); always redeploy without
`--bare` afterwards and check `space.json` is unchanged apart from ids.

Stage F:

```bash
./scripts/deploy.sh                                   # app resource + grants (06_app_access.sql, 03_app_grants.sql)
PATH=/opt/homebrew/bin:$PATH databricks bundle run bigbox_ops_app   # deploy the current app source
./scripts/smoke_test_app.sh                           # writes results/app/smoke_test.json; adds one labelled decision
set -a; source .env; set +a; uv run --with 'psycopg[binary]>=3.2' --with databricks-sdk==0.170.0 \
  python scripts/evidence_app.py --session-user <email> --warehouse-id d5b43df809d40fcf --out evidence/06_app.md
cd src/app && npm run typecheck && npm run lint && npm run lint:ast-grep && npm run format
```

Decisions now in `app.reorder_decisions` (27 at the end of stage F): 20 `stage-d-evidence`, 2 smoke-test rejects
(reason "HTTP smoke test ..."), 5 from the owner's browser session.

Add each later stage's run command here once that stage exists.

## Next actions, in order

1. At session start, confirm auth (`databricks -p fe-vm-serverless-stable-ritesh current-user me`), then re-list the
   workspace inventory with `../working/list_inventory.sh > /tmp/inv.txt`, diff it against
   `../working/do_not_touch.private.txt`, and refresh that file (keep the old copy).
2. Every P0 item has evidence (README, `evidence/INDEX.md`, `deck/deck.md` included). Remaining, in order:
   - committed and pushed to the public repo (`main`); any further push only on request, after `prepush_check.sh`;
   - the stage-F override follow-up (reject an "override" equal to the recommendation) was declined by the user on
     2026-11-26: a known limitation, not a to-do;
   - P1 items only if the user asks (BUILD_PROMPT §7), cheapest first.
   Regenerate the index whenever an evidence file changes: `uv run python scripts/evidence_index.py &&
   uv run python scripts/check_evidence.py`. Cost evidence: `uv run python scripts/evidence_cost.py --refresh-run
   387755722703731 --train-run 311784219823432 --warehouse-id d5b43df809d40fcf --out evidence/07_cost.md`. Business case (same run ids, after 07): `uv run python
   tools/value_model_business_case.py --refresh-run 387755722703731 --train-run 311784219823432 --warehouse-id
   d5b43df809d40fcf`.
3. The app was restarted on 2026-11-26 (`apps start`, then `bundle run bigbox_ops_app`); stop it when the demo is done
   (`databricks apps stop bigbox-ops-app`). Before a demo, warm the endpoint with one what-if: the first call after scale-to-zero took
   ~58 s.

## Traps that already cost time

1. **`DEFAULT` profile is the wrong workspace.** The original handoff said "profile `DEFAULT`", but on this laptop
   `DEFAULT` points at a different workspace. The fevm workspace's profile is `fe-vm-serverless-stable-ritesh`. Always
   pass `-p` (or set `DATABRICKS_CONFIG_PROFILE` from `.env`); never rely on the default.

2. **Bundle-managed catalogs need the direct engine.** `bundle deploy` failed with "Catalog resources are only
   supported with direct deployment mode". CLI 0.292 has no YAML key for it; set the environment variable
   `DATABRICKS_BUNDLE_ENGINE=direct`. `scripts/deploy.sh` does this. Running a bare `databricks bundle deploy` will
   fail again.

3. **The metastore has no storage root.** Creating the catalog returned `400 INVALID_STATE: Metastore storage root
   URL does not exist`. The 10-23 capability check only verified the CREATE_CATALOG privilege, so it missed this. The fix
   is an explicit `storage_root` under the workspace's own external location. The bucket name is internal, so it lives
   only in the gitignored `.env` as `BUNDLE_VAR_catalog_storage_root`. If `.env` is lost, recover the value with
   `databricks -p fe-vm-serverless-stable-ritesh catalogs get bigbox_fe_bar` (field `storage_root`). Never commit it.

4. **`mode: development` would rename everything.** Development mode prefixes catalog/schema names with the user,
   which breaks the agreed names that Genie, the app and the evidence reference. The `dev` target deliberately has no
   `mode`; it sets an explicit `root_path` instead.

5. **`bundle validate --strict` wants one resource type per file.** A single file defining a catalog, schemas and a
   volume produced a recommendation (under `--strict`, treat that as failing). The split is now
   `*.catalog.yml`, `*.schemas.yml` and `*.volume.yml`; follow the same pattern for pipelines, jobs and the rest.

6. **The pre-push denylist check silently passed.** In `prepush_check.sh` a pipe and a here-string both fed grep's
   stdin, so the patterns were read from the history instead of the denylist, and a planted term was **not** caught.
   A negative test in a throwaway `/tmp` copy found it; the fix is `grep -f <(...)`. Whenever that script changes,
   re-run all 4 cases (missing denylist, clean, planted term, planted secret plus wrong author) in a `/tmp` copy. On 2026-11-26 the secret pattern was tightened (the broad `(password|secret|token) = 8+ chars` flagged 4
   runtime assignments, none a secret): it now needs a quoted literal or an env-style `KEY=value` that isn't computed.
   Planted secrets can't be committed past the global secret-scan hook, so test the pattern on sample lines (6
   planted shapes must match, the 4 runtime lines must not) and the other cases with throwaway commits.

7. **The agent's git-hook guard blocks some harmless commands.** A command containing `bash -n` and
   `git add --dry-run` was rejected as "bypassing git hooks with --no-verify". Avoid `-n`-style flags near git
   commands; use `git status --short -uall` to list commit candidates. Also note: global Databricks git hooks run a
   secret scan on every commit, which is good, and should be left on.

8. **The FEVM MCP server can't be reached from the session.** `fe-vending-machine` timed out at startup because it
   needs a browser OAuth login. Workspace expiry was verified manually by the user instead (2027-01-13). If FEVM is
   needed (grant expiry, extensions), ask the user to run `/mcp` and reconnect it.

9. **A typed number went stale within a day.** I copied the external-location count (102) from the previous day's
   inventory into `PROVENANCE.md`; the fresh listing said 103. In this shared workspace, other teams added 7 catalogs
   and 2 Foundation Model endpoints were retired in one day. Regenerate every count from a fresh listing, and pick the
   LLM endpoint at runtime from `serving-endpoints list`.

10. **Empty CLI lists break naive JSON parsing.** `registered-models list` on a catalog with no models printed
    nothing, so `json.load` raised `JSONDecodeError`. Treat empty output as `[]` in scripts.

11. **Serverless compute was unproven.** The workspace had 0 job runs and its pipelines had no update history. A
    one-time `jobs submit` run (`390170343766971`, environment version 4) proved serverless jobs: 26 s, Python
    3.12.3, Spark 4.2.0, reads UC and the volume. Serverless pipelines were proven in stage A; Lakebase synced
    tables on an Autoscaling project in stage D (TRIGGERED sync, read from serverless jobs and the SQL warehouse).

12. **On serverless, `sys.exit(0)` fails the task.** The first `bigbox_generate_data` run wrote every file and then
    ended with `SystemExit: 0`, which the serverless `spark_python_task` runner reports as a task failure. Entry scripts
    must return normally on success and raise `SystemExit` only with a non-zero code (see the end of
    `src/generator/run_*.py`).

13. **Serverless retries failed tasks automatically, and `max_retries: 0` does not stop it.** After that "failure" the
    generate task was retried; the retry refused to write into the now non-empty landing and failed for real (exit 2).
    The `max_retries: 0` added then never took effect: the direct deploy engine and the Jobs API both omit a zero, and
    serverless auto-optimization retries anyway (seen again in stage C, see trap 31). The fix is
    `disable_auto_optimization: true` on every serverless task (all four jobs have it; the pipeline task has no such
    field). Keep both settings.

14. **Volume writes, not compute, set the runtime.** Writing 11.84 GB of plain CSV took 26.5 min (about 7.6 MB/s). The
    small hourly live files cost about 13 s per simulated day in per-file overhead, while the CPU work is 100 s locally.
    The fix keeps hourly snapshots: gzip level 1 with `mtime=0` (so hashes stay deterministic; 1.64 GB) plus an 8-thread
    write pool (`bigbox_gen/sink.py`). The whole job now takes 10.4 min. Auto Loader and Spark read `.csv.gz` and
    `.jsonl.gz` natively.

15. **CSV nulls depend on the reader.** pyarrow reads an empty CSV string field as `""` unless
    `strings_can_be_null=True`, and it infers an integer type for an all-zero `discount_amount` file. Spark reads empty
    fields as null. When reading extracts outside Spark, pin the column types and the null handling.

16. **zsh does not word-split unquoted variables.** `for e in $entries` passed every folder name as one path (the
    Files API returned "Bad Request", and nothing was deleted). Iterate with `... | while IFS= read -r e; do ...; done`.

17. **Generator bugs the tests caught before any cloud run** (all fixed; keep the tests):
    - A holiday before the simulation start gave a negative slice end, and `hol[0:-4]` is not an empty slice.
    - `np.array(list_of_tuples, dtype=object)` builds a 2-D array.
    - The lines of one online order were not contiguous, which broke `line_number`.
    - Cents-price rows counted as clean, so they could be duplicated or made late.
    - Late rows near the end of the window were clamped into earlier batches, putting `extract_ts` before `event_ts`.

    The conservation tests (file units = ground-truth units) are the ones that catch this class of bug.

18. **First drip release was empty.** The cursor started at midnight, but the first staged batch is at 06:00, so the
    first 4-hour release moved nothing. The cursor now starts at the earliest staged batch. This change came after the
    generate run, so `evidence/00_raw_data.md` notes that only `drip.py` differs from the hashed source.

19. **Manifest totals include files that haven't been delivered.** The first reconciliation was about 7 % short on
    every defect, because the generator's totals also count the live window still in `_staging/`. The generator now
    also writes `_manifest/injected_defects_by_file.json`. `evidence_lakeflow.py` sums it over the files bronze has
    ingested, matching on entity + file name because the drip moves files. Adding the per-file counts changed no output
    byte: a serverless hash-only re-run (`3804267305265`) compared 3,862 files with 0 differences and wrote only the new
    manifest.

20. **Silver MVs recompute fully, so take expectation counts from the latest update.** In update 2 the silver POS MV
    failed 233,711 rows against 233,520 in update 1, a total over everything delivered rather than the new rows only.
    Streaming tables are the opposite: their counts are per update, so sum them.

21. **A `&&` / `;` chain deployed unlinted code.** `ruff check ... && ruff format ...; ./scripts/deploy.sh` deployed
    after lint had failed, because `;` ignores the failure. It was redeployed after the fix, before any run. Gate the
    deploy with `&&` as well.

22. **Validate before the first full update.** `pipelines start-update --validate-only` resolves the whole graph and
    schemas in about a minute without reading data. Use it after every pipeline code change, before a backfill.

23. **Governed tag policies on the shared account.** `ALTER SCHEMA raw SET TAGS ('layer' = 'raw')` failed with
    `UC_TAG_POLICY_VALUE_NOT_ALLOWED`. The account has 3,075 governed tag policies: `layer` allows only
    bronze/silver/gold, `pii` only ssn/address, `domain` six values. Use governed keys with allowed values
    (`pii_type` name/email/phone, `sensitivity` pii/internal/public) and never create or change account
    policies. List them with `databricks tag-policies list-tag-policies`.

24. **Pipeline-owned MVs: comments and tags work, but not through `ALTER TABLE`.** `ALTER TABLE ... ALTER COLUMN
    ... COMMENT` fails ("is a view"); `ALTER MATERIALIZED VIEW ... ALTER COLUMN ... COMMENT` and `SET TAGS` work,
    and both survived a pipeline refresh. Table comments come from the pipeline decorators. Row filters and masks
    must be declared in the pipeline (`row_filter=`, `schema=` with `MASK`). Masks need a full explicit schema.

25. **The pipeline identity must pass its own row filter.** Gold MVs read `gold.store_sku_daily`, which carries
    the region filter. The pipeline runs as the owner, so the owner has `region = '*'` in `serving.region_access`.
    Remove that row and downstream gold tables silently become empty.

26. **DECIMAL rounding in a metric-view measure.** `AVG(CASE WHEN ... THEN 1.0 ELSE 0.0 END)` is DECIMAL
    arithmetic, and `in_stock_pct` came back with 5 decimals, so the comparison with hand SQL failed at 1e-9. Use
    integer ratios (`SUM(IF(x, 1, 0)) / COUNT(1)` divides as DOUBLE).

27. **YAML in metric views: quote any value containing `: `.** `comment: Store format: SUPERCENTER, ...` failed to
    parse ("mapping values are not allowed here").

28. **No path lineage for Auto Loader.** `system.access.table_lineage` records bronze → silver → gold → serving,
    but not raw volume → bronze (0 source paths on 68 bronze rows). `_source_file` on every bronze row documents
    that hop instead.

29. **Calibration limitation, to state in the deck.** Inventory turns come out at about 74 a year and days of
    supply at about 4.7 (`serving.availability_kpis`). The generator's order-up-to levels are lean (lead time +
    review + 3 safety days, no backroom stock); a real big-box turns 8–10 times a year. Don't present turns as
    realistic.

30. **The point-in-time training set returns `date` as a timestamp.** `fe.create_training_set(...).load_df()` gave
    datetime64, so comparing with a `datetime.date` failed after the 2-minute load (first stage-C run). Normalise the
    column after loading.

31. **A failed serverless notebook task was retried in the same run**, despite `max_retries: 0` (trap 13). Cancel the
    run when a retry can only fail again, fix, redeploy, then `jobs repair-run <run> --rerun-all-failed-tasks`
    (the CLI has no `--rerun-tasks` flag; use `--json` for a task list).

32. **databricks-sdk 0.170 requires `name` in `EndpointCoreConfigInput`**, even when `create_and_wait` gets `name` too.

33. **PyYAML reads `1.0e9` as a string** (YAML 1.1 needs a sign in the exponent: `1.0e+9`). The value model failed
    on a str / float division. `tests/test_value.py` now checks that every assumption loads as a number.

34. **Repaired runs list every attempt.** `jobs get-run` returns both the failed and the successful attempt of a
    repaired task. `export_notebook.py` and `evidence_ml.py` use the latest attempt per task key, and the evidence
    task table shows all attempts.

35. **Model lineage stops at MLflow.** UC lineage has feature table → notebook → `gold.forecast`, but no table → model
    edge, because the models are logged with plain MLflow so the endpoint takes the feature row in the request (as the
    brief specifies). The training datasets are logged on the sweep run (`mlflow.log_input`), and the evidence shows
    that chain instead. Tables written from pandas temp views (`gold.recommendations`, `ml.*` results) have no table
    lineage.

36. **The WAPE hypothesis (−25 %) is out of reach on this data, by construction.** The generator's own expected
    demand scores holdout WAPE 0.448 (Poisson noise and day shocks at ~2 units/day); the incumbent is at 0.479. The
    champion closes ~73 % of that gap. Say so in the deck; the gains show in the backtest, not in WAPE.

37. **The ML policy trades fast-perishable units for waste.** At service level 0.95 lost units rise on fast-moving
    perishables (the shelf-life cap removes most of their safety stock) while waste falls; overall lost units rise
    slightly and lost sales $ fall. The service level was fixed in `policy.yaml` before the backtest and was not tuned
    on the holdout; 0.90 / 0.98 are shown as sensitivity. If changed, change it in `policy.yaml` and re-run.

38. **CLI 0.292 has no Lakebase database / catalog / synced-table commands** (the skill's `create-synced-table` needs
    ≥ 0.294), and the bundle has `postgres_projects` but no database, catalog or synced-table resource (the legacy
    `synced_database_tables` targets the retired provisioned tier). `setup_lakebase.py` uses `databricks api` on
    `/api/2.0/postgres/...`; writes return a long-running operation to poll. Creating a database needs
    `spec.role` (the owner's role resource, looked up from `.../roles`).

39. **The synced table's pipeline name has a random suffix** ("Synced table: <name> Je4WjS"), so a bundle
    `lookup` by name can't find it. The `sync` task reads `pipeline_id` from the synced table and starts the update
    itself. The pipeline puts its event log table in the storage schema (`serving`); the governance evidence
    omits it.

40. **UC rejects comments on a synced table** (`TABLE_ONLINE_VIEW`: "only the owner fields can be updated"), so
    `serving.recommendations_synced` shows 0 of 33 column comments; the evidence states it.

41. **SDK 0.170 drops `scheduling_policy` from the parsed synced-table status** (the raw API has it), and its
    timestamps are protobuf objects (`str()` prints `seconds: ... nanos: ...`; use `ToJsonString()`).
    The committed `02_check_seed` output shows `scheduling_policy: null` for that reason; `04_lakebase.md`
    reads it from the raw API (TRIGGERED).

42. **Running `bigbox_live_drip` was blocked by the machine's permission classifier** this session (it moves
    files in the landing volume). Not needed: `score` rewrites `gold.recommendations` on every refresh, which gives
    the sync a new source version. Ask the user to run it, or to allow it, when fresh data is needed.

43. **"Lakebase can't sync a row-filtered table" was never tested** (it came from the scope's risk list; the
    sync docs don't say). What holds by construction: Postgres reads bypass UC, so a filter wouldn't protect
    the copy. Wording corrected in README, `02_ml_tables.sql` (table comment re-applied) and `05_grants.sql`.

44. **PyYAML reads the key `on:` as boolean True** (YAML 1.1, same family as trap 33): the Genie join specs in
    `space.yaml` lost their key. Renamed to `using:`.

45. **The Genie API requires every list in `serialized_space` sorted by `id`** ("example_question_sqls must be
    sorted by id"). `space.py` generates increasing ids so each list keeps its authored order; tables must also be
    sorted by identifier.

46. **Without the space's date rule Genie anchors on `current_date()`**, which is after the data ends (the
    ablation's 8 of 9 failures). The data's latest day is partial; the instruction maps today / last week / last
    month to explicit dates. If the data is regenerated or the drip moves on, update those dates in `space.yaml`
    and `questions.yaml` together.

47. **`shrink_pct` in the metric view was expired / received, but the brief says expired + damaged.** Fixed in
    `03_serving.sql` and the stage-B hand SQL (history 0.0941 → 0.1088); the backtest already used the brief's
    definition. Stage 0 / A evidence reconcile expired / received against the ground truth and are labelled so.

48. **zsh ties the lowercase variable `path` to `PATH`.** A loop `for path in /api/health ...` replaced the search
    path, so `curl`, `cut` and `head` were "not found". Never name a shell variable `path`.

49. **Two CLIs on this laptop.** `~/.local/bin/databricks` is 0.292 (first on PATH); Homebrew's 1.27.0 has the bundle
    `postgres` app resource (also bundle resources for Lakebase databases, synced tables and Genie spaces). 1.27 keeps
    its own token cache: it needed `databricks auth login -p fe-vm-serverless-stable-ritesh` once (done by the user).
    Its read-only `bundle plan` against the 0.292 state showed 0 changes before switching. `deploy.sh` puts
    `DATABRICKS_CLI` first on PATH and refuses a CLI older than 1.27; the Python helpers call `DATABRICKS_CLI` too.

50. **The app's first build fails, by construction.** The build runs `appkit generate-types` as the app's new
    service principal, which has no UC grants until the app (and so the SP) exists: `INSUFFICIENT_PERMISSIONS ... USE
    CATALOG`. `deploy.sh` now grants the SP (06 + Postgres) and deploys again. The bundle records the failed app as
    created, so a later `bundle deploy` reports "0 changed"; `bundle run bigbox_ops_app` builds and starts the code.

51. **`appkit.serving().invoke()` resolves to an execution envelope** (`{ok, data}` / `{ok: false, status,
    message}`), not the endpoint response its types promise. The first what-if returned 502 until the route parsed
    the envelope. The endpoint was scaled to zero then (~58 s first call); warm calls take ~100 ms.

52. **Genie's built-in AppKit routes always run on behalf of the user**, so the app needs `user_api_scopes:
    [dashboards.genie]`; the platform adds `iam.access-control:read` and `iam.current-user:read`. Analytics `.sql`
    files, Lakebase and programmatic serving calls run as the app SP.

53. **Billing lags by hours and partial hours bias per-hour rates.** 2026-11-25 usage appeared ~5 h after the
    fact. A mean $ per billed hour includes partly used hours (auto-stop, scale-to-zero, the app stopped after its
    test) and understated continuous rates by half (app 0.25 vs 0.49 DBU in its one full hour; warehouse 21.7 mean
    vs 40.0 peak). The cost model uses the busiest billed hour. Lakebase usage does carry the `project` tag
    (compute DBU and storage DSU); serverless pipelines, the warehouse and the app don't.

## Headline measured numbers

Stage 0 baseline. These are **ground-truth facts of the synthetic history under the incumbent policy**, measured by
Spark in `evidence/00_raw_data.md` (run `367799309166838`). They are the baseline the new policy is compared against;
they are not results of this build:

| Measure (history 2025-10-01 → 2026-09-30) | Value |
|---|---|
| store-SKU-days | 10,080,921 |
| days with a stocked-out trading hour | 7.24 % |
| stocked-out share of trading hours (1 − OSA) | 5.69 % |
| demand lost to stockouts | 3.25 % of units; $23,828,460 of $283,628,145 sales at list price |
| online fill rate | 94.27 % |
| perishable shrink (expired / received) | 9.41 % |

Stage A's gold layer reproduces those ground-truth figures (`evidence/01_lakeflow.md`): in-stock 92.7577 %,
on-shelf availability 94.3144 % and perishable shrink 9.4055 % are identical. Units sold close to 0 unexplained
(37,630,559 true = 37,393,671 in gold + 232,729 + 1,451 quarantined + 2,708 not yet delivered).

Stage C (run `311784219823432`; values copied from the evidence files, which are the source):

| Measure | Value | Evidence |
|---|---|---|
| holdout WAPE: incumbent / champion (LightGBM) / noise floor | 0.4790 / 0.4562 / 0.4478 | `03_ml.md` |
| parity batch vs endpoint, 500 rows | max abs diff 0.0 | `03_ml.md` |
| backtest at 0.95 vs incumbent: lost sales $ / OSA / perishable shrink | −33.7 % / +2.16 pts / −33.9 % | `03b_backtest_value.md` |
| value at ~$1B, 50 % realisation (margin + waste + carrying) | ~$11.0M / yr | `03b_backtest_value.md` |
| business case at ~$1B, low / mid / high (illustrative; full-year measured losses x capture) | $3.5M / $7.1M / $11M per yr | `docs/BUSINESS_CASE.md` |
| lost-sales estimate vs ground truth (holdout) | −20 % (estimate is low) | `03_ml.md` |

Stage D (check run `909089715190901`, refresh run `387755722703731`; values from `04_lakebase.md`):

| Measure | Value |
|---|---|
| source vs synced rows / queue rows / differing values | 28,005 = 28,005 / 5,133 = 5,133 / 0 on 12 columns |
| Postgres lookup from serverless, p50 / p95 (PK; store queue top 25) | 2.2 / 3.88 ms; 2.31 / 4.23 ms |
| triggered sync after `score` | 42 s, source version 3 → 4 |
| decisions Postgres → Delta | 20 → 20, all ids match; second write-back inserts 0 |

Stage E (`05_genie.md`): 25/25 in each of 3 runs, no flips; data sources alone 16/25.

Stage F (`06_app.md`): queue from Lakebase in 18–94 ms through the app; what-if ~100 ms warm, endpoint baseline =
batch forecast; smoke test PASS (Postgres 21 → 22, Delta 21 → 22 after write-back).

Cost (`07_cost.md`, billing through 2026-11-26): build to date $183.52 at list price (the shared Large warehouse
$174.46 of it); one refresh $0.72; modelled run cost $218,468 a year at company scale; ROI 50 $ of value per $ on
the 03b value, 32 $ on the business case's mid case.
