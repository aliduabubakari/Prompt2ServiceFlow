#!/usr/bin/env bash

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
GENERATOR="$PROJECT_ROOT/scripts/generate_service_catalog.py"
MANIFEST="$PROJECT_ROOT/benchmark/manifest.jsonl"

PHASE="required"
SCOPE="main"
CONFIG="$PROJECT_ROOT/config/catalog_generation.yaml"
RUN_ID=""
EXECUTE=false
CONTINUE_ON_ERROR=false
RETRIES=1
RETRY_DELAY=10
BETWEEN_CALL_DELAY=2
LIMIT=""
START_AT=""

usage() {
  cat <<'EOF'
Run Prompt2ServiceFlow catalogue generation one pipeline at a time.

Usage:
  scripts/run_catalog_pipelines.sh [options]

Options:
  --phase required|distractors
                              Generation phase. Default: required.
  --scope main|validation|extension|all
                              Pipelines to process. Default: main.
  --config PATH               Generator configuration file.
  --run-id ID                 Override the configured run ID.
  --execute                   Make paid OpenAI API calls.
  --continue-on-error         Continue after a pipeline exhausts retries.
  --retries N                 Retries after the first failed attempt. Default: 1.
  --retry-delay SECONDS       Delay before retrying a failed pipeline. Default: 10.
  --between-call-delay SECONDS
                              Delay between successful pipelines. Default: 2.
  --start-at PIPELINE_ID      Skip entries before this pipeline or benchmark ID.
  --limit N                   Process at most N selected pipelines.
  -h, --help                  Show this help.

Without --execute, the script performs a dry run and only renders prompts.
Completed pipelines are skipped by the Python generator, so reruns are safe.

Examples:
  scripts/run_catalog_pipelines.sh --execute

  scripts/run_catalog_pipelines.sh \
    --phase distractors \
    --execute

  scripts/run_catalog_pipelines.sh \
  --scope all \
    --run-id gpt55-catalog-all110-v001 \
    --execute
EOF
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 2
}

require_nonnegative_integer() {
  case "$2" in
    ''|*[!0-9]*) die "$1 must be a non-negative integer" ;;
  esac
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --phase)
      [ "$#" -ge 2 ] || die "--phase requires a value"
      PHASE="$2"
      shift 2
      ;;
    --scope)
      [ "$#" -ge 2 ] || die "--scope requires a value"
      SCOPE="$2"
      shift 2
      ;;
    --config)
      [ "$#" -ge 2 ] || die "--config requires a value"
      CONFIG="$2"
      shift 2
      ;;
    --run-id)
      [ "$#" -ge 2 ] || die "--run-id requires a value"
      RUN_ID="$2"
      shift 2
      ;;
    --execute)
      EXECUTE=true
      shift
      ;;
    --continue-on-error)
      CONTINUE_ON_ERROR=true
      shift
      ;;
    --retries)
      [ "$#" -ge 2 ] || die "--retries requires a value"
      RETRIES="$2"
      require_nonnegative_integer "--retries" "$RETRIES"
      shift 2
      ;;
    --retry-delay)
      [ "$#" -ge 2 ] || die "--retry-delay requires a value"
      RETRY_DELAY="$2"
      require_nonnegative_integer "--retry-delay" "$RETRY_DELAY"
      shift 2
      ;;
    --between-call-delay)
      [ "$#" -ge 2 ] || die "--between-call-delay requires a value"
      BETWEEN_CALL_DELAY="$2"
      require_nonnegative_integer "--between-call-delay" "$BETWEEN_CALL_DELAY"
      shift 2
      ;;
    --start-at)
      [ "$#" -ge 2 ] || die "--start-at requires a value"
      START_AT="$2"
      shift 2
      ;;
    --limit)
      [ "$#" -ge 2 ] || die "--limit requires a value"
      LIMIT="$2"
      require_nonnegative_integer "--limit" "$LIMIT"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown option: $1"
      ;;
  esac
done

case "$PHASE" in
  required|distractors) ;;
  *) die "--phase must be required or distractors" ;;
esac

case "$SCOPE" in
  main|validation|extension|all) ;;
  *) die "--scope must be main, validation, extension, or all" ;;
esac

[ -f "$CONFIG" ] || die "configuration file not found: $CONFIG"
[ -f "$MANIFEST" ] || die "manifest not found: $MANIFEST"
[ -f "$GENERATOR" ] || die "generator not found: $GENERATOR"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "Python executable not found: $PYTHON_BIN"

if [ -z "$RUN_ID" ]; then
  RUN_ID="$(
    "$PYTHON_BIN" - "$CONFIG" <<'PY'
import sys
from pathlib import Path

import yaml

config = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(config["generation"]["run_id"])
PY
  )"
  case "$SCOPE" in
    extension)
      RUN_ID="${RUN_ID}-extension-v1"
      ;;
    all)
      RUN_ID="${RUN_ID}-all110"
      ;;
  esac
fi

case "$SCOPE" in
  main)
    SPLIT_ARGS=(--split main)
    ;;
  validation)
    SPLIT_ARGS=(--split validation)
    ;;
  extension)
    SPLIT_ARGS=(--split extension)
    ;;
  all)
    SPLIT_ARGS=(--split main --split validation --split extension)
    ;;
esac

PIPELINE_FILE="$(mktemp "${TMPDIR:-/tmp}/prompt2serviceflow-pipelines.XXXXXX")"
cleanup() {
  rm -f "$PIPELINE_FILE"
}
trap cleanup EXIT
trap 'cleanup; exit 130' INT TERM

