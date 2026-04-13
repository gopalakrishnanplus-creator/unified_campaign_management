#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

bash tmp/docs/setup_demo_env.sh
source .venv/bin/activate

export REPORTING_API_USE_LIVE=false
export EXTERNAL_TICKETING_SYNC_ENABLED=false
export PWCLI="${PWCLI:-$HOME/.codex/skills/playwright/scripts/playwright_cli.sh}"

python manage.py check >/dev/null

SERVER_LOG="tmp/docs/devserver.log"
mkdir -p tmp/docs
SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]]; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if ! curl -fsS http://127.0.0.1:8002/ >/dev/null 2>&1; then
  python manage.py runserver 127.0.0.1:8002 >"$SERVER_LOG" 2>&1 &
  SERVER_PID=$!
  for _ in {1..30}; do
    if curl -fsS http://127.0.0.1:8002/ >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

python tmp/docs/capture_user_flow_screenshots.py
python tmp/docs/generate_user_flow_pack.py
bash tmp/docs/render_user_flow_pack.sh

echo "Training pack build complete."
