#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1
cd "$(dirname "$0")/.."
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose is required for this optional demo." >&2
  exit 2
fi
docker compose down --remove-orphans >/dev/null 2>&1 || true
docker compose build
docker compose up -d controller telemetry auth-node-1 auth-node-2 auth-node-3
trap 'docker compose down --remove-orphans >/dev/null 2>&1 || true' EXIT
for _ in $(seq 1 30); do
  if curl -fsS http://localhost:8000/health >/dev/null; then break; fi
  sleep 1
done
curl -fsS -X POST http://localhost:8000/rollout/start | python3 -m json.tool
docker compose --profile replay run --rm replay
sleep 3
python3 -m telemetry.metrics
printf '\nOptional Docker demo complete. These outputs are diagnostic and are separate from the controlled replay reproduction path.\n'
