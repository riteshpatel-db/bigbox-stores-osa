"""Apply src/governance/NN_*.sql on the SQL warehouse, in file order, one statement at a time.

  uv run python scripts/apply_governance.py --warehouse-id <id> [--files 01_access_model.sql ...]

${catalog}, ${owner} and ${sp_<persona>} placeholders are resolved at run time (the persona's
service-principal application id, looked up by display name), so no environment ids live in SQL.
"""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

GOVERNANCE = Path(__file__).resolve().parent.parent / "src" / "governance"


def cli(*args: str, body: dict | None = None):
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


def statements(sql: str) -> list[str]:
    """Split on ';' at end of line, but never inside a $$ ... $$ block (metric-view YAML)."""
    out, buf, in_dollar = [], [], False
    for line in sql.splitlines():
        if line.strip().startswith("--") and not buf:
            continue
        in_dollar ^= line.count("$$") % 2 == 1
        buf.append(line)
        if not in_dollar and line.rstrip().endswith(";"):
            out.append("\n".join(buf).rstrip().rstrip(";"))
            buf = []
    if "".join(buf).strip():
        out.append("\n".join(buf))
    return out


def run(warehouse_id: str, statement: str) -> None:
    r = cli(
        "api",
        "post",
        "/api/2.0/sql/statements",
        body={
            "warehouse_id": warehouse_id,
            "statement": statement,
            "wait_timeout": "50s",
            "on_wait_timeout": "CONTINUE",
        },
    )
    while r["status"]["state"] in ("PENDING", "RUNNING"):
        r = cli("api", "get", f"/api/2.0/sql/statements/{r['statement_id']}")
    if r["status"]["state"] != "SUCCEEDED":
        raise SystemExit(f"FAILED: {r['status']}\n{statement[:400]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warehouse-id", required=True)
    ap.add_argument("--catalog", default="bigbox_fe_bar")
    ap.add_argument("--files", nargs="*", help="default: every NN_*.sql in src/governance")
    args = ap.parse_args()
    values = {"catalog": args.catalog, "owner": cli("current-user", "me")["userName"]}
    app = cli("apps", "list")
    for a in app if isinstance(app, list) else app.get("apps", []):
        if a.get("name") == "bigbox-ops-app" and a.get("service_principal_client_id"):
            values["sp_app"] = a["service_principal_client_id"]
    for sp in cli("service-principals", "list"):
        name = sp.get("displayName", "")
        if name.startswith("bigbox-sp-"):
            values["sp_" + name.removeprefix("bigbox-sp-").replace("-", "_")] = sp["applicationId"]
    files = (
        [GOVERNANCE / f for f in args.files]
        if args.files
        else sorted(GOVERNANCE.glob("[0-9]*.sql"))
    )
    for f in files:
        if "${sp_app}" in f.read_text() and "sp_app" not in values:
            print(f"{f.name}: skipped (app bigbox-ops-app not deployed yet)")
            continue
        sql = re.sub(r"\$\{(\w+)\}", lambda m: values[m.group(1)], f.read_text())
        stmts = statements(sql)
        for s in stmts:
            run(args.warehouse_id, s)
        print(f"{f.name}: {len(stmts)} statements applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
