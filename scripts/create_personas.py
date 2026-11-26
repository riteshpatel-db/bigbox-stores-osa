"""Create the persona service principals, one local CLI profile each, and warehouse CAN_USE.

  uv run python scripts/create_personas.py --warehouse-id <id>

Idempotent: an existing SP is reused and an existing profile is left alone. Each OAuth secret is
written only to ~/.databrickscfg (back it up first) and is never printed.
"""

import argparse
import configparser
import json
import os
import subprocess

PERSONAS = ["bigbox-sp-ops-director", "bigbox-sp-region-east", "bigbox-sp-analyst"]
CFG = os.path.expanduser("~/.databrickscfg")


def cli(*args: str, body: dict | None = None) -> dict | list:
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
        raise SystemExit(f"failed: {' '.join(args[:2])}: {r.stderr[:300]}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warehouse-id", required=True)
    args = ap.parse_args()
    existing = {s.get("displayName"): s for s in cli("service-principals", "list")}
    cfg = configparser.RawConfigParser()
    cfg.read(CFG)
    host = cfg[os.environ["DATABRICKS_CONFIG_PROFILE"]]["host"]
    acl = []
    for name in PERSONAS:
        sp = existing.get(name)
        if sp is None:
            sp = cli(
                "service-principals",
                "create",
                body={
                    "displayName": name,
                    "active": True,
                    "entitlements": [
                        {"value": "workspace-access"},
                        {"value": "databricks-sql-access"},
                    ],
                },
            )
            print(f"created SP {name}: application_id {sp['applicationId']}")
        else:
            print(f"SP exists {name}: application_id {sp['applicationId']}")
        acl.append({"service_principal_name": sp["applicationId"], "permission_level": "CAN_USE"})
        if cfg.has_section(name):
            print(f"  profile [{name}] already present")
            continue
        secret = cli("service-principal-secrets-proxy", "create", sp["id"])
        with open(CFG, "a") as f:
            f.write(
                f"\n[{name}]\nhost          = {host}\nclient_id     = {sp['applicationId']}\n"
                f"client_secret = {secret['secret']}\n"
            )
        print(f"  profile [{name}] appended (secret value not shown)")
    cli("permissions", "update", "warehouses", args.warehouse_id, body={"access_control_list": acl})
    print(f"CAN_USE on warehouse {args.warehouse_id} for {len(acl)} personas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
