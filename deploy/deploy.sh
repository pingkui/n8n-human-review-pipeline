#!/usr/bin/env bash
# Imports the workflow, publishes it, starts n8n and the inbox. Needs deploy/.env (see .env.example).
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "missing deploy/.env (copy .env.example and fill it in)"; exit 1; }
docker compose pull -q
docker compose run --rm --no-deps --entrypoint n8n n8n import:workflow --input=/work/workflow.json
docker compose run --rm --no-deps --entrypoint n8n n8n publish:workflow --id=contentReview01
docker compose up -d
echo "waiting for the webhook to register..."
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST localhost:5678/webhook/content-request \
         -H 'Content-Type: application/json' -d '{"client":"?","topic":"?"}' || true)
  [ "$code" = 400 ] && { echo "ready: inbox http://127.0.0.1:8089  n8n http://127.0.0.1:5678"; exit 0; }
  sleep 3
done
echo "n8n did not register the webhook in time; see: docker compose logs n8n"; exit 1
