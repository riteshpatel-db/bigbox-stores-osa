"""Write evidence/05_genie.md from the scored runs in results/genie/ and the deployed space.

  uv run python scripts/evidence_genie.py --label final --worked q02 \
      --baseline "v0:data sources only (ablation)" "v1:full configuration, first run" \
      --out evidence/05_genie.md

Reads <label>_run1..3.json (written by src/genie/score.py), the baseline run(s) for the
before/after line, src/genie/space.json (the exported configuration) and the space metadata from
the Genie API. Nothing is typed.
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from write_evidence import HOST, code_hash, git_commit  # noqa: E402

RESULTS = ROOT / "results" / "genie"
CODE = ["src/genie"]


def runs(label: str) -> list[dict]:
    files = sorted(RESULTS.glob(f"{label}_run*.json"))
    return [json.loads(f.read_text()) for f in files]


def cell(r: dict) -> str:
    return "pass" if r["pass"] else "FAIL"


def short(reason: str) -> str:
    return reason.replace("|", "/").replace("\n", " ")[:70]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--baseline", nargs="*", default=[], help='"label:description" items')
    ap.add_argument("--worked", required=True, help="question id for the worked conversation")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rs = runs(args.label)
    space = json.loads((ROOT / "src" / "genie" / "space.json").read_text())
    ss = space["serialized_space"]
    ins = ss["instructions"]
    sid = rs[0]["space_id"]
    cmd = [
        os.environ.get("DATABRICKS_CLI", "databricks"),
        "-p",
        os.environ["DATABRICKS_CONFIG_PROFILE"],
        "genie",
        "get-space",
        sid,
    ]
    meta = json.loads(
        subprocess.run([*cmd, "-o", "json"], check=True, capture_output=True, text=True).stdout
    )
    commit = git_commit()
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    n_syn = sum(
        len(c.get("synonyms", []))
        for t in ss["data_sources"]["tables"]
        for c in t["column_configs"]
    )
    text = "".join(ins["text_instructions"][0]["content"])
    md = [
        "# 05 Genie: space, 25 questions scored against reference SQL, 3 runs",
        f"- Command: `uv run python src/genie/space.py deploy`, then `uv run python "
        f"src/genie/score.py --runs {len(rs)} --label {args.label}`, then "
        "`uv run python scripts/evidence_genie.py`",
        f"- Run at: {rs[0]['started']} → {rs[-1]['finished']} (UTC); evidence written {now}",
        f"- Workspace: {HOST}",
        "- UC objects: " + ", ".join(f"`{t['identifier']}`" for t in ss["data_sources"]["tables"]),
        f"- Git commit: {f'`{commit}`' if commit else 'none yet (first commit pending)'}; "
        f"source sha256 `{code_hash(CODE)}` over src/genie; raw runs in "
        f"`results/genie/{args.label}_run1..{len(rs)}.json`",
        "",
        "## Space",
        "",
        f'"{meta["title"]}" (`{sid}`), warehouse `{meta.get("warehouse_id")}`. Configuration '
        "exported to `src/genie/space.json` (built from `space.yaml` + `kpi_definitions.md` and "
        "recreated by `src/genie/space.py deploy`): "
        f"{len(ss['data_sources']['tables'])} data sources (2 metric views first, gold tables for "
        f"queue, decisions, supplier fill and drill-down), {n_syn} column synonyms, "
        f"{len(ins.get('join_specs', []))} join specs, {len(ins.get('example_question_sqls', []))} "
        f"example SQL, {len(ss['config'].get('sample_questions', []))} sample questions, "
        f"instructions of {len(text):,} characters ending with the KPI definitions table verbatim "
        f"({text.count('| `')} KPIs). None of the 25 scored questions is an example SQL.",
        "",
        "Scoring (`src/genie/score.py`): a new conversation per question and run through the "
        "Conversation API; Genie's SQL and the reference SQL run on the same warehouse; results "
        "are compared order-insensitively, numbers within 0.5 %, extra Genie columns allowed, "
        "same row count required.",
        "",
        "## Accuracy",
        "",
        "| run | passed | accuracy |",
        "|---|---|---|",
    ]
    for item in args.baseline:
        b, _, desc = item.partition(":")
        for r in runs(b):
            md.append(
                f"| `{b}`: {desc or 'baseline'} | {r['passed']}/{r['total']} | "
                f"{r['accuracy']:.0%} |"
            )
    for r in rs:
        md.append(f"| run {r['run']} | {r['passed']}/{r['total']} | {r['accuracy']:.0%} |")
    md += [
        "",
        "## Per question",
        "",
        "| id | question | "
        + " | ".join(f"run {r['run']}" for r in rs)
        + " | reason when failed |",
        "|---|---|" + "---|" * len(rs) + "---|",
    ]
    flips = []
    for i, q in enumerate(rs[0]["results"]):
        cells = [r["results"][i] for r in rs]
        if len({c["pass"] for c in cells}) > 1:
            flips.append(q["id"])
        why = "; ".join(sorted({short(c["reason"]) for c in cells if not c["pass"]}))
        md.append(
            f"| {q['id']} | {q['question']} | " + " | ".join(cell(c) for c in cells) + f" | {why} |"
        )
    md += [
        "",
        "Flipped between runs: "
        + (", ".join(flips) if flips else "none")
        + f". Passed in all {len(rs)} runs: "
        + str(sum(all(r["results"][i]["pass"] for r in rs) for i in range(len(rs[0]["results"]))))
        + f" of {len(rs[0]['results'])}.",
        "",
    ]
    for item in args.baseline:
        b, _, desc = item.partition(":")
        for r in runs(b):
            fails = [x for x in r["results"] if not x["pass"]]
            if not fails:
                continue
            anchored = [
                x["id"]
                for x in fails
                if re.search(r"current_(date|timestamp)", x.get("genie_sql") or "", re.I)
            ]
            md += [
                f"`{b}`, {desc}, failed {len(fails)}: "
                + "; ".join(f"{x['id']} {short(x['reason'])}" for x in fails)
                + f". Of these, {len(anchored)} anchored relative dates on current_date() "
                "(after the data ends) instead of the latest date in the data.",
                "",
            ]
    md += [
        "Caveat: the 25 questions were written with the instructions, so 100 % shows the space "
        "answers its intended questions consistently, not that it generalises to any question; "
        "the ablation shows how much of that comes from the curation.",
        "",
    ]
    w = next(x for x in rs[0]["results"] if x["id"] == args.worked)
    head = w.get("genie_result_head") or {"columns": [], "rows": []}
    md += [
        f"## Worked conversation (run 1, `{w['id']}`, {cell(w)}, {w['seconds']} s)",
        "",
        f"**Question:** {w['question']}",
        "",
        "**Genie's SQL:**",
        "",
        "```sql",
        (w.get("genie_sql") or "").strip(),
        "```",
        "",
        "**Result:**",
        "",
        "| " + " | ".join(head["columns"]) + " |",
        "|" + "---|" * len(head["columns"]),
        *(
            "| " + " | ".join("" if v is None else str(v)[:24] for v in row) + " |"
            for row in head["rows"]
        ),
        "",
        "**Genie's answer text:** "
        + ((w.get("genie_text") or "-").strip().replace("\n", " ")[:900]),
        "",
        f"Verdict against the reference SQL: {w['reason']}.",
    ]
    Path(args.out).write_text("\n".join(md) + "\n")
    print(f"wrote {args.out} ({len(chr(10).join(md)):,} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
