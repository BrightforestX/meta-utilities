#!/usr/bin/env bash
set -euo pipefail
RULE=${1:-formal/midspiral/rule-sandbox-lifecycle.yaml}
if [[ ! -f "$RULE" ]]; then
  echo "MIDSPIRAL_MISS: missing $RULE" >&2
  exit 1
fi
grep -q '^id:' "$RULE"
grep -q 'surrealql_assertion:' "$RULE"
grep -q 'midspiral:' "$RULE"
echo MIDSPIRAL_OK
