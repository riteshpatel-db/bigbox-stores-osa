"""Enforce evidence limits: <=30 files, <=9,000 chars each, <=90,000 in total, header present.

The limits count every file under evidence/ (including evidence/metrics/*.csv); the header is
required on the stage markdown files only.
"""

import sys
from pathlib import Path

MAX_FILES, MAX_CHARS, MAX_TOTAL = 30, 9_000, 90_000
HEADER = ("- Command:", "- Run at:", "- Workspace:", "- UC objects:", "- Git commit:")


def main() -> int:
    files = sorted(p for p in Path("evidence").rglob("*") if p.is_file())
    problems, total = [], 0
    for f in files:
        text = f.read_text()
        total += len(text)
        if len(text) > MAX_CHARS:
            problems.append(f"{f}: {len(text):,} chars > {MAX_CHARS:,}")
        if f.suffix == ".md" and f.parent.name == "evidence" and f.name != "INDEX.md":
            head = text.splitlines()[:8]
            missing = [h for h in HEADER if not any(line.startswith(h) for line in head)]
            if missing:
                problems.append(f"{f}: header missing {', '.join(missing)}")
        print(f"{len(text):>7,}  {f}")
    print(f"{total:>7,}  total in {len(files)} files")
    if len(files) > MAX_FILES:
        problems.append(f"{len(files)} files > {MAX_FILES}")
    if total > MAX_TOTAL:
        problems.append(f"{total:,} chars in total > {MAX_TOTAL:,}")
    for p in problems:
        print(f"FAIL {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
