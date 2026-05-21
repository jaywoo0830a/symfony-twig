#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────
# Twig Static Analyzer – VS Code Extension Installer
# ──────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
EXT_NAME="twig-static-analyzer"
EXT_DIR="${HOME}/.vscode/extensions/${EXT_NAME}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   Twig Static Analyzer – VS Code Installer   ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ── Step 1: Check prerequisites ──────────────────
echo -e "${YELLOW}[1/4] Checking prerequisites...${NC}"

# Python 3
if command -v python3 &>/dev/null; then
    PYTHON=$(command -v python3)
    echo -e "  ${GREEN}✓${NC} Python 3: ${PYTHON}"
elif command -v python &>/dev/null; then
    PYTHON=$(command -v python)
    echo -e "  ${GREEN}✓${NC} Python: ${PYTHON}"
else
    echo -e "  ${RED}✗${NC} Python 3 not found. Please install Python 3.9+."
    exit 1
fi

# Node.js (for compiling the extension)
if command -v node &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Node.js: $(node --version)"
else
    echo -e "  ${YELLOW}!${NC} Node.js not found – skipping extension compilation."
    echo "    Install Node.js if you want to rebuild the extension."
    NO_NODE=true
fi

# npm
if command -v npm &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} npm: $(npm --version)"
else
    NO_NODE=true
fi

echo ""

# ── Step 2: Install Python analyzer ──────────────
echo -e "${YELLOW}[2/4] Installing Python twig-analyzer...${NC}"

cd "${PROJECT_ROOT}"

PIP_INSTALLED=false

# Strategy 1: Use existing .venv
if [ -f "${PROJECT_ROOT}/.venv/bin/python" ]; then
    echo -e "  Using existing virtualenv: .venv"
    VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
    if ${VENV_PYTHON} -m pip install -e . --quiet 2>&1; then
        echo -e "  ${GREEN}✓${NC} twig-analyzer installed (venv)"
        PIP_INSTALLED=true
    fi
fi

# Strategy 2: Try system pip
if [ "${PIP_INSTALLED}" = false ]; then
    if ${PYTHON} -m pip install -e . --quiet 2>&1; then
        echo -e "  ${GREEN}✓${NC} twig-analyzer installed (system)"
        PIP_INSTALLED=true
    fi
fi

# Strategy 3: Create venv + install
if [ "${PIP_INSTALLED}" = false ]; then
    echo -e "  ${YELLOW}!${NC} System pip is restricted – creating .venv..."
    ${PYTHON} -m venv "${PROJECT_ROOT}/.venv" 2>&1
    VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
    ${VENV_PYTHON} -m pip install -e . --quiet 2>&1
    echo -e "  ${GREEN}✓${NC} twig-analyzer installed (new venv)"
    PIP_INSTALLED=true
fi

# Verify installation
if ${PYTHON} -m twig_analyzer --help &>/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} CLI works (python -m twig_analyzer)"
elif [ -n "${VENV_PYTHON:-}" ] && ${VENV_PYTHON} -m twig_analyzer --help &>/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} CLI works (venv python -m twig_analyzer)"
elif command -v twig-analyze &>/dev/null; then
    echo -e "  ${GREEN}✓${NC} CLI works (twig-analyze on PATH)"
else
    echo -e "  ${YELLOW}!${NC} CLI not on PATH – you can run:"
    echo "    python3 -m twig_analyzer <args>"
fi

echo ""

# ── Step 3: Build the extension ──────────────────
echo -e "${YELLOW}[3/4] Building VS Code extension...${NC}"

cd "${SCRIPT_DIR}"

if [ "${NO_NODE:-false}" = true ]; then
    echo -e "  ${YELLOW}!${NC} Skipping (Node.js not available)"
    echo "    Using pre-built extension if out/extension.js exists."
else
    npm install --silent 2>&1 | tail -1
    echo -e "  ${GREEN}✓${NC} npm dependencies installed"

    npx tsc -p ./ 2>&1
    echo -e "  ${GREEN}✓${NC} TypeScript compiled"
fi

if [ ! -f "${SCRIPT_DIR}/out/extension.js" ]; then
    echo -e "  ${RED}✗${NC} out/extension.js not found. Build failed?"
    exit 1
fi

echo ""

# ── Step 4: Install into VS Code ─────────────────
echo -e "${YELLOW}[4/4] Installing extension into VS Code...${NC}"

mkdir -p "${EXT_DIR}"

# Copy all necessary files
cp -r "${SCRIPT_DIR}/package.json"   "${EXT_DIR}/"
cp -r "${SCRIPT_DIR}/out"            "${EXT_DIR}/"
cp -r "${SCRIPT_DIR}/README.md"      "${EXT_DIR}/" 2>/dev/null || true

# Also copy the Python analyzer into the extension dir so it's self-contained
mkdir -p "${EXT_DIR}/twig_analyzer"
cp -r "${PROJECT_ROOT}/twig_analyzer/"* "${EXT_DIR}/twig_analyzer/"
cp "${PROJECT_ROOT}/pyproject.toml"    "${EXT_DIR}/" 2>/dev/null || true

echo -e "  ${GREEN}✓${NC} Extension installed to: ${EXT_DIR}"

echo ""

# ── Summary ──────────────────────────────────────
echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              Installation Complete!           ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${GREEN}►${NC} Restart VS Code (or run 'Developer: Reload Window')"
echo -e "  ${GREEN}►${NC} Open any .twig file to see diagnostics"
echo ""
echo -e "  Settings: ${CYAN}Ctrl+,${NC} → search 'twigAnalyzer'"
echo -e "  Command:  ${CYAN}Ctrl+Shift+P${NC} → 'Twig: Analyze Current File'"
echo ""
echo -e "  To uninstall:"
echo -e "    ${RED}rm -rf ${EXT_DIR}${NC}"
echo ""