if ! "$PYTHON_BIN" - "$MANIFEST" "$SCOPE" "$START_AT" "$LIMIT" >"$PIPELINE_FILE" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
scope = sys.argv[2]
start_at = sys.argv[3]
limit_text = sys.argv[4]
selected_splits = {"main", "validation", "extension"} if scope == "all" else {scope}

rows = [
    json.loads(line)
    for line in manifest_path.read_text(encoding="utf-8").splitlines()
    if line.strip()
]
rows = [row for row in rows if row["split"] in selected_splits]

if start_at:
    start_index = next(
        (
            index
            for index, row in enumerate(rows)
            if start_at in {row["pipeline_id"], row["benchmark_id"]}
        ),
        None,
    )
    if start_index is None:
        raise SystemExit(f"unknown --start-at pipeline: {start_at}")
    rows = rows[start_index:]

if limit_text:
    rows = rows[: int(limit_text)]

for row in rows:
    print(row["benchmark_id"])
PY
then
  die "could not select pipelines from the manifest"
fi

TOTAL="$(wc -l <"$PIPELINE_FILE" | tr -d ' ')"
[ "$TOTAL" -gt 0 ] || die "no pipelines selected"

LOG_ROOT="$PROJECT_ROOT/runs/catalog_generation/$RUN_ID/logs/$PHASE"
mkdir -p "$LOG_ROOT"
SUMMARY_LOG="$LOG_ROOT/runner-$(date -u +%Y%m%dT%H%M%SZ).log"

printf 'Catalog run: phase=%s scope=%s run_id=%s pipelines=%s execute=%s\n' \
  "$PHASE" "$SCOPE" "$RUN_ID" "$TOTAL" "$EXECUTE" | tee -a "$SUMMARY_LOG"

if [ "$EXECUTE" = true ]; then
  printf 'Paid API execution enabled. Completed responses will be skipped.\n' |
    tee -a "$SUMMARY_LOG"
else
  printf 'Dry run only. Add --execute to make API calls.\n' | tee -a "$SUMMARY_LOG"
fi

SUCCEEDED=0
FAILED=0
INDEX=0
FAILED_IDS=""

while IFS= read -r BENCHMARK_ID; do
  [ -n "$BENCHMARK_ID" ] || continue
  INDEX=$((INDEX + 1))
  SAFE_ID="$(printf '%s' "$BENCHMARK_ID" | tr ':/' '__')"
  PIPELINE_LOG="$LOG_ROOT/${SAFE_ID}.log"
  ATTEMPT=0
  MAX_ATTEMPTS=$((RETRIES + 1))
  PIPELINE_OK=false

  while [ "$ATTEMPT" -lt "$MAX_ATTEMPTS" ]; do
    ATTEMPT=$((ATTEMPT + 1))
    printf '\n[%s/%s] %s attempt %s/%s\n' \
      "$INDEX" "$TOTAL" "$BENCHMARK_ID" "$ATTEMPT" "$MAX_ATTEMPTS" |
      tee -a "$SUMMARY_LOG" "$PIPELINE_LOG"

    COMMAND=(
      "$PYTHON_BIN"
      "$GENERATOR"
      "$PHASE"
      --config "$CONFIG"
      --run-id "$RUN_ID"
      "${SPLIT_ARGS[@]}"
      --pipeline "$BENCHMARK_ID"
    )
    if [ "$EXECUTE" = true ]; then
      COMMAND+=(--execute)
    fi

    if "${COMMAND[@]}" 2>&1 | tee -a "$PIPELINE_LOG"; then
      PIPELINE_OK=true
      SUCCEEDED=$((SUCCEEDED + 1))
      printf '[%s/%s] completed %s\n' "$INDEX" "$TOTAL" "$BENCHMARK_ID" |
        tee -a "$SUMMARY_LOG"
      break
    fi

    if [ "$ATTEMPT" -lt "$MAX_ATTEMPTS" ]; then
      printf '[%s/%s] failed %s; retrying in %ss\n' \
        "$INDEX" "$TOTAL" "$BENCHMARK_ID" "$RETRY_DELAY" |
        tee -a "$SUMMARY_LOG"
      sleep "$RETRY_DELAY"
    fi
  done

  if [ "$PIPELINE_OK" != true ]; then
    FAILED=$((FAILED + 1))
    FAILED_IDS="${FAILED_IDS}${BENCHMARK_ID}\n"
    printf '[%s/%s] exhausted retries for %s\n' \
      "$INDEX" "$TOTAL" "$BENCHMARK_ID" | tee -a "$SUMMARY_LOG"
    if [ "$CONTINUE_ON_ERROR" != true ]; then
      printf 'Stopping. Re-run the same command to resume from this pipeline.\n' |
        tee -a "$SUMMARY_LOG"
      break
    fi
  elif [ "$INDEX" -lt "$TOTAL" ] && [ "$BETWEEN_CALL_DELAY" -gt 0 ]; then
    sleep "$BETWEEN_CALL_DELAY"
  fi
done <"$PIPELINE_FILE"

printf '\nSummary: succeeded=%s failed=%s selected=%s\n' \
  "$SUCCEEDED" "$FAILED" "$TOTAL" | tee -a "$SUMMARY_LOG"

if [ "$FAILED" -gt 0 ]; then
  printf 'Failed pipelines:\n%b' "$FAILED_IDS" | tee -a "$SUMMARY_LOG"
  exit 1
fi

"$PYTHON_BIN" "$GENERATOR" status \
  --config "$CONFIG" \
  --run-id "$RUN_ID" \
  "${SPLIT_ARGS[@]}" | tee -a "$SUMMARY_LOG"
