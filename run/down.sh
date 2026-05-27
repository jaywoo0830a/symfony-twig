#!/usr/bin/env bash
# run/down.sh — Stop Twig Analyzer services
#
# Usage:
#   ./run/down.sh              # stop all
#   ./run/down.sh --clean      # stop + remove images/volumes
#   ./run/down.sh --logs       # show logs before stopping

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CLEAN=false
SHOW_LOGS=false

for arg in "$@"; do
    case "$arg" in
        --clean) CLEAN=true ;;
        --logs)  SHOW_LOGS=true ;;
        -h|--help)
            echo "Usage: ./run/down.sh [--clean] [--logs]"
            exit 0 ;;
        *) echo "Unknown: $arg"; exit 1 ;;
    esac
done

$SHOW_LOGS && docker compose logs --tail=50 2>/dev/null || true

echo "Stopping..."
docker compose --profile dev down 2>/dev/null || true
docker compose --profile ci down 2>/dev/null || true
docker compose --profile tools down 2>/dev/null || true
docker compose down 2>/dev/null || true

if $CLEAN; then
    docker rmi twig-analyzer-lsp twig-analyzer-dev twig-analyzer-test 2>/dev/null || true
    docker compose down -v 2>/dev/null || true
    echo "Images & volumes removed."
fi

echo "Done."
