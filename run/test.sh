#!/usr/bin/env bash
# run/test.sh — Run tests (local venv or Docker)
#
# Usage:
#   ./run/test.sh               # local venv (default)
#   ./run/test.sh --docker      # Docker container
#   ./run/test.sh --cov         # local + coverage report
#   ./run/test.sh -k "test_if"  # filter specific tests
#   ./run/test.sh tests/test_lexer.py   # single file

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DOCKER_MODE=false
COV_MODE=false
PASS_THROUGH=()

for arg in "$@"; do
    case "$arg" in
        --docker) DOCKER_MODE=true ;;
        --cov)    COV_MODE=true ;;
        -h|--help)
            echo "Usage: ./run/test.sh [OPTIONS] [pytest args...]"
            echo "  (default)     Local venv"
            echo "  --docker      Run in Docker container"
            echo "  --cov         Coverage report (local only)"
            echo "  -k EXPR       Filter tests"
            echo "  tests/...     Specific file(s)"
            exit 0 ;;
        *) PASS_THROUGH+=("$arg") ;;
    esac
done

if $DOCKER_MODE; then
    echo "=== Docker Test ==="
    docker compose --profile ci build test
    exec docker compose --profile ci run --rm test "${PASS_THROUGH[@]}"
fi

# Local mode
echo "=== Local Test ==="
source .venv/bin/activate 2>/dev/null || true

if $COV_MODE; then
    exec python -m pytest "${PASS_THROUGH[@]:-tests/}" -v \
        --cov=twig_analyzer --cov-report=term-missing --cov-report=html:htmlcov
else
    exec python -m pytest "${PASS_THROUGH[@]:-tests/}" -v --tb=short
fi
