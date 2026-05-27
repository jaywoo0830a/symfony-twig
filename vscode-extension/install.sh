#!/usr/bin/env bash
# vscode-extension/install.sh — Install Twig extension into VS Code
# ============================================================================
# Prerequisite: Docker (nothing else — no Node.js, no Python, no npm)
#
# Usage:
#   bash vscode-extension/install.sh            # install (safe re-run)
#   bash vscode-extension/install.sh --force    # overwrite without prompt
#   bash vscode-extension/install.sh --help     # show help
#
# Idempotent: safe to run multiple times.  Existing installation is
# detected and skipped unless --force is given.
# ============================================================================
set -euo pipefail

# ── Globals ──────────────────────────────────────────────────────────
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
readonly EXT_NAME="twig-static-analyzer"
readonly EXT_ID="twig-analyzer.${EXT_NAME}"
readonly RUNTIME_IMAGE="twig-analyzer-lsp:latest"
readonly COMPILE_IMAGE="twig-analyzer-compile:latest"
readonly BACKUP_DIR="${SCRIPT_DIR}/.backups"

FORCE=0
DID_BUILD_RUNTIME=0
CID=""  # container ID tracker for cleanup trap

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

# ── Cleanup trap: always remove dangling containers ──────────────────
cleanup() {
    if [ -n "${CID:-}" ]; then
        docker rm "$CID" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

# ── Help ─────────────────────────────────────────────────────────────
usage() {
    cat <<'EOF'
Usage:  bash vscode-extension/install.sh [OPTIONS]

Installs the Twig Static Analyzer VS Code extension.
Requirements: Docker only (no Node.js, Python, or npm needed).

Options:
  --force     Overwrite existing installation without prompting
  --help      Show this help

After install, reload VS Code: Ctrl+Shift+P → Developer: Reload Window
EOF
    exit 0
}

# ── Parse flags ──────────────────────────────────────────────────────
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        --help)  usage ;;
        *)       warn "Unknown flag: $arg"; usage ;;
    esac
done

# ── VS Code discovery ────────────────────────────────────────────────
_find_vscode_ext_dir() {
    for d in \
        "${HOME}/.vscode-server/extensions" \
        "${HOME}/.vscode/extensions" \
        "${HOME}/.vscode-insiders/extensions" \
        "${HOME}/.vscode-server-insiders/extensions"; do
        [ -d "$d" ] && { printf '%s' "$d"; return 0; }
    done
    local fb="${HOME}/.vscode/extensions"
    mkdir -p "$fb"
    printf '%s' "$fb"
}

readonly VSCODE_EXT_DIR="$(_find_vscode_ext_dir)"
readonly EXT_DIR="${VSCODE_EXT_DIR}/${EXT_NAME}"
readonly EXT_JSON="${VSCODE_EXT_DIR}/extensions.json"

# ── Pre-flight checks ────────────────────────────────────────────────
_require_docker_daemon() {
    command -v docker >/dev/null 2>&1 || {
        err "Docker not found.  Install from https://docker.com"
        return 1
    }
    docker info >/dev/null 2>&1 || {
        err "Docker daemon is not running.  Start Docker Desktop first."
        return 1
    }
    return 0
}

_require_source_files() {
    local missing=0
    for f in \
        "${SCRIPT_DIR}/package.json" \
        "${SCRIPT_DIR}/twig.tmLanguage.json" \
        "${SCRIPT_DIR}/twig-language-configuration.json" \
        "${SCRIPT_DIR}/src/extension.ts" \
        "${SCRIPT_DIR}/src/providers.ts"; do
        if [ ! -f "$f" ]; then
            err "Missing required file: $f"
            missing=1
        fi
    done
    return "$missing"
}

_require_python_or_node() {
    # We only need one of python3 / node to manipulate extensions.json.
    # If neither is available we can still install files but can't register.
    command -v python3 >/dev/null 2>&1 && return 0
    command -v node    >/dev/null 2>&1 && return 0
    warn "Neither python3 nor node found — extension will NOT be registered in extensions.json"
    warn "Twig files may still show as Plain Text.  Install python3 or node and re-run."
    return 1
}

