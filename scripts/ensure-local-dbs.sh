#!/usr/bin/env bash
# Portable health check + guidance for the three local stores required for full meta-utilities experience.
# Weaviate (vector), Postgres (optional), SurrealDB (governed primary for research-memory + ODRS LinkML-shaped entities).
# Pure sim paths are never blocked. Memory/context "hit" paths, oteemo+context, ink governed-memory, and research-memory
# augmented asks require the stores (with user prompt in TUI via the ensure pre-flight).
# Two-layer timeouts protect against slow/misconfigured stores.

set -euo pipefail

COMPOSE_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/templates/local-dbs/docker-compose.yml"

have() { command -v "$1" >/dev/null 2>&1; }

check_port() {
  local host="$1" port="$2"
  if have python3; then
    python3 - <<PY
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(0.5)
try:
    s.connect((sys.argv[1], int(sys.argv[2])))
    print("open")
except Exception:
    print("closed")
finally:
    s.close()
PY
 "$host" "$port"
  elif have nc; then
    nc -z -w 1 "$host" "$port" && echo "open" || echo "closed"
  else
    # last resort: /dev/tcp (bash)
    (echo > "/dev/tcp/$host/$port") >/dev/null 2>&1 && echo "open" || echo "closed"
  fi
}

WEAVIATE_URL="${WEAVIATE_URL:-http://localhost:8080}"
SURREAL_URL="${SURREAL_URL:-ws://localhost:8000}"
POSTGRES_DSN="${POSTGRES_DSN:-postgresql://meta:meta@localhost:5432/meta}"

weaviate_host_port=$(echo "$WEAVIATE_URL" | sed -E 's#https?://##; s#/.+##')
surreal_host_port=$(echo "$SURREAL_URL" | sed -E 's#ws://##; s#/.+##')
pg_host=$(echo "$POSTGRES_DSN" | sed -E 's#.*@##; s#:[0-9]+/.*##')
pg_port=$(echo "$POSTGRES_DSN" | sed -E 's#.*:([0-9]+)/.*#\1#')

echo "Checking local DB health (non-blocking for pure sim)..."
w=$(check_port "${weaviate_host_port%:*}" "${weaviate_host_port#*:}")
s=$(check_port "${surreal_host_port%:*}" "${surreal_host_port#*:}")
p=$(check_port "$pg_host" "$pg_port")

printf "  Weaviate  %s  (%s)\n" "$w" "$WEAVIATE_URL"
printf "  SurrealDB %s  (%s)\n" "$s" "$SURREAL_URL"
printf "  Postgres  %s  (%s)\n" "$p" "$POSTGRES_DSN"

if [[ "$1" == "--up" || "$1" == "up" ]]; then
  if have docker && [[ -f "$COMPOSE_FILE" ]]; then
    echo "Bringing up via docker compose..."
    docker compose -f "$COMPOSE_FILE" up -d weaviate postgres surreal
    echo "Waiting for health..."
    for i in {1..30}; do
      w=$(check_port "${weaviate_host_port%:*}" "${weaviate_host_port#*:}")
      s=$(check_port "${surreal_host_port%:*}" "${surreal_host_port#*:}")
      p=$(check_port "$pg_host" "$pg_port")
      if [[ "$w" == "open" && "$s" == "open" && "$p" == "open" ]]; then
        echo "All three stores healthy."
        break
      fi
      sleep 1
    done
  else
    echo "docker or compose file not available; start the services manually and export the URLs above."
  fi
fi

echo
echo "Recommended exports (localhost defaults):"
echo "  export WEAVIATE_URL=$WEAVIATE_URL"
echo "  export SURREAL_URL=$SURREAL_URL"
echo "  export POSTGRES_DSN='$POSTGRES_DSN'"
echo "  export SCENARIO_RESEARCH_TIMEOUT_SEC=1800   # client layer; host tool_timeouts is the second layer"
echo
echo "For full experience (research-memory hits, context-forge long-horizon, ODRS governed traces + LiveBusinessContext, ink 'ask' + memory):"
echo "  stores must be reachable. Pure simulation + px context pulls remain fully functional without them."
echo "  See templates/local-dbs/docker-compose.yml and the root AGENTS.md + docs/memory*."
