"""Score the Genie space against questions.yaml through the Conversation API.

  uv run python src/genie/score.py --runs 3 --label final [--only q01 q02] [--warehouse NAME]

For every question and run: start a new conversation, wait for Genie's answer, take the SQL it
generated, run that SQL and the reference SQL on the same warehouse, and compare the result sets:
- order-insensitive (rows are matched, not compared by position);
- numeric values within 0.5 % (relative; absolute 1e-9 near zero);
- dates compared as dates (a TIMESTAMP at midnight equals the DATE);
- Genie may return extra columns; every reference column must map to a distinct Genie column, and
  the same number of rows must come back. A ratio column returned as a percentage (x100) counts as a
  match and is reported as such.
Each run is written to results/genie/<label>_run<k>.json with the question, Genie's SQL and text,
both row counts, the verdict and its reason.
"""

import argparse
import datetime as dt
import itertools
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / "results" / "genie"
TOL = 0.005
MAX_ROWS = 5000
DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:[T ]00:00:00(?:\.0+)?(?:Z|[+-]00:?00)?)?$")


def cli(*args: str, body: dict | None = None) -> dict:
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
    for attempt in range(6):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            return json.loads(r.stdout) if r.stdout.strip() else {}
        if "429" in r.stderr or "RESOURCE_EXHAUSTED" in r.stderr or "rate" in r.stderr.lower():
            time.sleep(15 * (attempt + 1))
            continue
        raise RuntimeError(r.stderr.strip()[:500])
    raise RuntimeError(f"rate limited: {' '.join(args[:3])}")


