"""LSP Server for Twig templates — functional, immutable, pure-core design.

Implements JSON-RPC 2.0 over stdin/stdout per the Language Server Protocol 3.17.

Design principles (per https://docs.python.org/3.14/howto/functional.html):
  1. Immutable state  — frozen dataclasses, replace(), tuple over list
  2. Pure functions   — computation separated from IO side effects
  3. Pattern matching — match/case for message dispatch (Python 3.10+)
  4. Composition      — pipe data through pure transforms, then execute
  5. Lazy evaluation   — generators, itertools where appropriate

Usage:
    python -m twig_analyzer.lsp_server
    twig-lsp
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from .analyzer import Analyzer
from .builtins import BUILTIN_TAGS, BUILTIN_FILTERS, BUILTIN_FUNCTIONS, BUILTIN_TESTS
from .config import TwigAnalyzerConfig
from .formatter import format_twig

# ═══════════════════════════════════════════════════════════════════════
# 1. Pure types — frozen, algebraic
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ServerState:
    """Immutable snapshot. Every handler returns a new ServerState via replace()."""
    root_path: str = ""
    config: Optional[TwigAnalyzerConfig] = None
    documents: Tuple[Tuple[str, str], ...] = ()  # ((uri, source), ...)
    analyzer: Any = None

    @staticmethod
    def create(root_path: str = "", config: Optional[TwigAnalyzerConfig] = None) -> ServerState:
        cfg = config or (TwigAnalyzerConfig.discover(root_path) if root_path else TwigAnalyzerConfig.empty())
        return ServerState(root_path=root_path, config=cfg, analyzer=Analyzer(config=cfg))

    def with_document(self, uri: str, text: str) -> ServerState:
        docs = tuple((u, t) for u, t in self.documents if u != uri) + ((uri, text),)
        return replace(self, documents=docs)

    def without_document(self, uri: str) -> ServerState:
        docs = tuple((u, t) for u, t in self.documents if u != uri)
        return replace(self, documents=docs)

    def find_document(self, uri: str) -> Optional[str]:
        for u, t in self.documents:
            if u == uri:
                return t
        return None


# ═══════════════════════════════════════════════════════════════════════
# 2. Pure functions — zero side effects
# ═══════════════════════════════════════════════════════════════════════

def extract_word(source: str, line: int, char: int) -> Optional[str]:
    """Pure: extract the word at a position in source text."""
    lines = source.split("\n")
    if line >= len(lines):
        return None
    lt = lines[line]
    start = char
    while start > 0 and (lt[start - 1].isalnum() or lt[start - 1] in "_."):
        start -= 1
    end = char
    while end < len(lt) and (lt[end].isalnum() or lt[end] in "_."):
        end += 1
    return lt[start:end] if start < end else None


def classify_context(before_cursor: str) -> str:
    """Pure: 'tag' | 'filter' | 'expression' | 'html'."""
    in_tag = "{%" in before_cursor and "%}" not in before_cursor
    in_expr = "{{" in before_cursor and "}}" not in before_cursor
    after_pipe = "|" in before_cursor and in_expr
    if in_tag:       return "tag"
    if after_pipe:   return "filter"
    if in_expr:      return "expression"
    return "html"


def build_hover(word: str, line: int, char: int) -> Optional[dict]:
    """Pure: build LSP hover response or None."""
    info = (BUILTIN_TAGS.get(word) or BUILTIN_FILTERS.get(word) or
            BUILTIN_FUNCTIONS.get(word) or BUILTIN_TESTS.get(word))
    if not info:
        return None
    desc = info.get("description", "")
    since = info.get("since", "—")
    example = info.get("example", "")
    return {
        "contents": {
            "kind": "markdown",
            "value": f"### `{word}`\n\n{desc}\n\n> Since: {since}\n> Example: `{example}`",
        },
        "range": {
            "start": {"line": line, "character": char - len(word)},
            "end": {"line": line, "character": char},
        },
    }


def build_completions(context: str) -> list[dict]:
    """Pure: generate LSP completion items."""
    if context == "tag":
        return [{"label": t, "kind": 14, "detail": i.get("description", "")} for t, i in BUILTIN_TAGS.items()]
    if context == "filter":
        return [{"label": f, "kind": 2, "detail": f"Twig Filter (since {BUILTIN_FILTERS[f].get('since', '—')})"} for f in BUILTIN_FILTERS]
    if context == "expression":
        funcs = [{"label": f, "kind": 3, "detail": f"Twig Function (since {BUILTIN_FUNCTIONS[f].get('since', '—')})",
                  "insertText": f"{f}($1)", "insertTextFormat": 2} for f in BUILTIN_FUNCTIONS]
        filts = [{"label": f, "kind": 2, "detail": f"Twig Filter (since {BUILTIN_FILTERS[f].get('since', '—')})"} for f in BUILTIN_FILTERS]
        return funcs + filts
    return []


def resolve_template_path(doc_uri: str, source: str, line: int) -> Optional[str]:
    """Pure: resolve {% tag 'path' %} or {{ func('path') }} → file:// URI."""
    lines = source.split("\n")
    if line >= len(lines):
        return None
    m = re.search(r"""['"]([^'"]+)['"]""", lines[line])
    if not m:
        return None
    template_name = m.group(1)
    if doc_uri.startswith("file://"):
        resolved = Path(doc_uri[7:]).parent / template_name
        if resolved.is_file():
            return f"file://{resolved}"
    return None


