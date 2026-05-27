#!/usr/bin/env bash
# vscode-extension/install.sh — Install Twig extension into VS Code
# ============================================================================
# Prerequisite: Docker Desktop (nothing else needed)
set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
EXT_NAME="twig-static-analyzer"
RUNTIME_IMAGE="twig-analyzer-lsp:latest"
COMPILE_IMAGE="twig-analyzer-compile:latest"

# ── Colors ───────────────────────────────────────────────────────────
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; BOLD=''; NC=''
fi
ok()   { printf "${GREEN}  ✓${NC} %s\n" "$1"; }
warn() { printf "${YELLOW}  !${NC} %s\n" "$1"; }
err()  { printf "${RED}  ✗${NC} %s\n" "$1"; }
info() { printf "${CYAN}%s${NC}\n" "$1"; }
step() { printf "\n${YELLOW}[%s]${NC} ${BOLD}%s${NC}\n" "$1" "$2"; }

# ── Help ─────────────────────────────────────────────────────────────
usage() {
    echo "Usage: bash vscode-extension/install.sh"
    echo ""
    echo "Installs the Twig Static Analyzer VS Code extension."
    echo "Requirements: Docker Desktop only."
    exit 0
}
[ "${1:-}" = "--help" ] && usage

# ── VS Code discovery ────────────────────────────────────────────────
find_vscode_ext_dir() {
    for d in \
        "${HOME}/.vscode-server/extensions" \
        "${HOME}/.vscode/extensions" \
        "${HOME}/.vscode-insiders/extensions" \
        "${HOME}/.vscode-server-insiders/extensions"; do
        [ -d "$d" ] && { echo "$d"; return; }
    done
    local fb="${HOME}/.vscode/extensions"
    mkdir -p "$fb"
    echo "$fb"
}

VSCODE_EXT_DIR=$(find_vscode_ext_dir)
EXT_DIR="${VSCODE_EXT_DIR}/${EXT_NAME}"

# ── Docker helpers ───────────────────────────────────────────────────
require_docker() {
    command -v docker >/dev/null 2>&1 || {
        err "Docker not found. Install from https://docker.com"
        exit 1
    }
}

build_runtime() {
    if docker image inspect "$RUNTIME_IMAGE" >/dev/null 2>&1; then
        ok "Runtime image: $RUNTIME_IMAGE"
        return 0
    fi
    info "Building runtime image (one-time)..."
    cd "$PROJECT_ROOT"
    docker build --target runtime -t "$RUNTIME_IMAGE" . >/dev/null 2>&1 || {
        err "Docker build failed. Is Docker running?"
        return 1
    }
    ok "Runtime image built"
}

compile_typescript() {
    info "Compiling TypeScript via Docker..."
    cd "$PROJECT_ROOT"
    docker build --target compile -t "$COMPILE_IMAGE" . >/dev/null 2>&1 || {
        err "TypeScript compilation failed"
        return 1
    }
    ok "TypeScript compiled + JSON generated"

    local cid
    cid=$(docker create "$COMPILE_IMAGE" 2>/dev/null)
    [ -z "$cid" ] && { err "Failed to create container"; return 1; }

    rm -rf "${SCRIPT_DIR}/out" "${SCRIPT_DIR}/src/data" 2>/dev/null || true
    docker cp "$cid:/build/out" "${SCRIPT_DIR}/out" >/dev/null 2>&1 || {
        docker rm "$cid" >/dev/null 2>&1
        err "Failed to extract compiled output"
        return 1
    }
    mkdir -p "${SCRIPT_DIR}/src/data"
    docker cp "$cid:/build/src/data/." "${SCRIPT_DIR}/src/data/" >/dev/null 2>&1 || true
    docker rm "$cid" >/dev/null 2>&1
    ok "Output extracted (out/ + src/data/)"
}

install_files() {
    mkdir -p "$EXT_DIR/src/data"
    cp "${SCRIPT_DIR}/package.json"                     "$EXT_DIR/"
    cp -r "${SCRIPT_DIR}/out"                           "$EXT_DIR/"
    cp -r "${SCRIPT_DIR}/src/data"                      "$EXT_DIR/src/" 2>/dev/null || true
    cp "${SCRIPT_DIR}/twig.tmLanguage.json"             "$EXT_DIR/"
    cp "${SCRIPT_DIR}/twig-language-configuration.json" "$EXT_DIR/"
    ok "Extension files → ${EXT_DIR}"
}

# ══════════════════════════════════════════════════════════════════════
header() {
    echo ""
    printf "${CYAN}╔══════════════════════════════════════════════╗${NC}\n"
    printf "${CYAN}║${NC}   %-42s ${CYAN}║${NC}\n" "$1"
    printf "${CYAN}╚══════════════════════════════════════════════╝${NC}\n"
    echo ""
}

header "Twig Static Analyzer – VS Code Installer"
info "  VS Code:  ${VSCODE_EXT_DIR}"
info "  Target:   ${EXT_DIR}"

step "1/2" "Checking prerequisites"
require_docker
ok "Docker: $(docker --version 2>&1 | head -1)"
[ -f "${SCRIPT_DIR}/package.json" ] || { err "package.json not found"; exit 1; }

step "2/2" "Building & installing"
build_runtime || exit 1
compile_typescript || exit 1
install_files

header "Installation Complete"
echo "  ► Reload Window:  Ctrl+Shift+P → Developer: Reload Window"
echo "  ► Open any .twig or .html.twig file"
echo ""
echo "  Requirements: Docker Desktop must be running"
echo "  Uninstall:    bash vscode-extension/uninstall.sh"
echo ""
