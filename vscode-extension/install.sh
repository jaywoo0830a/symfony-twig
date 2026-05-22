#!/usr/bin/env bash
# shellcheck disable=SC2059,SC2086
# ──────────────────────────────────────────────────────────────────────
# Twig Static Analyzer – VS Code Extension Installer
# Compatible with: macOS, Linux, Windows (Git Bash), WSL
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── OS Detection ─────────────────────────────────────────────────────
detect_os() {
    case "$(uname -s)" in
        Darwin)  echo "macos" ;;
        Linux)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                echo "wsl"
            else
                echo "linux"
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
        *)       echo "unknown" ;;
    esac
}

OS=$(detect_os)
IS_WINDOWS=false; IS_WSL=false
case "$OS" in windows) IS_WINDOWS=true ;; wsl) IS_WSL=true ;; esac

# ── Paths ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
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
step() { printf "\n${YELLOW}[%s]${NC} ${BOLD}%s${NC}\n" "$1" "$2"; }

# ── Find VS Code extensions directory ────────────────────────────────
find_vscode_ext_dir() {
    local dirs=()
    [ -d "${HOME}/.vscode-server/extensions" ]        && dirs+=("${HOME}/.vscode-server/extensions")
    [ -d "${HOME}/.vscode/extensions" ]                && dirs+=("${HOME}/.vscode/extensions")
    [ -d "${HOME}/.vscode-insiders/extensions" ]       && dirs+=("${HOME}/.vscode-insiders/extensions")
    [ -d "${HOME}/.vscode-server-insiders/extensions" ]&& dirs+=("${HOME}/.vscode-server-insiders/extensions")
    [ -d "${HOME}/.vscode-oss/extensions" ]            && dirs+=("${HOME}/.vscode-oss/extensions")

    # macOS Application Support paths
    if [ "$OS" = "macos" ]; then
        [ -d "${HOME}/Library/Application Support/Code" ] && dirs+=("${HOME}/Library/Application Support/Code")
        [ -d "${HOME}/Library/Application Support/Code - Insiders" ] && dirs+=("${HOME}/Library/Application Support/Code - Insiders")
    fi

    # Windows via Git Bash / WSL
    if [ "$IS_WINDOWS" = true ] || [ "$IS_WSL" = true ]; then
        local win_home="${USERPROFILE:-}"
        [ -n "$win_home" ] && [ -d "${win_home}/.vscode/extensions" ] && dirs+=("${win_home}/.vscode/extensions")
    fi

    # Custom override
    [ -n "${VSCODE_EXTENSIONS_DIR:-}" ] && dirs=("${VSCODE_EXTENSIONS_DIR}" "${dirs[@]}")

    for d in "${dirs[@]}"; do [ -d "$d" ] && echo "$d" && return; done

    local fallback="${HOME}/.vscode/extensions"
    mkdir -p "$fallback"
    echo "$fallback"
}

VSCODE_EXT_DIR=$(find_vscode_ext_dir)
EXT_DIR="${VSCODE_EXT_DIR}/${EXT_NAME}"

# ── Find Python 3 ────────────────────────────────────────────────────
find_python() {
    [ -f "${PROJECT_ROOT}/.venv/bin/python3" ] && { echo "${PROJECT_ROOT}/.venv/bin/python3"; return; }
    [ -f "${PROJECT_ROOT}/.venv/bin/python" ]  && { echo "${PROJECT_ROOT}/.venv/bin/python"; return; }
    command -v python3 >/dev/null 2>&1 && { command -v python3; return; }
    command -v python  >/dev/null 2>&1 && { command -v python; return; }

    # Windows common paths
    for p in "/c/Program Files/Python312/python.exe" "/c/Program Files/Python311/python.exe" \
             "/c/Python312/python.exe" "/mnt/c/Program Files/Python312/python.exe"; do
        [ -f "$p" ] && { echo "$p"; return; }
    done
    echo ""
}

has_node() { command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; }

# ── Install Python package ───────────────────────────────────────────
install_python_package() {
    local python="$1"
    if "$python" -c "import twig_analyzer" 2>/dev/null; then
        ok "twig-analyzer already installed"
        return 0
    fi
    if "$python" -m pip install -e "${PROJECT_ROOT}" --quiet 2>/dev/null; then
        ok "twig-analyzer installed via pip"
        return 0
    fi
    warn "pip install failed – creating virtualenv..."
    "$python" -m venv "${PROJECT_ROOT}/.venv" 2>/dev/null || {
        err "Failed to create virtualenv. Install python3-venv or virtualenv."
        return 1
    }
    local venv_py="${PROJECT_ROOT}/.venv/bin/python3"
    [ -f "$venv_py" ] || venv_py="${PROJECT_ROOT}/.venv/bin/python"
    "$venv_py" -m pip install -e "${PROJECT_ROOT}" --quiet 2>/dev/null || {
        err "pip install into venv failed"
        return 1
    }
    ok "twig-analyzer installed in venv"
}

