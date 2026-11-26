"""Create the Lakebase objects the bundle cannot declare yet, then the app schema (idempotent).

  uv run --with 'psycopg[binary]>=3.2' python scripts/setup_lakebase.py [--catalog bigbox_fe_bar]

The project `bigbox-ops` (with its `production` branch and `primary` endpoint) is a bundle
resource. This script adds, in order, each only if missing:
  1. the Postgres database `bigbox_ops` on the production branch;
  2. its Unity Catalog registration, catalog `bigbox_ops_pg` (the write-back reads through it);
  3. the synced table `<catalog>.serving.recommendations_synced` <- `<catalog>.gold.recommendations`
     (TRIGGERED, primary key store_id + sku_id; in Postgres: serving.recommendations_synced);
  4. src/lakebase/01_app_schema.sql in Postgres: schema `app` and table `app.reorder_decisions`;
  5. src/lakebase/02_serving_indexes.sql: queue indexes on the synced table (once it is online);
  6. src/lakebase/03_app_grants.sql: the app's service principal, once the app exists.
The CLI (0.292) has no commands for 1-3, so they go through `databricks api` (Postgres API v2).
psycopg comes in through `uv run --with`, so it is not a project dependency.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECT = "projects/bigbox-ops"
BRANCH = f"{PROJECT}/branches/production"
ENDPOINT = f"{BRANCH}/endpoints/primary"
DATABASE_ID, PG_DATABASE, PG_CATALOG = "bigbox-ops", "bigbox_ops", "bigbox_ops_pg"


def cli(*args: str, body: dict | None = None, ok_missing: bool = False):
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
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        if ok_missing and ("does not exist" in r.stderr or "NOT_FOUND" in r.stderr):
            return None
        raise SystemExit(f"failed: {' '.join(args[:3])}: {r.stderr.strip()[:500]}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def wait(op: dict, what: str) -> dict:
    """Postgres API writes return a long-running operation; poll it until done."""
    while not op.get("done"):
        time.sleep(5)
        op = cli("api", "get", f"/api/2.0/postgres/{op['name']}")
    if "error" in op:
        raise SystemExit(f"{what} failed: {op['error']}")
    return op.get("response", {})


def ensure_database() -> None:
    dbs = cli("api", "get", f"/api/2.0/postgres/{BRANCH}/databases").get("databases", [])
    if any(d["status"]["postgres_database"] == PG_DATABASE for d in dbs):
        print(f"database {PG_DATABASE}: exists")
        return
    # The database needs an owner role: the caller's own (created with the project).
    me = cli("current-user", "me")["userName"]
    roles = cli("api", "get", f"/api/2.0/postgres/{BRANCH}/roles").get("roles", [])
    role = next(r["name"] for r in roles if r.get("status", {}).get("postgres_role") == me)
    op = cli(
        "api",
        "post",
        f"/api/2.0/postgres/{BRANCH}/databases?database_id={DATABASE_ID}",
        body={"spec": {"postgres_database": PG_DATABASE, "role": role}},
    )
    wait(op, "create database")
    print(f"database {PG_DATABASE}: created")


def ensure_catalog() -> None:
    if cli("api", "get", f"/api/2.0/postgres/catalogs/{PG_CATALOG}", ok_missing=True):
        print(f"catalog {PG_CATALOG}: exists")
        return
    op = cli(
        "api",
        "post",
        f"/api/2.0/postgres/catalogs?catalog_id={PG_CATALOG}",
        body={"spec": {"postgres_database": PG_DATABASE, "branch": BRANCH}},
    )
    wait(op, "register catalog")
    print(f"catalog {PG_CATALOG}: registered")


def ensure_synced_table(catalog: str) -> None:
    """Create the synced table if missing, then wait until its first snapshot is online."""
    name = f"{catalog}.serving.recommendations_synced"
    st = cli("api", "get", f"/api/2.0/postgres/synced_tables/{name}", ok_missing=True)
    if not st:
        op = cli(
            "api",
            "post",
            f"/api/2.0/postgres/synced_tables?synced_table_id={name}",
            body={
                "spec": {
                    "source_table_full_name": f"{catalog}.gold.recommendations",
                    "primary_key_columns": ["store_id", "sku_id"],
                    "scheduling_policy": "TRIGGERED",
                    "branch": BRANCH,
                    "postgres_database": PG_DATABASE,
                    "create_database_objects_if_missing": True,
                    "new_pipeline_spec": {"storage_catalog": catalog, "storage_schema": "serving"},
                }
            },
        )
        st = wait(op, "create synced table")
        print(f"synced table {name}: created")
    t0 = time.time()
    while (
        "ONLINE" not in st.get("status", {}).get("detailed_state", "") and time.time() - t0 < 1800
    ):
        time.sleep(15)
        st = cli("api", "get", f"/api/2.0/postgres/synced_tables/{name}")
    status = st.get("status", {})
    if "ONLINE" not in status.get("detailed_state", ""):
        raise SystemExit(f"synced table {name} not online: {status.get('message')}")
    print(
        f"synced table {name}: {status.get('detailed_state')}, pipeline {status.get('pipeline_id')}"
    )


def apply_postgres_sql() -> None:
    import psycopg  # supplied by `uv run --with`

    ep = cli("api", "get", f"/api/2.0/postgres/{ENDPOINT}")
    token = cli("postgres", "generate-database-credential", ENDPOINT)["token"]
    user = cli("current-user", "me")["userName"]
    with psycopg.connect(
        host=ep["status"]["hosts"]["host"],
        dbname=PG_DATABASE,
        user=user,
        password=token,
        sslmode="require",
        autocommit=True,
    ) as conn:
        for f in ("01_app_schema.sql", "02_serving_indexes.sql"):
            conn.execute((ROOT / "src" / "lakebase" / f).read_text())
            print(f"{f}: applied")
        n = conn.execute("SELECT count(*) FROM app.reorder_decisions").fetchone()[0]
        print(f"app.reorder_decisions: {n:,} rows")
        apps = cli("apps", "list")
        app_sp = next(
            (
                x.get("service_principal_client_id")
                for x in (apps if isinstance(apps, list) else apps.get("apps", []))
                if x.get("name") == "bigbox-ops-app"
            ),
            None,
        )
        if not app_sp:
            print("03_app_grants.sql: skipped (app bigbox-ops-app not deployed yet)")
            return
        sql = (ROOT / "src" / "lakebase" / "03_app_grants.sql").read_text()
        conn.execute(sql.replace("${sp_app}", app_sp))
        print(f"03_app_grants.sql: applied for the app's service principal {app_sp}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="bigbox_fe_bar")
    args = ap.parse_args()
    ensure_database()
    ensure_catalog()
    ensure_synced_table(args.catalog)
    apply_postgres_sql()
    return 0


if __name__ == "__main__":
    sys.exit(main())
