#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
QNT=${1:-$ROOT/formal/quint/smoke.qnt}
if [[ ! -f "$QNT" ]]; then
  mkdir -p "$(dirname "$QNT")"
  cat > "$QNT" <<'Q'
module smoke {
  var n: int
  action Init = { n' = 1 }
  action Next = { n' = n }
  val Positive = n > 0
}
Q
fi
grep -q 'module smoke' "$QNT"
if command -v quint >/dev/null; then
  quint typecheck "$QNT"
else
  npx --yes @informalsystems/quint@0.32.0 typecheck "$QNT"
fi
echo FORMAL_SMOKE_OK
