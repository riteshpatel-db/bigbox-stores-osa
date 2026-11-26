# 00b Live drip (one release)
- Command: `databricks bundle run bigbox_live_drip` (job `bigbox_live_drip`, run `352948629226807`)
- Run at: 2026-11-24T05:05:51Z → 2026-11-24T05:06:25Z (UTC)
- Workspace: https://fevm-serverless-stable-ritesh.cloud.databricks.com
- UC objects: `/Volumes/bigbox_fe_bar/raw/landing/_staging`, `/Volumes/bigbox_fe_bar/raw/landing`
- Git commit: none yet (first commit pending); source sha256 `73011715590b` over src/generator

## Tasks

| task | result | duration |
|---|---|---|
| release | SUCCESS | 0.5 min |

## Output: release

```text
{
  "released_from": "2026-10-01T06:00:00",
  "released_before": "2026-10-01T10:00:00",
  "released": 8,
  "remaining": 1280,
  "by_entity": {
    "inventory_snapshots": 2,
    "online_order_lines": 2,
    "pos_order_lines": 2,
    "replenishment_receipts": 1,
    "write_offs": 1
  }
}
```

## Landing before / after (CLI, same session)

```text
pos files in landing before: 365, staged pos: 392
pos files in landing after: 367, staged pos: 390
{"released_before": "2026-10-01T10:00:00"}
```
