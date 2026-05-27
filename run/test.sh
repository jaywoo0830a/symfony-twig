#!/usr/bin/env bash
# run/test.sh — Run tests in Docker
#
# Usage:
#   ./run/test.sh                    # all tests
#   ./run/test.sh -k "filter"        # filter by keyword
#   ./run/test.sh tests/test_tags.py # single file
#   ./run/test.sh --cov              # with coverage report

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ARGS=("${@:-}")

echo "=== Running Tests (Docker) ==="
docker compose --profile ci build test
exec docker compose --profile ci run --rm test "${ARGS[@]}"