# ── Idempotency guard ────────────────────────────────────────────────
_check_existing() {
    if [ -d "$EXT_DIR" ] && [ "$FORCE" -eq 0 ]; then
        warn "Already installed at ${EXT_DIR}"
        info "Use --force to overwrite, or run uninstall.sh first."
        return 1
    fi
    return 0
}

# ── Docker helpers ───────────────────────────────────────────────────
_build_runtime() {
    if docker image inspect "$RUNTIME_IMAGE" >/dev/null 2>&1; then
        ok "Runtime image: $RUNTIME_IMAGE"
        DID_BUILD_RUNTIME=0
        return 0
    fi
    info "Building runtime image (one-time, ~60s)..."
    cd "$PROJECT_ROOT"
    local log
    log=$(mktemp)
    if docker build --target runtime -t "$RUNTIME_IMAGE" . >"$log" 2>&1; then
        rm -f "$log"
        DID_BUILD_RUNTIME=1
        ok "Runtime image built"
    else
        warn "Docker build log:"
        tail -20 "$log" >&2
        rm -f "$log"
        err "Docker build (runtime) failed.  Check Docker logs."
        return 1
    fi
}

_compile_typescript() {
    info "Compiling TypeScript via Docker..."
    cd "$PROJECT_ROOT"
    local log
    log=$(mktemp)
    if docker build --target compile -t "$COMPILE_IMAGE" . >"$log" 2>&1; then
        rm -f "$log"
    else
        warn "Docker build log:"
        tail -20 "$log" >&2
        rm -f "$log"
        err "TypeScript compilation failed"
        return 1
    fi
    ok "TypeScript compiled + JSON generated"

    CID=$(docker create "$COMPILE_IMAGE" 2>/dev/null)
    [ -z "$CID" ] && { err "Failed to create compile container"; return 1; }

    # Clean previous extracted artifacts (both out/ and src/data/ are generated)
    rm -rf "${SCRIPT_DIR}/out" "${SCRIPT_DIR}/src/data" 2>/dev/null || true

    docker cp "$CID:/build/out" "${SCRIPT_DIR}/out" >/dev/null 2>&1 || {
        err "Failed to extract out/ from container"
        return 1
    }
    mkdir -p "${SCRIPT_DIR}/src/data"
    docker cp "$CID:/build/src/data/." "${SCRIPT_DIR}/src/data/" >/dev/null 2>&1 || {
        err "Failed to extract src/data/ from container"
        return 1
    }

    docker rm "$CID" >/dev/null 2>&1
    CID=""
    ok "Output extracted (out/ + src/data/)"
}

# ── File installation ────────────────────────────────────────────────
_install_files() {
    # Remove previous installation if present
    if [ -d "$EXT_DIR" ]; then
        info "Removing previous installation..."
        rm -rf "$EXT_DIR"
    fi

    mkdir -p "${EXT_DIR}/src/data"

    local failed=0
    cp "${SCRIPT_DIR}/package.json"                     "${EXT_DIR}/" || failed=1
    cp -r "${SCRIPT_DIR}/out"                           "${EXT_DIR}/" || failed=1
    cp -r "${SCRIPT_DIR}/src/data/."                    "${EXT_DIR}/src/data/" 2>/dev/null || true
    cp "${SCRIPT_DIR}/twig.tmLanguage.json"             "${EXT_DIR}/" || failed=1
    cp "${SCRIPT_DIR}/twig-language-configuration.json" "${EXT_DIR}/" || failed=1

    if [ "$failed" -eq 1 ]; then
        err "File copy failed — check disk space and permissions"
        return 1
    fi
    ok "Extension files → ${EXT_DIR}"
}

_verify_installation() {
    local failed=0
    for f in package.json twig.tmLanguage.json twig-language-configuration.json out/extension.js; do
        if [ ! -f "${EXT_DIR}/${f}" ]; then
            err "Missing after install: ${EXT_DIR}/${f}"
            failed=1
        fi
    done
    return $failed
}

