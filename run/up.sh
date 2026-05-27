#!/usr/bin/env bash
# run/up.sh — Start Twig Analyzer services
#
# Usage:
#   ./run/up.sh                  # production LSP (TCP :2087)
#   ./run/up.sh --dev            # development + hot-reload (TCP :2088)
#   ./run/up.sh --stdio          # stdio mode (editor pipe)
#   ./run/up.sh --cli "args"     # run CLI command
#   ./run/up.sh --all            # all services (prod + dev)
#   ./run/up.sh --build          # force rebuild

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODE="prod"
BUILD_FLAG=""

for arg in "$@"; do
    case "$arg" in
        --dev)     MODE="dev" ;;
        --stdio)   MODE="stdio" ;;
        --cli)     MODE="cli"; CLI_ARGS="${*:2}"; break ;;
        --build)   BUILD_FLAG="--build" ;;
        --all)     MODE="all" ;;
        -h|--help) MODE="help" ;;
        *)         echo "Unknown: $arg"; exit 1 ;;
    esac
done

case "$MODE" in
    help)
        echo "Usage: ./run/up.sh [MODE]"
        echo "  (default)  Production LSP  → :2087"
        echo "  --dev      Dev + hot-reload → :2088"
        echo "  --stdio    Editor pipe mode"
        echo "  --cli ...  Run CLI command"
        echo "  --all      All services"
        echo "  --build    Force rebuild"
        exit 0 ;;
    stdio)
        docker build --target runtime -t twig-analyzer-lsp .
        exec docker run -i --rm -v "$ROOT:/workspace:ro" twig-analyzer-lsp ;;
    dev)
        docker compose --profile dev up -d $BUILD_FLAG lsp-dev
        echo "Dev → http://localhost:2088" ;;
    all)
        docker compose --profile dev up -d $BUILD_FLAG
        echo "Prod → :2087  |  Dev → :2088" ;;
    cli)
        shift 2 2>/dev/null || true
        docker compose --profile tools build $BUILD_FLAG cli
        docker compose --profile tools run --rm cli ${CLI_ARGS:-$*} ;;
    *)
        docker compose up -d $BUILD_FLAG lsp
        echo "LSP → http://localhost:2087" ;;
esac

echo "Status: docker compose ps  |  Stop: ./run/down.sh"
