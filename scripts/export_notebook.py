"""Write the notebooks of a finished job run back to the repo as .ipynb, with the run's outputs.

  uv run python scripts/export_notebook.py --run-id <job run id> [--tasks features train ...]

`databricks jobs export-run` returns each notebook task as HTML with the notebook model embedded
(base64 of URL-encoded JSON: commands with their source and results). This converts that model to
nbformat 4: markdown cells, code cells, and their outputs as the run produced them (stdout,
tables from display(), errors). Every task's source must equal the repo notebook it ran from,
so the committed file is the exact code plus its real output. The only output removed is the
Spark Connect "Effective usage policy" log line, an opaque session token with no content.
"""

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOISE = re.compile(r"Effective usage policy for this session")
MAX_TABLE_ROWS = 50


def cli(*args: str) -> dict:
    cmd = [
        os.environ.get("DATABRICKS_CLI", "databricks"),
        "-p",
        os.environ["DATABRICKS_CONFIG_PROFILE"],
        *args,
        "-o",
        "json",
    ]
    return json.loads(subprocess.run(cmd, check=True, capture_output=True, text=True).stdout)


def notebook_model(task_run_id: int) -> dict:
    html = cli("jobs", "export-run", str(task_run_id), "--views-to-export", "CODE")["views"][0][
        "content"
    ]
    blob = re.search(r"__DATABRICKS_NOTEBOOK_MODEL = '([^']+)'", html).group(1)
    return json.loads(urllib.parse.unquote(base64.b64decode(blob).decode()))


def text_output(text: str) -> dict | None:
    lines = [ln for ln in text.splitlines(keepends=True) if not NOISE.search(ln)]
    return {"output_type": "stream", "name": "stdout", "text": "".join(lines)} if lines else None


def table_output(r: dict) -> dict:
    cols = [c["name"] for c in r.get("schema", [])]
    rows = r.get("data", [])[:MAX_TABLE_ROWS]
    md = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    for row in rows:
        md += "| " + " | ".join("" if v is None else str(v) for v in row) + " |\n"
    more = len(r.get("data", [])) - len(rows)
    if more > 0 or r.get("overflow"):
        md += f"\n({more if more > 0 else 'more'} rows not shown)\n"
    return {"output_type": "display_data", "metadata": {}, "data": {"text/markdown": md}}


def outputs(results: dict | None) -> list[dict]:
    if not results:
        return []
    items = results["data"] if results.get("type") == "listResults" else [results]
    out = []
    for r in items:
        kind = r.get("type")
        if kind == "table":
            out.append(table_output(r))
        elif kind in ("ansi", "text", "raw") and isinstance(r.get("data"), str):
            o = text_output(r["data"])
            if o:
                out.append(o)
        elif kind == "html":
            html = {"text/html": r["data"]}
            out.append({"output_type": "display_data", "metadata": {}, "data": html})
        elif kind == "error" or r.get("errorSummary"):
            out.append(
                {
                    "output_type": "error",
                    "ename": "Error",
                    "evalue": str(r.get("errorSummary") or r.get("data"))[:2000],
                    "traceback": [],
                }
            )
        elif r.get("data") not in (None, "", []):
            out.append(text_output(str(r["data"])) or {})
    return [o for o in out if o]


def to_ipynb(model: dict) -> dict:
    cells = []
    for c in sorted(model["commands"], key=lambda c: c["position"]):
        src = c["command"]
        if src.startswith("%md"):
            cells.append({"cell_type": "markdown", "metadata": {}, "source": src[3:].lstrip("\n")})
        else:
            cells.append(
                {
                    "cell_type": "code",
                    "metadata": {},
                    "source": src,
                    "outputs": outputs(c.get("results")),
                    "execution_count": None,
                }
            )
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "language_info": {"name": "python"},
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
        },
        "cells": cells,
    }


def sources(nb: dict) -> list[tuple[str, str]]:
    return [(c["cell_type"], c["source"].strip()) for c in nb["cells"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True, type=int)
    ap.add_argument("--tasks", nargs="*", help="task keys (default: every notebook task)")
    args = ap.parse_args()
    run = cli("jobs", "get-run", str(args.run_id))
    latest = {}  # a repaired run lists every attempt; export the last one of each task
    for t in sorted(run["tasks"], key=lambda t: t["start_time"]):
        latest[t["task_key"]] = t
    for task in latest.values():
        nb_task = task.get("notebook_task")
        if not nb_task or (args.tasks and task["task_key"] not in args.tasks):
            continue
        # The bundle uploads the repo under <root>/files/, so the path after it is repo-relative.
        rel = nb_task["notebook_path"].split("/files/", 1)[1]
        target = ROOT / (rel if rel.endswith(".ipynb") else rel + ".ipynb")
        nb = to_ipynb(notebook_model(task["run_id"]))
        repo = json.loads(target.read_text())
        if sources(nb) != sources(repo):
            print(f"{task['task_key']}: source differs from {target.name}; not written")
            return 1
        target.write_text(json.dumps(nb, indent=1) + "\n")
        n_out = sum(len(c.get("outputs", [])) for c in nb["cells"])
        print(f"{task['task_key']}: wrote {target.relative_to(ROOT)} ({n_out} outputs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
