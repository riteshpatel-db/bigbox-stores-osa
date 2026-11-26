"""Job entry point for bigbox_generate_data.

run_generate.py --output /Volumes/<catalog>/raw/landing            write the dataset
run_generate.py --hash-only --compare <landing>/_manifest/files.json
    re-run in memory and compare every file hash with an earlier run
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(globals().get("__file__", sys.argv[0]))))

from bigbox_gen.config import DEFAULT_CONFIG, load_config  # noqa: E402
from bigbox_gen.run import generate  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--output")
    ap.add_argument("--hash-only", action="store_true")
    ap.add_argument("--compare", help="files.json of an earlier run to compare hashes against")
    ap.add_argument("--write-manifest", nargs="*", default=[], help="manifest paths to save")
    ap.add_argument("--manifest-root", help="landing root the manifest paths are relative to")
    args = ap.parse_args()
    cfg = load_config(args.config)

    if args.hash_only:
        sink = generate(cfg, None, log=lambda s: print(s, flush=True))
        for rel in args.write_manifest:  # save a manifest produced by this in-memory run
            dest = Path(args.manifest_root) / rel
            tmp = dest.with_name(f"_{dest.name}.tmp")
            tmp.write_bytes(sink.manifests[rel])
            os.replace(tmp, dest)
            print(f"wrote {dest} ({len(sink.manifests[rel]):,} bytes)", flush=True)
        if not args.compare:
            return 0
        before = json.loads(Path(args.compare).read_text())
        after = sink.files
        skip = {"_manifest/files.json"}
        keys = set(before) - skip
        diff = sorted(k for k in keys if before[k]["sha256"] != after.get(k, {}).get("sha256"))
        new = sorted(set(after) - set(before) - skip)
        print(
            f"determinism check: {len(keys)} files compared, {len(diff)} differ; "
            f"{len(new)} new in this run: {new}",
            flush=True,
        )
        for k in diff[:20]:
            print(f"  DIFF {k}", flush=True)
        return 1 if diff else 0

    out = Path(args.output)
    if out.exists() and any(p for p in out.iterdir() if not p.name.startswith(".")):
        print(f"refusing to write: {out} is not empty (clear it deliberately first)", flush=True)
        return 2
    generate(cfg, out, log=lambda s: print(s, flush=True))
    return 0


if __name__ == "__main__":
    code = main()
    if code:  # serverless treats any SystemExit, even exit(0), as a task failure
        raise SystemExit(code)
