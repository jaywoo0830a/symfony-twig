#!/usr/bin/env bash
# vscode-extension/uninstall.sh — Remove Twig extension from VS Code
# ============================================================================
# Usage:
#   bash vscode-extension/uninstall.sh            # uninstall extension
#   bash vscode-extension/uninstall.sh --docker   # also remove Docker images
#   bash vscode-extension/uninstall.sh --clean    # remove project artifacts too
#   bash vscode-extension/uninstall.sh --help     # show help
#
# Safe: removes extension dirs + cleans extensions.json entries.
# Idempotent: safe to run even if nothing is installed.
# ============================================================================
set -euo pipefail

readonly EXT_NAME="twig-static-analyzer"
readonly EXT_ID="twig-analyzer.${EXT_NAME}"
readonly RUNTIME_IMAGE="twig-analyzer-lsp:latest"
readonly COMPILE_IMAGE="twig-analyzer-compile:latest"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REMOVE_DOCKER=0
CLEAN_ARTIFACTS=0

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

# ── Help ─────────────────────────────────────────────────────────────
usage() {
    cat <<'EOF'
Usage:  bash vscode-extension/uninstall.sh [OPTIONS]

Removes the Twig Static Analyzer extension from VS Code.

Options:
  --docker   Also remove Docker images (twig-analyzer-lsp, twig-analyzer-compile)
  --clean    Also remove local build artifacts (out/, src/data/, .backups/)
  --help     Show this help

After uninstall, reload VS Code: Ctrl+Shift+P → Developer: Reload Window
EOF
    exit 0
}

for arg in "$@"; do
    case "$arg" in
        --docker) REMOVE_DOCKER=1 ;;
        --clean)  CLEAN_ARTIFACTS=1 ;;
        --help)   usage ;;
        *)        warn "Unknown flag: $arg"; usage ;;
    esac
done

# ── Find installed extension dirs ────────────────────────────────────
_find_installed_dirs() {
    local found=()
    for base in \
        "${HOME}/.vscode-server/extensions" \
        "${HOME}/.vscode/extensions" \
        "${HOME}/.vscode-insiders/extensions" \
        "${HOME}/.vscode-server-insiders/extensions"; do
        local d="${base}/${EXT_NAME}"
        [ -d "$d" ] && found+=("$d")
    done
    printf '%s\n' "${found[@]}"
}

# ── Remove from extensions.json ─────────────────────────────────────
_cleanup_extensions_json() {
    local ext_json="$1"
    [ -f "$ext_json" ] || return 0
    chmod u+w "$ext_json" 2>/dev/null || true

    if command -v python3 >/dev/null 2>&1; then
        python3 -c "
import json, os, sys

ext_json = '${ext_json}'
try:
    data = json.load(open(ext_json))
except Exception:
    sys.exit(0)  # malformed or missing — leave alone, not an error

before = len(data)
data = [e for e in data if e.get('identifier',{}).get('id') != '${EXT_ID}']

if len(data) < before:
    json.dump(data, open(ext_json, 'w'), indent=2)
    print('  ✓ Cleaned ${ext_json}')
" 2>&1 || warn "Failed to clean ${ext_json}"
    elif command -v node >/dev/null 2>&1; then
        node -e "
const fs = require('fs');
try {
    let data = JSON.parse(fs.readFileSync('${ext_json}','utf8'));
    const before = data.length;
    data = data.filter(e => (e.identifier||{}).id !== '${EXT_ID}');
    if (data.length < before) {
        fs.writeFileSync('${ext_json}', JSON.stringify(data, null, 2));
        console.log('  ✓ Cleaned ${ext_json}');
    }
} catch(_) { process.exit(0); }
" 2>&1 || warn "Failed to clean ${ext_json}"
    else
        warn "Cannot clean ${ext_json} — python3/node not available"
    fi
}

# ── Remove Docker images ─────────────────────────────────────────────
_remove_docker_images() {
    info "Removing Docker images..."
    for img in "$RUNTIME_IMAGE" "$COMPILE_IMAGE"; do
        if docker image inspect "$img" >/dev/null 2>&1; then
            docker rmi "$img" >/dev/null 2>&1 && ok "Removed $img" || warn "Could not remove $img"
        else
            ok "Image not present: $img"
        fi
    done
    # Prune dangling build cache
    docker image prune -f >/dev/null 2>&1 || true
}

# ── Clean local artifacts ────────────────────────────────────────────
_clean_artifacts() {
    info "Cleaning local build artifacts..."
    local cleaned=0
    for d in "${SCRIPT_DIR}/out" "${SCRIPT_DIR}/src/data" "${SCRIPT_DIR}/.backups"; do
        if [ -d "$d" ]; then
            rm -rf "$d" && ok "Removed $d" && cleaned=1
        fi
    done
    [ "$cleaned" -eq 0 ] && ok "No artifacts to clean"
}

# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

_header() {
    echo ""
    printf "${CYAN}╔══════════════════════════════════════════════╗${NC}\n"
    printf "${CYAN}║${NC}   %-42s ${CYAN}║${NC}\n" "$1"
    printf "${CYAN}╚══════════════════════════════════════════════╝${NC}\n"
    echo ""
}

_header "Twig Static Analyzer – VS Code Uninstaller"

# ── 1. Remove extension directories ──────────────────────────────────
DIRS=$(_find_installed_dirs | xargs -r echo)

if [ -z "${DIRS:-}" ]; then
    info "Extension directory not found on disk."
else
    info "Removing Twig Static Analyzer extension..."
    for d in $DIRS; do
        rm -rf "$d" && ok "Removed $d" || err "Failed to remove $d"
    done
fi

# ── 2. Clean extensions.json entries ─────────────────────────────────
info "Cleaning extension registry (extensions.json)..."
for base in \
    "${HOME}/.vscode-server/extensions" \
    "${HOME}/.vscode/extensions" \
    "${HOME}/.vscode-insiders/extensions" \
    "${HOME}/.vscode-server-insiders/extensions"; do
    _cleanup_extensions_json "${base}/extensions.json"
done

# ── 3. Optional: Docker images ───────────────────────────────────────
if [ "$REMOVE_DOCKER" -eq 1 ]; then
    if command -v docker >/dev/null 2>&1; then
        _remove_docker_images
    else
        warn "--docker specified but docker command not found"
    fi
fi

# ── 4. Optional: Local artifacts ─────────────────────────────────────
if [ "$CLEAN_ARTIFACTS" -eq 1 ]; then
    _clean_artifacts
fi

# ── Done ─────────────────────────────────────────────────────────────
echo ""
_header "Uninstall Complete"
echo "  ► Reload Window:      Ctrl+Shift+P → Developer: Reload Window"
echo ""
if [ "$REMOVE_DOCKER" -eq 0 ]; then
    echo "  Docker images kept.  To remove:  --docker"
fi
echo ""
