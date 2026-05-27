#!/usr/bin/env bash
# vscode-extension/uninstall.sh — Remove Twig extension from VS Code
# ============================================================================
set -euo pipefail

EXT_NAME="twig-static-analyzer"

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

# ── Main ─────────────────────────────────────────────────────────────
DIRS=$(find_dirs)

if [ -z "$DIRS" ]; then
    echo "Extension not found. Nothing to uninstall."
    exit 0
fi

echo "Removing Twig Static Analyzer..."
for d in $DIRS; do
    rm -rf "$d" && echo "  ✓ $d"
done

echo ""
echo "Uninstalled. Reload VS Code to complete."
echo ""
echo "Optional: docker rmi twig-analyzer-lsp twig-analyzer-compile"
