#!/usr/bin/env bash
# run/test.sh — Run test suite in Docker
# ============================================================================
source "$(dirname "$0")/common.sh"

usage() {
    echo "Usage: run/test.sh [OPTIONS] [pytest args...]"
    echo ""
    echo "Options:"
    echo "  (default)     Run all 137 tests"
    echo "  -k EXPR        Filter tests by keyword"
    echo "  FILE           Run a specific test file"
    echo "  --help         Show this help"
    echo ""
    echo "Examples:"
    echo "  run/test.sh                           # all tests"
    echo "  run/test.sh -k \"filter\"             # filter tests"
    echo "  run/test.sh tests/test_tags.py        # single file"
    echo "  run/test.sh tests/test_lexer.py -v    # single file, verbose"
    exit 0
}

# ── Parse arguments ──────────────────────────────────────────────────
PYTEST_ARGS=()

for arg in "$@"; do
    case "$arg" in
        -h|--help) usage ;;
        *)         PYTEST_ARGS+=("$arg") ;;
    esac
done

require_docker

# ── Execute ──────────────────────────────────────────────────────────
header "Running Tests"
docker compose --profile ci build test
exec docker compose --profile ci run --rm test "${PYTEST_ARGS[@]}"
