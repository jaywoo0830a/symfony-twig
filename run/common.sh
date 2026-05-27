#!/usr/bin/env bash
# run/common.sh — Shared utilities for all run/*.sh scripts.
# Source this file:  source "$(dirname "$0")/common.sh"

set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_IMAGE="twig-analyzer-lsp:latest"
COMPOSE_FILE="$ROOT/docker-compose.yml"

# ── Colors ───────────────────────────────────────────────────────────
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; BOLD=''; NC=''
fi

# ── Logging ──────────────────────────────────────────────────────────
ok()   { printf "${GREEN}  ✓${NC} %s\n" "$1"; }
warn() { printf "${YELLOW}  !${NC} %s\n" "$1"; }
err()  { printf "${RED}  ✗${NC} %s\n" "$1"; }
info() { printf "${CYAN}%s${NC}\n" "$1"; }
header() {
    printf "\n${CYAN}╔══════════════════════════════════════════════╗${NC}\n"
    printf "${CYAN}║${NC}   %-42s ${CYAN}║${NC}\n" "$1"
    printf "${CYAN}╚══════════════════════════════════════════════╝${NC}\n\n"
}
step() { printf "\n${YELLOW}[%s]${NC} ${BOLD}%s${NC}\n" "$1" "$2"; }

# ── Docker checks ────────────────────────────────────────────────────
require_docker() {
    command -v docker >/dev/null 2>&1 || {
        err "Docker not found. Install Docker Desktop from https://docker.com"
        exit 1
    }
}

# ── Compose helpers ──────────────────────────────────────────────────
compose() {
    docker compose -f "$COMPOSE_FILE" "$@"
}

compose_up() {
    local profile="${1:-}"
    local flags="${2:-}"
    if [ -n "$profile" ]; then
        compose --profile "$profile" up -d $flags
    else
        compose up -d $flags
    fi
}

compose_down() {
    compose --profile dev  down 2>/dev/null || true
    compose --profile ci   down 2>/dev/null || true
    compose --profile tools down 2>/dev/null || true
    compose                down 2>/dev/null || true
}
