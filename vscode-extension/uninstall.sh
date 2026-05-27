#!/usr/bin/env bash
# vscode-extension/uninstall.sh — Remove Twig extension from VS Code
# ============================================================================
set -euo pipefail

EXT_NAME="twig-static-analyzer"
EXT_ID="twig-analyzer.twig-static-analyzer"

# ── Find VS Code extension dirs ──────────────────────────────────────
find_dirs() {
    for d in \
        "${HOME}/.vscode-server/extensions/${EXT_NAME}" \
        "${HOME}/.vscode/extensions/${EXT_NAME}" \
        "${HOME}/.vscode-insiders/extensions/${EXT_NAME}" \
        "${HOME}/.vscode-server-insiders/extensions/${EXT_NAME}"; do
        [ -d "$d" ] && echo "$d" || true
    done
}

# ── Remove from extensions.json ──────────────────────────────────────
cleanup_extensions_json() {
    for ext_root in \
        "${HOME}/.vscode-server/extensions" \
        "${HOME}/.vscode/extensions" \
        "${HOME}/.vscode-insiders/extensions" \
        "${HOME}/.vscode-server-insiders/extensions"; do
        local ext_json="${ext_root}/extensions.json"
        [ -f "$ext_json" ] || continue
        python3 -c "
import json, sys
try:
    data = json.load(open('${ext_json}'))
    before = len(data)
    data = [e for e in data if e.get('identifier',{}).get('id') != '${EXT_ID}']
    if len(data) < before:
        json.dump(data, open('${ext_json}', 'w'), indent=2)
        print(f'  ✓ Cleaned ${ext_json}')
except: pass
" 2>/dev/null || true
    done
}

# ── Main ─────────────────────────────────────────────────────────────
DIRS=$(find_dirs)

if [ -z "$DIRS" ]; then
    echo "Extension not found. Nothing to uninstall."
else
    echo "Removing Twig Static Analyzer..."
    for d in $DIRS; do
        rm -rf "$d" && echo "  ✓ $d"
    done
fi

echo "Cleaning extension registry..."
cleanup_extensions_json

echo ""
echo "Uninstalled. Reload VS Code to complete."
echo ""
echo "Optional: docker rmi twig-analyzer-lsp twig-analyzer-compile"
