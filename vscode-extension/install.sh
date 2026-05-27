#!/usr/bin/env bash
# Twig Static Analyzer – VS Code Extension Installer (Docker-only)
# Prerequisite: Docker Desktop installed and running. Nothing else needed.
set -euo pipefail

detect_os() {
    case "$(uname -s)" in Darwin) echo "macos" ;; Linux) grep -qi microsoft /proc/version 2>/dev/null && echo "wsl" || echo "linux" ;; MINGW*|MSYS*|CYGWIN*) echo "windows" ;; *) echo "unknown" ;; esac
}

OS=$(detect_os)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
EXT_NAME="twig-static-analyzer"
DOCKER_IMAGE="twig-analyzer-lsp:latest"
COMPILE_IMAGE="twig-analyzer-compile:latest"

# ── Colors ──
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
else RED=''; GREEN=''; YELLOW=''; CYAN=''; BOLD=''; NC=''; fi
ok()   { printf "${GREEN}  ✓${NC} %s\n" "$1"; }
warn() { printf "${YELLOW}  !${NC} %s\n" "$1"; }
err()  { printf "${RED}  ✗${NC} %s\n" "$1"; }
info() { printf "${CYAN}%s${NC}\n" "$1"; }
step() { printf "\n${YELLOW}[%s]${NC} ${BOLD}%s${NC}\n" "$1" "$2"; }

# ── Find VS Code extensions dir ──
find_vscode_ext_dir() {
    for d in "${HOME}/.vscode-server/extensions" "${HOME}/.vscode/extensions" "${HOME}/.vscode-insiders/extensions" "${HOME}/.vscode-server-insiders/extensions"; do [ -d "$d" ] && { echo "$d"; return; }; done
    local fb="${HOME}/.vscode/extensions"; mkdir -p "$fb"; echo "$fb"
}

VSCODE_EXT_DIR=$(find_vscode_ext_dir)
EXT_DIR="${VSCODE_EXT_DIR}/${EXT_NAME}"
has_docker() { command -v docker >/dev/null 2>&1; }

# ── Build Docker images ──
build_images() {
    if docker image inspect "$DOCKER_IMAGE" >/dev/null 2>&1; then
        ok "Runtime image: $DOCKER_IMAGE"
    else
        info "Building runtime image..."
        cd "$PROJECT_ROOT"
        docker build --target runtime -t "$DOCKER_IMAGE" . >/dev/null 2>&1 || { err "Docker build failed"; return 1; }
        ok "Runtime image built"
    fi

    info "Compiling TypeScript (Docker)..."
    cd "$PROJECT_ROOT"
    docker build --target compile -t "$COMPILE_IMAGE" . >/dev/null 2>&1 || { err "TypeScript compilation failed"; return 1; }
    ok "TypeScript compiled via Docker"
}

# ── Extract compiled output from Docker ──
extract_output() {
    local cid; cid=$(docker create "$COMPILE_IMAGE" 2>/dev/null)
    [ -z "$cid" ] && { err "Failed to create container"; return 1; }
    rm -rf "${SCRIPT_DIR}/out" 2>/dev/null || true
    docker cp "$cid:/build/out" "${SCRIPT_DIR}/out" 2>/dev/null || { docker rm "$cid" >/dev/null 2>&1; err "Failed to extract out/"; return 1; }
    docker rm "$cid" >/dev/null 2>&1
    ok "Compiled output extracted to out/"
}

# ── Copy extension files ──
install_files() {
    mkdir -p "$EXT_DIR/src/data"
    cp "${SCRIPT_DIR}/package.json"                     "$EXT_DIR/"
    cp -r "${SCRIPT_DIR}/out"                           "$EXT_DIR/"
    cp -r "${SCRIPT_DIR}/src/data"                      "$EXT_DIR/src/" 2>/dev/null || true
    cp "${SCRIPT_DIR}/twig.tmLanguage.json"             "$EXT_DIR/"
    cp "${SCRIPT_DIR}/twig-language-configuration.json" "$EXT_DIR/"
    ok "Extension files copied to ${EXT_DIR}"
}

# ══════════════════════════════════════════════════════════════════════
echo ""
info "╔══════════════════════════════════════════════╗"
info "║   Twig Static Analyzer – VS Code Installer   ║"
info "╚══════════════════════════════════════════════╝"
echo ""
info "  OS:       ${OS}"
info "  VS Code:  ${VSCODE_EXT_DIR}"
echo ""

step "1/3" "Checking prerequisites..."
has_docker || { err "Docker not found. Install Docker Desktop from https://docker.com"; exit 1; }
ok "Docker: $(docker --version 2>&1 | head -1)"

step "2/3" "Building (Docker)..."
build_images || exit 1
extract_output || exit 1

step "3/3" "Installing extension..."
install_files

echo ""
info "╔══════════════════════════════════════════════╗"
info "║           Installation Complete!              ║"
info "╚══════════════════════════════════════════════╝"
echo ""
echo "  ► Restart VS Code: Ctrl+Shift+P → Developer: Reload Window"
echo "  ► Open any .twig or .html.twig file"
echo ""
echo "  Requirements: Docker Desktop running"
echo "  Uninstall:    rm -rf ${EXT_DIR}"
