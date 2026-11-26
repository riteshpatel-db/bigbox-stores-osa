#!/usr/bin/env bash
# Run before every push. Fails if the full git history contains a denylisted term,
# looks like it holds a secret, or has a commit by anyone other than the expected author.
#
# The denylist lives OUTSIDE the repo (one term per line, case-insensitive) so the terms
# themselves are never committed. Default path: ../working/denylist.private.txt
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
DENYLIST="${DENYLIST:-../working/denylist.private.txt}"
EXPECTED_AUTHOR="ritesh-patel_data <ritesh.patel@databricks.com>"
fail=0

if [[ ! -s "$DENYLIST" ]] || ! grep -qv '^[[:space:]]*$' "$DENYLIST"; then
  echo "FAIL: denylist $DENYLIST is missing or empty; add the private terms first."
  exit 1
fi

history="$(git log -p --all --format='%H %an <%ae>%n%B')"

echo "1/3 denylisted terms in full history"
if grep -iqFf <(grep -v '^[[:space:]]*$' "$DENYLIST") <<<"$history"; then
  echo "FAIL: a denylisted term appears in the history. Rewrite history; do not add a fixing commit."
  fail=1
else
  echo "  ok"
fi

echo "2/3 secret patterns in full history"
secret_re='dapi[0-9a-f]{32}|dose[0-9a-f]{32}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----'
secret_re+='|xox[abpr]-[0-9A-Za-z-]{10,}|gh[pousr]_[0-9A-Za-z]{36}'
# A literal assigned to a password / secret / token: quoted (8+ characters, also as a JSON or YAML
# key), or an env-style KEY=value line whose value is not computed ($, (, {). Code that assigns a
# value obtained at runtime (e.g. `token = client.get_token()`) does not match; the earlier, broader
# pattern flagged such lines (four in the first commit, all runtime values, none a secret).
secret_re+='|(password|secret|token)[A-Za-z_]*["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"'][^[:space:]"'"'"']{8,}["'"'"']'
secret_re+='|^[+ ]?[[:space:]]*(export[[:space:]]+)?[A-Z_]*(PASSWORD|SECRET|TOKEN)[A-Z_]*=[^[:space:]$({"'"'"']{8,}'
if grep -iqE "$secret_re" <<<"$history"; then
  grep -inE "$secret_re" <<<"$history" | cut -c1-120
  echo "FAIL: possible secret in history."
  fail=1
else
  echo "  ok"
fi

echo "3/3 commit authors"
bad_authors="$(git log --all --format='%an <%ae>' | sort -u | grep -vxF "$EXPECTED_AUTHOR" || true)"
if [[ -n "$bad_authors" ]]; then
  echo "FAIL: unexpected author(s): $bad_authors"
  fail=1
else
  echo "  ok"
fi

exit "$fail"