# ── Build VS Code extension ──────────────────────────────────────────
build_extension() {
    cd "$SCRIPT_DIR"
    [ -f "package.json" ] || { err "package.json not found"; return 1; }
    if ! has_node; then
        if [ -f "${SCRIPT_DIR}/out/extension.js" ]; then
            warn "Node.js not found – using pre-built extension"
            return 0
        fi
        err "No Node.js and no pre-built extension. Install Node.js."
        return 1
    fi
    npm install --silent 2>/dev/null || true
    ok "npm dependencies ready"
    npx tsc -p ./ 2>/dev/null || { err "TypeScript compilation failed"; return 1; }
    ok "TypeScript compiled"
    [ -f "${SCRIPT_DIR}/out/extension.js" ] || { err "out/extension.js not found"; return 1; }
    return 0
}

# ── Install extension files ──────────────────────────────────────────
install_extension_files() {
    mkdir -p "$EXT_DIR"
    cp "${SCRIPT_DIR}/package.json"                     "$EXT_DIR/" 2>/dev/null || true
    cp -r "${SCRIPT_DIR}/out"                           "$EXT_DIR/" 2>/dev/null || true
    cp "${SCRIPT_DIR}/README.md"                        "$EXT_DIR/" 2>/dev/null || true
    cp "${SCRIPT_DIR}/twig.tmLanguage.json"             "$EXT_DIR/" 2>/dev/null || true
    cp "${SCRIPT_DIR}/twig-language-configuration.json" "$EXT_DIR/" 2>/dev/null || true
    mkdir -p "${EXT_DIR}/twig_analyzer"
    cp -r "${PROJECT_ROOT}/twig_analyzer/"*             "${EXT_DIR}/twig_analyzer/" 2>/dev/null || true
    cp "${PROJECT_ROOT}/pyproject.toml"                 "${EXT_DIR}/" 2>/dev/null || true
    ok "Extension files copied to ${EXT_DIR}"
}

# ── Register in extensions.json ──────────────────────────────────────
register_extension() {
    local ext_json="${VSCODE_EXT_DIR}/extensions.json"
    [ -f "$ext_json" ] || { warn "extensions.json not found – VS Code will discover automatically"; return 0; }
    local py; py=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || echo "")
    [ -z "$py" ] && { warn "Python not available – skipping registration"; return 0; }
    "$py" -c "
import json, os, time
ext_json = '${ext_json}'
ext_id = '${EXT_ID}'
ext_dir = '${EXT_DIR}'
try:
    with open(ext_json) as f: data = json.load(f)
except: data = []
data = [e for e in data if e.get('identifier',{}).get('id') != ext_id]
data.append({
    'identifier': {'id': ext_id},
    'version': '1.0.0',
    'location': {'\$mid': 1, 'path': ext_dir, 'scheme': 'file'},
    'relativeLocation': os.path.basename(ext_dir),
    'metadata': {'installedTimestamp': int(time.time()*1000), 'pinned': True, 'source': 'vsix'}
})
with open(ext_json, 'w') as f: json.dump(data, f, indent=2)
" 2>/dev/null && ok "Registered in extensions.json" || true
}

# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════
echo ""
info "╔══════════════════════════════════════════════╗"
info "║   Twig Static Analyzer – VS Code Installer   ║"
info "╚══════════════════════════════════════════════╝"
echo ""
info "  OS:       ${OS}"
info "  VS Code:  ${VSCODE_EXT_DIR}"
info "  Install:  ${EXT_DIR}"
echo ""

step "1/4" "Checking prerequisites..."
PYTHON=$(find_python)
[ -z "$PYTHON" ] && { err "Python 3 not found. Install Python 3.9+ from https://python.org"; exit 1; }
ok "Python: $PYTHON ($($PYTHON --version 2>&1))"
if has_node; then
    ok "Node.js: $(node --version)"; ok "npm:     $(npm --version)"
else
    warn "Node.js not found – will use pre-built extension"
fi

step "2/4" "Installing Python twig-analyzer..."
install_python_package "$PYTHON"
if "$PYTHON" -m twig_analyzer --help >/dev/null 2>&1; then
    ok "CLI: python -m twig_analyzer"
elif [ -f "${PROJECT_ROOT}/.venv/bin/python" ]; then
    PYTHON="${PROJECT_ROOT}/.venv/bin/python"
    ok "CLI: venv python -m twig_analyzer"
else
    warn "CLI verification skipped"
fi

step "3/4" "Building VS Code extension..."
build_extension || exit 1

step "4/4" "Installing extension into VS Code..."
install_extension_files
register_extension

echo ""
info "╔══════════════════════════════════════════════╗"
info "║           Installation Complete!              ║"
info "╚══════════════════════════════════════════════╝"
echo ""
echo "  ► Restart VS Code: Ctrl+Shift+P → Developer: Reload Window"
echo "  ► Open any .twig or .html.twig file"
echo ""
echo "  Settings:  Ctrl+,  → search 'twigAnalyzer'"
echo "  Command:   Ctrl+Shift+P → 'Twig: Analyze Current File'"
echo "  Uninstall: bash ${SCRIPT_DIR}/uninstall.sh"
echo ""
exit 0
