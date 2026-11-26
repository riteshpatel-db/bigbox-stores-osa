"""Write evidence/NN_<stage>.md from a finished job run: run metadata plus every task's real output.

  uv run python scripts/write_evidence.py --run-id 123 --title "00 Raw data" \
      --out evidence/00_raw_data.md --uc bigbox_fe_bar.raw.landing --code src/generator \
      --command "databricks bundle run bigbox_generate_data" --markdown-task validate

Uses the Databricks CLI with the profile in DATABRICKS_CONFIG_PROFILE. Task output whose task key is
passed with --markdown-task is embedded as markdown; all other output goes in a text block.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
from pathlib import Path

HOST = "https://fevm-serverless-stable-ritesh.cloud.databricks.com"
LIMIT = 9000


def cli(*args: str) -> dict:
    profile = os.environ["DATABRICKS_CONFIG_PROFILE"]
    cmd = [os.environ.get("DATABRICKS_CLI", "databricks"), "-p", profile, *args, "-o", "json"]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def code_hash(paths: list[str]) -> str:
    """sha256 over the source files that ran, in path order (stands in until the first commit)."""
    h = hashlib.sha256()
    for root in paths:
        r = Path(root)
        if not r.exists():
            raise FileNotFoundError(root)
        # A file path hashes that file; a directory, every file under it.
        files = [r] if r.is_file() else [p for p in r.rglob("*") if p.is_file()]
        for f in sorted(p for p in files if "__pycache__" not in p.parts):
            h.update(str(f).encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:12]


def git_commit() -> str:
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def ts(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--command", required=True)
    ap.add_argument("--uc", nargs="+", required=True)
    ap.add_argument("--code", nargs="+", required=True)
    ap.add_argument("--markdown-task", nargs="*", default=[])
    args = ap.parse_args()

    run = cli("jobs", "get-run", args.run_id)
    commit = git_commit()
    code = f"`{commit}`" if commit else "none yet (first commit pending)"
    lines = [
        f"# {args.title}",
        f"- Command: `{args.command}` (job `{run['run_name']}`, run `{run['run_id']}`)",
        f"- Run at: {ts(run['start_time'])} → {ts(run['end_time'])} (UTC)",
        f"- Workspace: {HOST}",
        f"- UC objects: {', '.join(f'`{u}`' for u in args.uc)}",
        f"- Git commit: {code}; source sha256 `{code_hash(args.code)}` over {', '.join(args.code)}",
        "",
        "## Tasks",
        "",
        "| task | result | duration |",
        "|---|---|---|",
    ]
    tasks = sorted(run["tasks"], key=lambda t: t["start_time"])
    for t in tasks:
        state = t["state"].get("result_state", t["state"]["life_cycle_state"])
        secs = (t["end_time"] - t["start_time"]) / 1000
        lines.append(f"| {t['task_key']} | {state} | {secs / 60:.1f} min |")
    for t in tasks:
        out = cli("jobs", "get-run-output", str(t["run_id"]))
        body = (out.get("logs") or out.get("error") or "(no output)").rstrip()
        lines += ["", f"## Output: {t['task_key']}", ""]
        lines += [body] if t["task_key"] in args.markdown_task else ["```text", body, "```"]
    text = "\n".join(lines) + "\n"
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text)
    over = "  (OVER 9,000 LIMIT)" if len(text) > LIMIT else ""
    print(f"wrote {args.out}: {len(text):,} chars{over}")
    return 0 if len(text) <= LIMIT else 1


if __name__ == "__main__":
    raise SystemExit(main())