# ── Registration in extensions.json ──────────────────────────────────
_register_extension() {
    local now
    now=$(date +%s)000  # JS-style milliseconds timestamp

    # Deterministic UUID derived from extension name
    local fake_uuid
    fake_uuid=$(echo -n "$EXT_NAME" | md5sum | awk \
        '{printf "%s-%s-%s-%s-%s", substr($1,1,8), substr($1,9,4), substr($1,13,4), substr($1,17,4), substr($1,21,12)}')

    # Backup extensions.json before modifying
    if [ -f "$EXT_JSON" ]; then
        mkdir -p "$BACKUP_DIR"
        cp "$EXT_JSON" "${BACKUP_DIR}/extensions.json.bak.$(date +%Y%m%d_%H%M%S)" || true
    fi

    if command -v python3 >/dev/null 2>&1; then
        python3 -c "
import json, os, sys

ext_json = '${EXT_JSON}'
entry = {
    'identifier':  {'id': '${EXT_ID}', 'uuid': '${fake_uuid}'},
    'version':     '1.0.0',
    'location':    {'\$mid': 1, 'path': '${EXT_DIR}', 'scheme': 'file'},
    'relativeLocation': '${EXT_NAME}',
    'metadata': {
        'installedTimestamp': ${now:-0},
        'source':              'vsix',
        'id':                  '${fake_uuid}',
        'publisherId':         'twig-analyzer',
        'publisherDisplayName':'Twig Analyzer',
        'targetPlatform':      'undefined',
        'updated':             False,
        'private':             True,
        'isPreReleaseVersion': False,
        'hasPreReleaseVersion':False,
    },
}

data = []
if os.path.exists(ext_json):
    try:
        data = json.load(open(ext_json))
    except Exception:
        data = []

# Deduplicate: remove any old entry with same id, then append
data = [e for e in data if e.get('identifier',{}).get('id') != '${EXT_ID}']
data.append(entry)
json.dump(data, open(ext_json, 'w'), indent=2)
" 2>&1 || {
            warn "Failed to register in extensions.json (python3 error)"
            return 1
        }
    elif command -v node >/dev/null 2>&1; then
        node -e "
const fs = require('fs');
const entry = {
    identifier:  {id: '${EXT_ID}', uuid: '${fake_uuid}'},
    version:     '1.0.0',
    location:    {'\$mid': 1, path: '${EXT_DIR}', scheme: 'file'},
    relativeLocation: '${EXT_NAME}',
    metadata: {
        installedTimestamp: ${now:-0},
        source: 'vsix',
        id: '${fake_uuid}',
        publisherId: 'twig-analyzer',
        publisherDisplayName: 'Twig Analyzer',
        targetPlatform: 'undefined',
        updated: false,
        private: true,
        isPreReleaseVersion: false,
        hasPreReleaseVersion: false,
    },
};
let data = [];
try { data = JSON.parse(fs.readFileSync('${EXT_JSON}','utf8')); } catch(_){}
data = data.filter(e => (e.identifier||{}).id !== '${EXT_ID}');
data.push(entry);
fs.writeFileSync('${EXT_JSON}', JSON.stringify(data, null, 2));
" 2>/dev/null || {
            warn "Failed to register in extensions.json (node error)"
            return 1
        }
    else
        warn "Skipping extensions.json — install python3 or node then re-run"
        return 1
    fi
    ok "Registered in extensions.json"
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

_header "Twig Static Analyzer – VS Code Installer"
info "  VS Code extensions dir: ${VSCODE_EXT_DIR}"
info "  Install target:         ${EXT_DIR}"

# ── Step 1: Prerequisites ────────────────────────────────────────────
step "1/3" "Checking prerequisites"

_require_docker_daemon || exit 1
ok "Docker: $(docker --version 2>&1 | head -1)"

_require_source_files || exit 1
ok "Source files present"

_check_existing || exit 1

# ── Step 2: Build ────────────────────────────────────────────────────
step "2/3" "Building (Docker multi-stage)"

_build_runtime  || exit 1
_compile_typescript || exit 1

# ── Step 3: Install ──────────────────────────────────────────────────
step "3/3" "Installing extension"

_install_files     || exit 1
_verify_installation || exit 1
_register_extension || true  # non-fatal: files are in place

# ── Done ─────────────────────────────────────────────────────────────
_header "Installation Complete"
echo "  ► Reload Window:  Ctrl+Shift+P → Developer: Reload Window"
echo "  ► Open any .twig or .html.twig file"
echo ""
echo "  Requirements: Docker Desktop must be running"
echo "  Uninstall:    bash vscode-extension/uninstall.sh"
echo ""
