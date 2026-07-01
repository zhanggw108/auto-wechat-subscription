#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DATE="${AI_RADAR_RUN_DATE:-$(date +%F)}"
LOG_DIR="$ROOT/storage/logs"
LOG_FILE="$LOG_DIR/ai-radar-daily-$RUN_DATE.log"

mkdir -p "$LOG_DIR"
cd "$ROOT"

{
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ai-radar daily start date=$RUN_DATE"
  PYTHONPATH=apps/api .venv/bin/python -m ai_radar.cli run-scheduled \
    --date "$RUN_DATE" \
    --storage-root storage \
    --live-sources
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ai-radar daily succeeded date=$RUN_DATE"
} >>"$LOG_FILE" 2>&1
