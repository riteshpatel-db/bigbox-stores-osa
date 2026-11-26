"""Release staged live micro-batch files into the landing folders, oldest first."""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
from pathlib import Path

CURSOR = "_manifest/drip_cursor.json"


def _slot(name: str) -> dt.datetime:
    stamp = name.rsplit("_", 1)[1].split(".")[0]  # e.g. pos_2026100109.csv -> 2026100109
    return dt.datetime.strptime(stamp, "%Y%m%d%H")


def release(landing: Path | str, hours: int) -> dict:
    """Move every staged file whose slot starts before cursor + hours, then advance the cursor."""
    landing = Path(landing)
    staged = sorted(
        (p for p in (landing / "_staging").glob("*/*") if not p.name.startswith("_")),
        key=lambda p: (_slot(p.name), p.parent.name),
    )
    cursor_file = landing / CURSOR
    if cursor_file.exists():
        cursor = dt.datetime.fromisoformat(json.loads(cursor_file.read_text())["released_before"])
    elif staged:
        cursor = _slot(staged[0].name)  # first run starts at the earliest staged batch
    else:
        return {"released": 0, "remaining": 0, "released_before": None, "by_entity": {}}
    new_cursor = cursor + dt.timedelta(hours=hours)
    by_entity: dict[str, int] = {}
    for p in staged:
        if _slot(p.name) >= new_cursor:
            break
        dest_dir = landing / p.parent.name
        dest_dir.mkdir(parents=True, exist_ok=True)
        tmp = dest_dir / f"_{p.name}.tmp"  # hidden from Auto Loader until the rename
        shutil.copyfile(p, tmp)
        os.replace(tmp, dest_dir / p.name)
        p.unlink()
        by_entity[p.parent.name] = by_entity.get(p.parent.name, 0) + 1
    tmp = cursor_file.with_name(f"_{cursor_file.name}.tmp")
    tmp.write_text(json.dumps({"released_before": new_cursor.isoformat()}) + "\n")
    os.replace(tmp, cursor_file)
    released = sum(by_entity.values())
    return {
        "released_from": cursor.isoformat(),
        "released_before": new_cursor.isoformat(),
        "released": released,
        "remaining": len(staged) - released,
        "by_entity": dict(sorted(by_entity.items())),
    }