def run_sql(warehouse: str, sql: str) -> tuple[list[str], list[list]]:
    r = cli(
        "api",
        "post",
        "/api/2.0/sql/statements",
        body={
            "warehouse_id": warehouse,
            "statement": sql,
            "wait_timeout": "50s",
            "on_wait_timeout": "CONTINUE",
            "format": "JSON_ARRAY",
            "disposition": "INLINE",
        },
    )
    while r["status"]["state"] in ("PENDING", "RUNNING"):
        time.sleep(1)
        r = cli("api", "get", f"/api/2.0/sql/statements/{r['statement_id']}")
    if r["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(r["status"].get("error", {}).get("message", "failed")[:300])
    manifest = r.get("manifest", {})
    cols = [c["name"] for c in manifest.get("schema", {}).get("columns", [])]
    if manifest.get("total_row_count", 0) > MAX_ROWS:
        return cols, [None] * manifest["total_row_count"]  # too many rows to be a match
    result, chunk = r.get("result", {}), 0
    rows = list(result.get("data_array", []) or [])
    while result.get("next_chunk_internal_link"):
        chunk += 1
        result = cli(
            "api", "get", f"/api/2.0/sql/statements/{r['statement_id']}/result/chunks/{chunk}"
        )
        rows += result.get("data_array", []) or []
    return cols, rows


def norm(v):
    if v is None:
        return None
    s = str(v).strip()
    m = DATE.match(s)
    if m:
        return ("d", m.group(1))
    try:
        return ("n", float(s))
    except ValueError:
        return ("s", s.lower())


def same(a, b, scale: float = 1.0) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if a[0] != b[0]:
        return False
    if a[0] == "n":
        x, y = a[1] * scale, b[1]
        return abs(x - y) <= max(1e-9, TOL * max(abs(x), abs(y)))
    return a[1] == b[1]


def column_matches(ref: list, gen: list, scale: float) -> bool:
    key = lambda v: (v is None, v[0] if v else "", v[1] if v else 0)  # noqa: E731
    return all(
        same(a, b, scale) for a, b in zip(sorted(ref, key=key), sorted(gen, key=key), strict=True)
    )


def compare(ref_cols, ref_rows, gen_cols, gen_rows) -> tuple[bool, str]:
    if len(ref_rows) != len(gen_rows):
        return False, f"row count {len(gen_rows)} vs reference {len(ref_rows)}"
    if not ref_rows:
        return True, "both empty"
    r = [[norm(v) for v in row] for row in ref_rows]
    g = [[norm(v) for v in row] for row in gen_rows]
    rc = list(zip(*r, strict=True))
    gc = list(zip(*g, strict=True))
    options = []  # per reference column: (genie column, scale) candidates
    for i, col in enumerate(rc):
        cands = [
            (j, s)
            for j in range(len(gc))
            for s in (1.0, 100.0)
            if (s == 1.0 or all(v is None or v[0] == "n" and abs(v[1]) <= 1 for v in col))
            and column_matches(list(col), list(gc[j]), s)
        ]
        if not cands:
            return False, f"no Genie column matches reference column {ref_cols[i]!r}"
        options.append(cands)
    for combo in itertools.product(*options):
        if len({j for j, _ in combo}) < len(combo):
            continue
        free = list(range(len(g)))
        ok = True
        for row in r:
            hit = next(
                (
                    k
                    for k in free
                    if all(same(row[i], g[k][j], s) for i, (j, s) in enumerate(combo))
                ),
                None,
            )
            if hit is None:
                ok = False
                break
            free.remove(hit)
        if ok:
            pct = [ref_cols[i] for i, (_, s) in enumerate(combo) if s != 1.0]
            return True, "match" + (f" (as percentage: {', '.join(pct)})" if pct else "")
    return False, "values match per column but not row by row"


def ask(space_id: str, question: str, timeout_s: int = 300) -> dict:
    t0 = time.time()
    m = cli(
        "api",
        "post",
        f"/api/2.0/genie/spaces/{space_id}/start-conversation",
        body={"content": question},
    )
    conv, msg = m["conversation_id"], m["message_id"]
    path = f"/api/2.0/genie/spaces/{space_id}/conversations/{conv}/messages/{msg}"
    while True:
        m = cli("api", "get", path)
        if m.get("status") in ("COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"):
            break
        if time.time() - t0 > timeout_s:
            break
        time.sleep(3)
    sql, text = None, []
    for a in m.get("attachments") or []:
        if a.get("query"):
            sql = a["query"].get("query")
        if a.get("text"):
            text.append(a["text"].get("content", ""))
    return {
        "conversation_id": conv,
        "message_id": msg,
        "status": m.get("status"),
        "genie_sql": sql,
        "genie_text": "\n".join(t for t in text if t),
        "error": (m.get("error") or {}).get("error"),
        "seconds": round(time.time() - t0, 1),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--label", required=True)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--warehouse", default="FE_BAR_Ritesh")
    ap.add_argument("--title", default="Bigbox Stores - Store Ops")
    args = ap.parse_args()
    spaces = cli("genie", "list-spaces").get("spaces", [])
    space_id = next(s["space_id"] for s in spaces if s.get("title") == args.title)
    wh = next(w["id"] for w in cli("warehouses", "list") if w["name"] == args.warehouse)
    questions = yaml.safe_load((HERE / "questions.yaml").read_text())["questions"]
    if args.only:
        questions = [q for q in questions if q["id"] in args.only]
    refs = {q["id"]: run_sql(wh, q["sql"]) for q in questions}
    OUT.mkdir(parents=True, exist_ok=True)
    for k in range(1, args.runs + 1):
        started = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        results = []
        for q in questions:
            res = {"id": q["id"], "topic": q["topic"], "question": q["question"]}
            try:
                res |= ask(space_id, q["question"])
            except RuntimeError as e:
                res |= {"status": "API_ERROR", "error": str(e), "genie_sql": None}
            rc, rr = refs[q["id"]]
            res["reference_rows"] = len(rr)
            if not res.get("genie_sql"):
                res |= {"pass": False, "reason": f"no SQL from Genie ({res.get('status')})"}
            else:
                try:
                    gcols, grows = run_sql(wh, res["genie_sql"])
                    res["genie_rows"] = len(grows)
                    res["genie_result_head"] = {"columns": gcols, "rows": grows[:10]}
                    ok, why = compare(rc, rr, gcols, grows)
                    res |= {"pass": ok, "reason": why}
                except RuntimeError as e:
                    res |= {"pass": False, "reason": f"Genie SQL failed: {e}"}
            results.append(res)
            print(
                f"run {k} {q['id']} {'PASS' if res['pass'] else 'FAIL'} {res['reason']}", flush=True
            )
        passed = sum(r["pass"] for r in results)
        doc = {
            "label": args.label,
            "run": k,
            "space_id": space_id,
            "started": started,
            "finished": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "passed": passed,
            "total": len(results),
            "accuracy": round(passed / len(results), 4),
            "results": results,
        }
        path = OUT / f"{args.label}_run{k}.json"
        path.write_text(json.dumps(doc, indent=1) + "\n")
        print(f"run {k}: {passed}/{len(results)} -> {path.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