def build_diagnostics(uri: str, source: str, analyzer: Any) -> list[dict]:
    """Pure: run analysis → LSP diagnostic dicts."""
    if not analyzer or not source:
        return []
    result = analyzer.analyze(source)
    return [{
        "range": {
            "start": {"line": d.range.start_line - 1, "character": d.range.start_column - 1},
            "end": {"line": d.range.end_line - 1, "character": d.range.end_column - 1},
        },
        "severity": int(d.severity),
        "code": d.rule_id,
        "source": "twig-analyzer",
        "message": d.message,
    } for d in result.diagnostics]


# ═══════════════════════════════════════════════════════════════════════
# 3. JSON-RPC message constructors (pure factories)
# ═══════════════════════════════════════════════════════════════════════

def rpc_response(msg_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}

def rpc_error(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}

def rpc_notification(method: str, params: dict = None) -> dict:
    msg = {"jsonrpc": "2.0", "method": method}
    if params: msg["params"] = params
    return msg


# ═══════════════════════════════════════════════════════════════════════
# 4. Handlers — pure (state, params) → (state, [messages])
# ═══════════════════════════════════════════════════════════════════════

def handle_initialize(state: ServerState, params: dict, msg_id: Any) -> Tuple[ServerState, list[dict]]:
    root_uri = params.get("rootUri", "")
    root_path = params.get("rootPath", "")
    if root_uri.startswith("file://"):
        root_path = root_uri[7:]
    ns = ServerState.create(root_path=root_path)
    return ns, [rpc_response(msg_id, {
        "capabilities": {
            "textDocumentSync": {"openClose": True, "change": 1},
            "hoverProvider": True,
            "completionProvider": {"triggerCharacters": [" ", "|", ".", "(", "<"]},
            "definitionProvider": True,
            "documentFormattingProvider": True,
        },
        "serverInfo": {"name": "twig-analyzer", "version": "1.0.0"},
    })]

def handle_initialized(state: ServerState, params: dict) -> Tuple[ServerState, list[dict]]:
    return state, []

def handle_did_open(state: ServerState, params: dict) -> Tuple[ServerState, list[dict]]:
    doc = params.get("textDocument", {})
    uri, text = doc.get("uri", ""), doc.get("text", "")
    ns = state.with_document(uri, text)
    diags = build_diagnostics(uri, text, ns.analyzer)
    return ns, [rpc_notification("textDocument/publishDiagnostics", {"uri": uri, "diagnostics": diags})]

def handle_did_change(state: ServerState, params: dict) -> Tuple[ServerState, list[dict]]:
    doc = params.get("textDocument", {})
    uri = doc.get("uri", "")
    changes = params.get("contentChanges", [])
    if not changes or "text" not in changes[0]:
        return state, []
    text = changes[0]["text"]
    ns = state.with_document(uri, text)
    diags = build_diagnostics(uri, text, ns.analyzer)
    return ns, [rpc_notification("textDocument/publishDiagnostics", {"uri": uri, "diagnostics": diags})]

def handle_did_close(state: ServerState, params: dict) -> Tuple[ServerState, list[dict]]:
    uri = params.get("textDocument", {}).get("uri", "")
    ns = state.without_document(uri)
    return ns, [rpc_notification("textDocument/publishDiagnostics", {"uri": uri, "diagnostics": []})]

def handle_hover(state: ServerState, params: dict, msg_id: Any) -> Tuple[ServerState, list[dict]]:
    uri = params.get("textDocument", {}).get("uri", "")
    pos = params.get("position", {})
    src = state.find_document(uri) or ""
    if not src:
        return state, [rpc_response(msg_id, None)]
    word = extract_word(src, pos.get("line", 0), pos.get("character", 0))
    if not word:
        return state, [rpc_response(msg_id, None)]
    resp = build_hover(word, pos.get("line", 0), pos.get("character", 0))
    return state, [rpc_response(msg_id, resp)]

def handle_completion(state: ServerState, params: dict, msg_id: Any) -> Tuple[ServerState, list[dict]]:
    uri = params.get("textDocument", {}).get("uri", "")
    pos = params.get("position", {})
    src = state.find_document(uri) or ""
    if not src:
        return state, [rpc_response(msg_id, {"isIncomplete": False, "items": []})]
    line, char = pos.get("line", 0), pos.get("character", 0)
    lines = src.split("\n")
    before = lines[line][:char] if line < len(lines) else ""
    ctx = classify_context(before)
    return state, [rpc_response(msg_id, {"isIncomplete": False, "items": build_completions(ctx)})]

