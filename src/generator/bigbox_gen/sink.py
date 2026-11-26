"""File sink: gzips each extract, hashes its bytes and, unless hash-only, writes it atomically.

Writes go through a small thread pool: on a UC volume the cost is per-file latency and throughput,
not CPU, so overlapping writes keeps the full run inside its time budget.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv

CSV_OPTIONS = pacsv.WriteOptions(include_header=True, quoting_style="needed")


class Sink:
    """Write files under root (or only hash them when root is None); record sha256, bytes, rows."""

    def __init__(self, root: Path | str | None, workers: int = 8):
        self.root = Path(root) if root is not None else None
        self.files: dict[str, dict] = {}
        self.manifests: dict[
            str, bytes
        ] = {}  # small JSON files, kept so hash-only runs can save them
        self._pool = ThreadPoolExecutor(workers) if self.root else None
        self._slots = threading.BoundedSemaphore(workers * 4)  # caps bytes held in memory
        self._futures: list[Future] = []

    def csv(self, relpath: str, table: pa.Table) -> None:
        buf = io.BytesIO()
        pacsv.write_csv(table, buf, write_options=CSV_OPTIONS)
        self._put(relpath + ".gz", _gzip(buf.getvalue()), table.num_rows)

    def jsonl(self, relpath: str, rows: list[dict]) -> None:
        data = "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows).encode()
        self._put(relpath + ".gz", _gzip(data), len(rows))

    def json(self, relpath: str, obj: object) -> None:
        data = (json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n").encode()
        self.manifests[relpath] = data
        self._put(relpath, data, None)

    def close(self) -> None:
        """Wait for every pending write; re-raise the first failure."""
        if self._pool is None:
            return
        for f in self._futures:
            f.result()
        self._pool.shutdown()

    def _put(self, relpath: str, data: bytes, rows: int | None) -> None:
        self.files[relpath] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "rows": rows,
        }
        if self._pool is None:
            return
        self._slots.acquire()
        fut = self._pool.submit(self._write, self.root / relpath, data)
        fut.add_done_callback(lambda _: self._slots.release())
        self._futures.append(fut)

    @staticmethod
    def _write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Leading underscore: Spark / Auto Loader ignore the file until it is renamed in place.
        tmp = path.with_name(f"_{path.name}.tmp")
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)


def _gzip(data: bytes) -> bytes:
    # mtime=0 keeps the bytes (and so the hashes) identical across runs
    return gzip.compress(data, compresslevel=1, mtime=0)
