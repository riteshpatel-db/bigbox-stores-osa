"""Job entry point for bigbox_live_drip: release the next simulated hours of live files."""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(globals().get("__file__", sys.argv[0]))))

from bigbox_gen.config import DEFAULT_CONFIG, load_config  # noqa: E402
from bigbox_gen.drip import release  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--landing", required=True)
    ap.add_argument("--hours", type=int, help="default: live.drip_hours_per_run from the config")
    args = ap.parse_args()
    hours = args.hours or load_config(DEFAULT_CONFIG)["live"]["drip_hours_per_run"]
    print(json.dumps(release(args.landing, hours), indent=2), flush=True)
    return 0


if __name__ == "__main__":
    code = main()
    if code:  # serverless treats any SystemExit, even exit(0), as a task failure
        raise SystemExit(code)