def handle_definition(state: ServerState, params: dict, msg_id: Any) -> Tuple[ServerState, list[dict]]:
    uri = params.get("textDocument", {}).get("uri", "")
    pos = params.get("position", {})
    src = state.find_document(uri) or ""
    if not src:
        return state, [rpc_response(msg_id, None)]
    resolved = resolve_template_path(uri, src, pos.get("line", 0))
    if resolved:
        return state, [rpc_response(msg_id, {"uri": resolved, "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}})]
    return state, [rpc_response(msg_id, None)]

def handle_formatting(state: ServerState, params: dict, msg_id: Any) -> Tuple[ServerState, list[dict]]:
    uri = params.get("textDocument", {}).get("uri", "")
    src = state.find_document(uri) or ""
    if not src:
        return state, [rpc_response(msg_id, [])]
    try:
        formatted = format_twig(src)
    except Exception:
        formatted = src
    lines = src.split("\n")
    return state, [rpc_response(msg_id, [{"range": {"start": {"line": 0, "character": 0}, "end": {"line": max(len(lines) - 1, 0), "character": len(lines[-1]) if lines else 0}}, "newText": formatted}])]

def handle_shutdown(state: ServerState, params: dict, msg_id: Any) -> Tuple[ServerState, list[dict]]:
    return state, [rpc_response(msg_id, None)]


# ═══════════════════════════════════════════════════════════════════════
# 5. Dispatch tables — method → pure handler
# ═══════════════════════════════════════════════════════════════════════

NOTIFICATION_HANDLERS: Dict[str, Callable] = {
    "initialized":               handle_initialized,
    "textDocument/didOpen":      handle_did_open,
    "textDocument/didChange":    handle_did_change,
    "textDocument/didClose":     handle_did_close,
}

REQUEST_HANDLERS: Dict[str, Callable] = {
    "initialize":                handle_initialize,
    "textDocument/hover":        handle_hover,
    "textDocument/completion":   handle_completion,
    "textDocument/definition":   handle_definition,
    "textDocument/formatting":   handle_formatting,
    "shutdown":                  handle_shutdown,
}


def dispatch_request(state: ServerState, method: str, params: dict, msg_id: Any) -> Tuple[ServerState, list[dict]]:
    handler = REQUEST_HANDLERS.get(method)
    if handler:
        return handler(state, params, msg_id)
    return state, [rpc_error(msg_id, -32601, f"Method not found: {method}")]

def dispatch_notification(state: ServerState, method: str, params: dict) -> Tuple[ServerState, list[dict]]:
    handler = NOTIFICATION_HANDLERS.get(method)
    if handler:
        return handler(state, params)
    return state, []


# ═══════════════════════════════════════════════════════════════════════
# 6. Transport — IO shell only, pure functions do the work
# ═══════════════════════════════════════════════════════════════════════

class LspTransport:
    """Minimal async LSP transport. All logic in pure handler functions."""

    def __init__(self):
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._running = False

    async def start(self) -> None:
        loop = asyncio.get_event_loop()
        self._reader = asyncio.StreamReader(loop=loop)
        proto = asyncio.StreamReaderProtocol(self._reader)
        await loop.connect_read_pipe(lambda: proto, sys.stdin)
        transport, _ = await loop.connect_write_pipe(asyncio.Protocol, sys.stdout)
        self._writer = asyncio.StreamWriter(transport, proto, self._reader, loop)
        self._running = True

    def write(self, msg: dict) -> None:
        body = json.dumps(msg, ensure_ascii=False)
        header = f"Content-Length: {len(body.encode('utf-8'))}\r\n\r\n"
        self._writer.write((header + body).encode("utf-8"))

    async def read_one(self) -> Optional[dict]:
        try:
            header = b""
            while not header.endswith(b"\r\n\r\n"):
                ch = await self._reader.read(1)
                if not ch:
                    return None
                header += ch
            cl = int(header.decode().split(":")[1].strip())
            body = await self._reader.readexactly(cl)
            return json.loads(body.decode("utf-8"))
        except Exception:
            return None

    async def run(self, initial_state: ServerState) -> None:
        state = initial_state
        while self._running:
            raw = await self.read_one()
            if raw is None:
                break
            method = raw.get("method", "")
            params = raw.get("params", {})
            msg_id = raw.get("id")
            if msg_id is not None:
                state, msgs = dispatch_request(state, method, params, msg_id)
            elif method:
                state, msgs = dispatch_notification(state, method, params)
            else:
                msgs = []
            for msg in msgs:
                self.write(msg)
            if method == "exit":
                self._running = False


# ═══════════════════════════════════════════════════════════════════════
# 7. Entry point
# ═══════════════════════════════════════════════════════════════════════

async def main() -> None:
    transport = LspTransport()
    await transport.start()
    state = ServerState.create()
    await transport.run(state)


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
