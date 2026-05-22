#!/usr/bin/env bash
# shellcheck disable=SC2059
# ──────────────────────────────────────────────────────────────────────
# Twig Static Analyzer – VS Code Extension Uninstaller
# Compatible with: macOS, Linux, Windows (Git Bash), WSL
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── OS Detection ─────────────────────────────────────────────────────
detect_os() {
    case "$(uname -s)" in
        Darwin)  echo "macos" ;;
        Linux)
            grep -qi microsoft /proc/version 2>/dev/null && echo "wsl" || echo "linux" ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
        *)       echo "unknown" ;;
    esac
}

OS=$(detect_os)
IS_WINDOWS=false; IS_WSL=false
case "$OS" in windows) IS_WINDOWS=true ;; wsl) IS_WSL=true ;; esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXT_NAME="twig-static-analyzer"
EXT_ID="twig-analyzer.twig-static-analyzer"

# ── Color helpers ────────────────────────────────────────────────────
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

# ── Find all extension installation directories ──────────────────────
find_ext_dirs() {
    local found=()

    # VS Code Server
    [ -d "${HOME}/.vscode-server/extensions/${EXT_NAME}" ]        && found+=("${HOME}/.vscode-server/extensions/${EXT_NAME}")

    # VS Code Desktop
    [ -d "${HOME}/.vscode/extensions/${EXT_NAME}" ]               && found+=("${HOME}/.vscode/extensions/${EXT_NAME}")

    # VS Code Insiders
    [ -d "${HOME}/.vscode-insiders/extensions/${EXT_NAME}" ]      && found+=("${HOME}/.vscode-insiders/extensions/${EXT_NAME}")
    [ -d "${HOME}/.vscode-server-insiders/extensions/${EXT_NAME}" ] && found+=("${HOME}/.vscode-server-insiders/extensions/${EXT_NAME}")

    # VS Codium
    [ -d "${HOME}/.vscode-oss/extensions/${EXT_NAME}" ]           && found+=("${HOME}/.vscode-oss/extensions/${EXT_NAME}")

    # macOS
    if [ "$OS" = "macos" ]; then
        [ -d "${HOME}/Library/Application Support/Code/${EXT_NAME}" ]          && found+=("${HOME}/Library/Application Support/Code/${EXT_NAME}")
        [ -d "${HOME}/Library/Application Support/Code - Insiders/${EXT_NAME}" ] && found+=("${HOME}/Library/Application Support/Code - Insiders/${EXT_NAME}")
    fi

    # Windows
    if [ "$IS_WINDOWS" = true ] || [ "$IS_WSL" = true ]; then
        local win_home="${USERPROFILE:-}"
        [ -n "$win_home" ] && [ -d "${win_home}/.vscode/extensions/${EXT_NAME}" ] && found+=("${win_home}/.vscode/extensions/${EXT_NAME}")
    fi

    # Custom override
    [ -n "${VSCODE_EXTENSIONS_DIR:-}" ] && [ -d "${VSCODE_EXTENSIONS_DIR}/${EXT_NAME}" ] && found+=("${VSCODE_EXTENSIONS_DIR}/${EXT_NAME}")

    # Also check project-local venv (optional removal)
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
    [ -d "${PROJECT_ROOT}/.venv" ] && found+=("${PROJECT_ROOT}/.venv")

    printf '%s\n' "${found[@]}"
}

# ── Remove from extensions.json ──────────────────────────────────────
unregister_extension() {
    local ext_json="$1"
    [ -f "$ext_json" ] || return 0

    local py
    py=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo "")
    [ -z "$py" ] && return 0

    "$py" -c "
import json
ext_json = '${ext_json}'
ext_id = '${EXT_ID}'
try:
    with open(ext_json) as f: data = json.load(f)
except: data = []
before = len(data)
data = [e for e in data if e.get('identifier',{}).get('id') != ext_id]
if len(data) < before:
    with open(ext_json, 'w') as f: json.dump(data, f, indent=2)
    print('  Removed from extensions.json')
" 2>/dev/null
}

# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

echo ""
info "╔══════════════════════════════════════════════╗"
info "║  Twig Static Analyzer – VS Code Uninstaller  ║"
info "╚══════════════════════════════════════════════╝"
echo ""
info "  OS: ${OS}"
echo ""

# Find extension dirs
mapfile -t EXT_DIRS < <(find_ext_dirs)

if [ ${#EXT_DIRS[@]} -eq 0 ]; then
    info "  No ${EXT_NAME} installations found."
    echo ""
    exit 0
fi

info "  Found ${#EXT_DIRS[@]} installation(s):"
for d in "${EXT_DIRS[@]}"; do
    echo "    ${YELLOW}→${NC} $d"
done
echo ""

# Confirm
read -r -p "  Remove all listed directories? [y/N] " answer
echo ""
case "${answer:-n}" in
    [yY]|[yY][eE][sS]) ;;
    *) info "  Cancelled."; echo ""; exit 0 ;;
esac

# Remove
REMOVED=0
for d in "${EXT_DIRS[@]}"; do
    if [ -d "$d" ]; then
        rm -rf "$d"
        ok "Removed: $d"
        REMOVED=$((REMOVED + 1))
    fi
done

# Clean up extensions.json registrations
for base in \
    "${HOME}/.vscode-server/extensions" \
    "${HOME}/.vscode/extensions" \
    "${HOME}/.vscode-insiders/extensions" \
    "${HOME}/.vscode-server-insiders/extensions" \
    "${HOME}/.vscode-oss/extensions"; do
    unregister_extension "${base}/extensions.json" 2>/dev/null || true
done

echo ""
ok "Removed ${REMOVED} installation(s)"
echo ""
info "  ► Restart VS Code for changes to take effect"
info "  ► To reinstall: bash ${SCRIPT_DIR}/install.sh"
echo ""

exit 0
