#!/usr/bin/env bash
# run/up.sh — Start Twig Analyzer services
# ============================================================================
source "$(dirname "$0")/common.sh"

usage() {
    echo "Usage: run/up.sh [MODE]"
    echo ""
    echo "Modes:"
    echo "  (default)  Start production LSP server       → http://localhost:2087"
    echo "  --dev      Start dev server (hot-reload)     → http://localhost:2088"
    echo "  --stdio    Run LSP in stdio mode             → for editor piping"
    echo "  --cli ...  Run one-shot CLI command          → e.g. --cli \"analyze templates/\""
    echo "  --build    Force rebuild Docker images"
    echo "  --help     Show this help"
    exit 0
}

# ── Parse arguments ──────────────────────────────────────────────────
MODE="prod"
BUILD_FLAG=""

for arg in "$@"; do
    case "$arg" in
        --dev)     MODE="dev" ;;
        --stdio)   MODE="stdio" ;;
        --cli)     MODE="cli"; CLI_ARGS="${*:2}"; break ;;
        --build)   BUILD_FLAG="--build" ;;
        -h|--help) usage ;;
        *)         err "Unknown option: $arg"; usage ;;
    esac
done

require_docker

# ── Execute ──────────────────────────────────────────────────────────
case "$MODE" in
    stdio)
        info "LSP Server (stdio mode)"
        docker build --target runtime -t "$DOCKER_IMAGE" "$ROOT"
        exec docker run -i --rm -v "$ROOT:/workspace:ro" "$DOCKER_IMAGE"
        ;;
    dev)
        info "Starting dev server (hot-reload)..."
        compose_up dev "$BUILD_FLAG"
        ok "Dev server → http://localhost:2088"
        ;;
    cli)
        shift 2 2>/dev/null || true
        info "twig-analyze ${CLI_ARGS:-$*}"
        compose build cli
        exec docker compose run --rm cli ${CLI_ARGS:-$*}
        ;;
    *)
        info "Starting production server..."
        compose_up "" "$BUILD_FLAG"
        ok "LSP Server → http://localhost:2087"
        ;;
esac

echo ""
info "Status:  docker compose ps"
info "Logs:    docker compose logs -f"
info "Stop:    run/down.sh"
