#!/usr/bin/env bash
# run/down.sh — Stop Twig Analyzer services
# ============================================================================
source "$(dirname "$0")/common.sh"

usage() {
    echo "Usage: run/down.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  (default)  Stop all services"
    echo "  --clean    Stop + remove images, volumes, networks"
    echo "  --logs     Show recent logs before stopping"
    echo "  --help     Show this help"
    exit 0
}

# ── Parse arguments ──────────────────────────────────────────────────
CLEAN=false
SHOW_LOGS=false

for arg in "$@"; do
    case "$arg" in
        --clean) CLEAN=true ;;
        --logs)  SHOW_LOGS=true ;;
        -h|--help) usage ;;
        *)       err "Unknown option: $arg"; usage ;;
    esac
done

# ── Execute ──────────────────────────────────────────────────────────
$SHOW_LOGS && { info "Recent logs:"; compose logs --tail=50 2>/dev/null || true; echo; }

info "Stopping all services..."
compose_down
ok "Services stopped"

if $CLEAN; then
    info "Removing images..."
    docker rmi "$DOCKER_IMAGE" twig-analyzer-dev twig-analyzer-test twig-analyzer-compile 2>/dev/null || true
    compose down -v 2>/dev/null || true
    ok "Images & volumes removed"
fi
