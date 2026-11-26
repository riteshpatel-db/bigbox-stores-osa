"""bigbox_refresh task `sync`: push tonight's gold.recommendations into Lakebase.

Triggers one update of the synced table's pipeline (serving.recommendations_synced, TRIGGERED
mode, reads the change data feed of gold.recommendations) and waits until the synced table is
back online with nothing pending. The pipeline id is read from the synced table, so no
environment id is hard-coded (the pipeline is created by scripts/setup_lakebase.py).
"""

import argparse
import json
import time

from databricks.sdk import WorkspaceClient

DONE = {"COMPLETED"}
FAILED = {"FAILED", "CANCELED"}


def iso(x) -> str | None:
    """SDK timestamps are protobuf Timestamps; print them as RFC 3339."""
    if x is None:
        return None
    return x.ToJsonString() if hasattr(x, "ToJsonString") else str(x)


def synced_version(st) -> int | None:
    """Source (Delta) commit version the synced table last caught up to."""
    info = st.status.last_sync.delta_table_sync_info if st.status.last_sync else None
    return info.delta_commit_version if info else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--timeout-s", type=int, default=1800)
    args = ap.parse_args()
    w = WorkspaceClient()
    name = f"synced_tables/{args.catalog}.serving.recommendations_synced"
    st = w.postgres.get_synced_table(name)
    pipeline_id = st.status.pipeline_id
    before = synced_version(st)
    t0 = time.time()
    update_id = w.pipelines.start_update(pipeline_id).update_id
    while True:
        u = w.pipelines.get_update(pipeline_id, update_id).update
        state = u.state.value if u.state else "UNKNOWN"
        if state in DONE | FAILED or time.time() - t0 > args.timeout_s:
            break
        time.sleep(10)
    st = w.postgres.get_synced_table(name)
    result = {
        "synced_table": name,
        "pipeline_id": pipeline_id,
        "update_id": update_id,
        "update_state": state,
        "seconds": round(time.time() - t0, 1),
        "detailed_state": st.status.detailed_state.value if st.status.detailed_state else None,
        "source_commit_version_before": before,
        "source_commit_version_after": synced_version(st),
        "last_sync_end": iso(st.status.last_sync.sync_end_time) if st.status.last_sync else None,
    }
    print(json.dumps(result, indent=2, default=str), flush=True)
    if state != "COMPLETED":
        raise RuntimeError(f"sync update {update_id} ended {state}")
    return 0


if __name__ == "__main__":
    code = main()
    if code:  # serverless treats any SystemExit, even exit(0), as a task failure
        raise SystemExit(code)
