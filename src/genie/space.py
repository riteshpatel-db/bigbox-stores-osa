"""Create, update and export the Genie space "Bigbox Stores - Store Ops".

  uv run python src/genie/space.py deploy [--catalog bigbox_fe_bar] [--warehouse FE_BAR_Ritesh]
  uv run python src/genie/space.py export
  uv run python src/genie/space.py deploy --bare   # ablation only: data sources, nothing else

`deploy` builds the Genie `serialized_space` from space.yaml (instructions, synonyms, joins,
example SQL) and kpi_definitions.md (the KPI table, verbatim), creates the space or updates the one
with the same title, then exports it. `export` writes the space as the API returns it to
space.json, so the committed file is the deployed configuration. The CLI profile comes from
DATABRICKS_CONFIG_PROFILE; Genie spaces are not a bundle resource type in this CLI version.
"""

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
EXPORT = HERE / "space.json"


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
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"failed: {' '.join(args[:3])}: {r.stderr.strip()[:800]}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def lines(text: str) -> list[str]:
    return text.strip("\n").splitlines(keepends=True)


_PREFIX, _SEQ = uuid.uuid4().hex[:24], [0]


def new_id() -> str:
    """Increasing ids: the API requires every list sorted by id, so creation order is kept."""
    _SEQ[0] += 1
    return f"{_PREFIX}{_SEQ[0]:08x}"


def build(catalog: str) -> tuple[dict, dict]:
    raw = (HERE / "space.yaml").read_text().replace("${catalog}", catalog)
    spec = yaml.safe_load(raw)
    kpis = [
        ln for ln in (HERE / "kpi_definitions.md").read_text().splitlines() if ln.startswith("|")
    ]
    instructions = spec["instructions"].rstrip("\n") + "\n\n" + "\n".join(kpis) + "\n"
    tables = []
    for t in spec["tables"]:
        cols = []
        for name, c in sorted((t.get("columns") or {}).items()):
            cc = {"column_name": name, "enable_format_assistance": True}
            if c.get("synonyms"):
                cc["synonyms"] = c["synonyms"]
            if c.get("entity_matching"):
                cc["enable_entity_matching"] = True
            cols.append(cc)
        tables.append({"identifier": t["identifier"], "column_configs": cols})
    tables.sort(key=lambda t: t["identifier"])
    joins = []
    for j in spec["join_specs"]:
        la, ra = j["left"].split(".")[-1], j["right"].split(".")[-1]
        cond = " AND ".join(f"`{la}`.`{c}` = `{ra}`.`{c}`" for c in j["using"])
        joins.append(
            {
                "id": new_id(),
                "left": {"identifier": j["left"], "alias": la},
                "right": {"identifier": j["right"], "alias": ra},
                "sql": [cond, f"--rt=FROM_RELATIONSHIP_TYPE_{j['relationship']}--"],
            }
        )
    serialized = {
        "version": 2,
        "config": {
            "sample_questions": [
                {"id": new_id(), "question": [q]} for q in spec["sample_questions"]
            ]
        },
        "data_sources": {"tables": tables},
        "instructions": {
            "text_instructions": [{"id": new_id(), "content": lines(instructions)}],
            "example_question_sqls": [
                {"id": new_id(), "question": [e["question"]], "sql": lines(e["sql"])}
                for e in spec["example_sqls"]
            ],
            "join_specs": joins,
        },
    }
    meta = {"title": spec["title"], "description": spec["description"]}
    return meta, serialized


def strip_ids(o):
    if isinstance(o, dict):
        return {k: strip_ids(v) for k, v in o.items() if k != "id"}
    if isinstance(o, list):
        return [strip_ids(v) for v in o]
    return o


def unchanged(space_id: str, meta: dict, warehouse_id: str, serialized: dict) -> bool:
    """True when the deployed space equals the built one apart from the generated ids."""
    s = cli("api", "get", f"/api/2.0/genie/spaces/{space_id}?include_serialized_space=true")
    return (
        s.get("title") == meta["title"]
        and s.get("description") == meta["description"]
        and s.get("warehouse_id") == warehouse_id
        and strip_ids(json.loads(s["serialized_space"])) == strip_ids(serialized)
    )


def find_space(title: str) -> str | None:
    found, token = [], None
    while True:
        page = cli("genie", "list-spaces", *(["--page-token", token] if token else []))
        found += [s["space_id"] for s in page.get("spaces", []) if s.get("title") == title]
        token = page.get("next_page_token")
        if not token:
            break
    if len(found) > 1:
        raise SystemExit(f"{len(found)} spaces titled {title!r}; resolve by hand")
    return found[0] if found else None


def export(space_id: str) -> dict:
    s = cli("api", "get", f"/api/2.0/genie/spaces/{space_id}?include_serialized_space=true")
    out = {
        "title": s["title"],
        "description": s.get("description"),
        "warehouse_id": s.get("warehouse_id"),
        "serialized_space": json.loads(s["serialized_space"]),
    }
    EXPORT.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["deploy", "export"])
    ap.add_argument("--catalog", default="bigbox_fe_bar")
    ap.add_argument("--warehouse", default="FE_BAR_Ritesh")
    ap.add_argument(
        "--bare",
        action="store_true",
        help="deploy the data sources only (no instructions, synonyms, joins, examples) to measure "
        "what the curation adds; not exported, so space.json stays the full configuration",
    )
    args = ap.parse_args()
    meta, serialized = build(args.catalog)
    if args.bare:
        tables = [{"identifier": t["identifier"]} for t in serialized["data_sources"]["tables"]]
        serialized = {"version": 2, "data_sources": {"tables": tables}}
    space_id = find_space(meta["title"])
    if args.command == "deploy":
        wh = next(w["id"] for w in cli("warehouses", "list") if w["name"] == args.warehouse)
        body = {**meta, "warehouse_id": wh, "serialized_space": json.dumps(serialized)}
        if space_id and not args.bare and unchanged(space_id, meta, wh, serialized):
            print(f"space {space_id} already matches space.yaml; not updated")
        elif space_id:
            cli("api", "patch", f"/api/2.0/genie/spaces/{space_id}", body=body)
            print(f"updated space {space_id}")
        else:
            space_id = cli("api", "post", "/api/2.0/genie/spaces", body=body)["space_id"]
            print(f"created space {space_id}")
    if not space_id:
        raise SystemExit(f"no space titled {meta['title']!r}")
    if args.bare:
        print("bare configuration deployed (not exported); redeploy without --bare after scoring")
        return 0
    out = export(space_id)
    ss = out["serialized_space"]
    ins = ss.get("instructions", {})
    print(
        f"exported {EXPORT.name}: {len(ss['data_sources']['tables'])} data sources, "
        f"{len(ins.get('example_question_sqls', []))} example SQL, "
        f"{len(ins.get('join_specs', []))} join specs, "
        f"{len(ss.get('config', {}).get('sample_questions', []))} sample questions"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
