#!/usr/bin/env bash
# HTTP smoke test of the DEPLOYED app (bigbox-ops-app), with a token generated at runtime.
#
#   ./scripts/smoke_test_app.sh            # writes results/app/smoke_test.json and prints a transcript
#
# 1. health and identity; 2. the queue (first open item); 3. a what-if on that item;
# 4. POST a decision (reject, labelled as a smoke test), with the row count of Postgres
#    app.reorder_decisions before and after, read through the bigbox_ops_pg catalog on the warehouse;
# 5. the bigbox_refresh write_back task alone, then the Delta gold.reorder_decisions count before and
#    after and the new decision id found in Delta.
# The token comes from `databricks auth token` for the CLI profile and is never printed or stored.
set -euo pipefail

cd "$(dirname "$0")/.."
set -a
# shellcheck disable=SC1091
source .env
set +a
if [[ -n "${DATABRICKS_CLI:-}" ]]; then
  export PATH="$(dirname "$DATABRICKS_CLI"):$PATH"
fi
: "${DATABRICKS_CONFIG_PROFILE:?set DATABRICKS_CONFIG_PROFILE in .env}"
CAT="${BUNDLE_VAR_catalog:-bigbox_fe_bar}"
APP=bigbox-ops-app
OUT=results/app/smoke_test.json
mkdir -p results/app

j() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

URL="$(databricks apps get "$APP" -o json | j "d['url']")"
WAREHOUSE_ID="$(databricks warehouses list -o json | j "next(w['id'] for w in d if w['name']=='FE_BAR_Ritesh')")"
REFRESH_JOB="$(databricks jobs list --name bigbox_refresh -o json | j "(d if isinstance(d,list) else d['jobs'])[0]['job_id']")"
TOKEN="$(databricks auth token -o json | j "d['access_token']")"

call() { # method path [json-body] -> body, then the HTTP status on the last line
  local method="$1" route="$2" body="${3:-}"
  local args=(-s -m 180 -X "$method" -H "Authorization: Bearer $TOKEN" -w '\n%{http_code}')
  [[ -n "$body" ]] && args+=(-H 'Content-Type: application/json' -d "$body")
  curl "${args[@]}" "$URL$route"
}
status_of() { tail -n 1 <<<"$1"; }
body_of() { sed '$d' <<<"$1"; }

sql_scalar() { # one value from the warehouse
  local body
  body="$(python3 -c 'import json,sys; print(json.dumps({"warehouse_id": sys.argv[1], "statement": sys.argv[2], "wait_timeout": "50s"}))' "$WAREHOUSE_ID" "$1")"
  databricks api post /api/2.0/sql/statements --json "$body" -o json | j "d['result']['data_array'][0][0]"
}
sql_count() { sql_scalar "SELECT count(*) FROM $1"; }

TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"' EXIT
put() { printf '%s' "$2" >"$TMPD/$1"; }
get() { cat "$TMPD/$1"; }
put started "$(now)"
put url "$URL"

echo "1/5 health and identity"
h="$(call GET /api/health)"; put health_status "$(status_of "$h")"; put health "$(body_of "$h")"
w="$(call GET /api/whoami)"; put whoami_status "$(status_of "$w")"
echo "  GET /api/health -> $(get health_status) $(get health)"
echo "  GET /api/whoami -> $(get whoami_status) (identity from the Apps proxy headers)"

echo "2/5 queue"
q="$(call GET '/api/queue?open=true&limit=5')"; put queue_status "$(status_of "$q")"; put queue "$(body_of "$q")"
STORE="$(j "d['rows'][0]['store_id']" <<<"$(get queue)")"
SKU="$(j "d['rows'][0]['sku_id']" <<<"$(get queue)")"
put item "$STORE/$SKU"
echo "  GET /api/queue?open=true&limit=5 -> $(get queue_status): $(j "f\"{d['total']} open queue items, {len(d['rows'])} returned in {d['ms']} ms\"" <<<"$(get queue)"); first: $STORE $SKU"

echo "3/5 what-if"
wi="$(call POST /api/whatif "{\"store_id\":\"$STORE\",\"sku_id\":\"$SKU\",\"promo_discount\":0.15}")"
put whatif_status "$(status_of "$wi")"; put whatif "$(body_of "$wi")"
echo "  POST /api/whatif (15 % off) -> $(get whatif_status) $(get whatif)"

echo "4/5 decision (Postgres before / after)"
put pg_before "$(sql_count "bigbox_ops_pg.app.reorder_decisions")"
dec="$(call POST /api/decisions "{\"store_id\":\"$STORE\",\"sku_id\":\"$SKU\",\"action\":\"reject\",\"reason\":\"HTTP smoke test (scripts/smoke_test_app.sh)\"}")"
put decision_status "$(status_of "$dec")"; put decision "$(body_of "$dec")"
put pg_after "$(sql_count "bigbox_ops_pg.app.reorder_decisions")"
DID="$(j "d['decision_id']" <<<"$(get decision)")"
echo "  POST /api/decisions -> $(get decision_status) $(get decision)"
echo "  Postgres app.reorder_decisions: $(get pg_before) -> $(get pg_after)"

echo "5/5 write-back (bigbox_refresh task write_back only) and Delta before / after"
put delta_before "$(sql_count "$CAT.gold.reorder_decisions")"
run="$(databricks jobs run-now --json "{\"job_id\": $REFRESH_JOB, \"only\": [\"write_back\"]}" -o json)"
put writeback_run_id "$(j "d['run_id']" <<<"$run")"
put writeback_result "$(j "d['state'].get('result_state')" <<<"$run")"
put delta_after "$(sql_count "$CAT.gold.reorder_decisions")"
put decision_in_delta "$(sql_scalar "SELECT count(*) FROM $CAT.gold.reorder_decisions WHERE decision_id = '$DID'")"
echo "  run $(get writeback_run_id): $(get writeback_result); Delta gold.reorder_decisions: $(get delta_before) -> $(get delta_after); decision $DID in Delta: $(get decision_in_delta)"
put finished "$(now)"
unset TOKEN

python3 - "$OUT" "$TMPD" <<'PY'
import json, os, sys
d = sys.argv[2]
r = {k: open(os.path.join(d, k)).read() for k in os.listdir(d)}
for k in ("health", "queue", "whatif", "decision"):
    try:
        r[k] = json.loads(r[k])
    except (KeyError, ValueError):
        pass
if isinstance(r.get("queue"), dict):
    r["queue"]["rows"] = r["queue"]["rows"][:1]
ok = all(r[k] in ("200", "201") for k in ("health_status", "queue_status", "whatif_status", "decision_status"))
r["passed"] = (ok and int(r["pg_after"]) == int(r["pg_before"]) + 1
               and int(r["delta_after"]) >= int(r["delta_before"]) + 1 and r["decision_in_delta"] == "1"
               and r["writeback_result"] == "SUCCESS")
json.dump(r, open(sys.argv[1], "w"), indent=1, sort_keys=True)
print(("PASS" if r["passed"] else "FAIL") + f": wrote {sys.argv[1]}")
sys.exit(0 if r["passed"] else 1)
PY
