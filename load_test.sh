#!/bin/bash
# Load tester for code-reviewer
# Launches reviews of 20 public Python repos, one every ~2 minutes, for N cycles.
# Usage: ./load_test.sh [cycles]   (default: 1 cycle, ~40 minutes)

set -euo pipefail

CYCLES="${1:-1}"
INTERVAL_SECONDS=1 # 2 minutes between launches

REPOS=(
  # Small/medium repos (all use 'main' as default branch)
  "https://github.com/pallets/click"
  "https://github.com/encode/starlette"
  "https://github.com/pallets/markupsafe"
  "https://github.com/pallets/itsdangerous"
  "https://github.com/encode/uvicorn"
  "https://github.com/sloria/environs"
  "https://github.com/willmcgugan/textual"
  "https://github.com/mitmproxy/pdoc"
  "https://github.com/pallets/jinja"
  "https://github.com/pallets/werkzeug"
  "https://github.com/pallets/quart"
  "https://github.com/python-attrs/attrs"
  "https://github.com/psf/requests"
  "https://github.com/psf/black"
  "https://github.com/celery/celery"
  "https://github.com/python-poetry/poetry"
  "https://github.com/encode/django-rest-framework"
  "https://github.com/pytest-dev/pytest"
  "https://github.com/pydantic/pydantic"
  # One larger repo
  "https://github.com/pallets/flask"
)

TOTAL_REPOS=${#REPOS[@]}
LOG_DIR="load_test_logs"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SUMMARY_LOG="$LOG_DIR/summary_${TIMESTAMP}.log"

echo "=== Code Reviewer Load Test ===" | tee "$SUMMARY_LOG"
echo "Cycles: $CYCLES" | tee -a "$SUMMARY_LOG"
echo "Repos per cycle: $TOTAL_REPOS" | tee -a "$SUMMARY_LOG"
echo "Interval: ${INTERVAL_SECONDS}s between launches" | tee -a "$SUMMARY_LOG"
echo "Estimated time: $((CYCLES * TOTAL_REPOS * INTERVAL_SECONDS / 60)) minutes" | tee -a "$SUMMARY_LOG"
echo "Started at: $(date)" | tee -a "$SUMMARY_LOG"
echo "---" | tee -a "$SUMMARY_LOG"

PASS=0
FAIL=0

for ((cycle = 1; cycle <= CYCLES; cycle++)); do
  echo "" | tee -a "$SUMMARY_LOG"
  echo "=== Cycle $cycle of $CYCLES ===" | tee -a "$SUMMARY_LOG"

  for ((i = 0; i < TOTAL_REPOS; i++)); do
    REPO="${REPOS[$i]}"
    REPO_NAME=$(basename "$REPO")
    RUN_LOG="$LOG_DIR/${TIMESTAMP}_c${cycle}_${REPO_NAME}.log"

    echo "[$(date +%H:%M:%S)] Cycle $cycle | Repo $((i + 1))/$TOTAL_REPOS | $REPO_NAME" | tee -a "$SUMMARY_LOG"

    if ./run "$REPO" >"$RUN_LOG" 2>&1; then
      echo "  -> SUCCESS" | tee -a "$SUMMARY_LOG"
      PASS=$((PASS + 1))
    else
      EXIT_CODE=$?
      echo "  -> FAILED (exit $EXIT_CODE) — see $RUN_LOG" | tee -a "$SUMMARY_LOG"
      FAIL=$((FAIL + 1))
    fi

    # Sleep between launches (skip after the last repo of the last cycle)
    if [[ $cycle -lt $CYCLES || $i -lt $((TOTAL_REPOS - 1)) ]]; then
      echo "  Waiting ${INTERVAL_SECONDS}s before next launch..."
      sleep "$INTERVAL_SECONDS"
    fi
  done
done

echo "" | tee -a "$SUMMARY_LOG"
echo "=== Load Test Complete ===" | tee -a "$SUMMARY_LOG"
echo "Finished at: $(date)" | tee -a "$SUMMARY_LOG"
echo "Passed: $PASS  Failed: $FAIL  Total: $((PASS + FAIL))" | tee -a "$SUMMARY_LOG"
echo "Logs in: $LOG_DIR/"
