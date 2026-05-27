#!/usr/bin/env python3
"""Smoke test for the LSP server — sends initialize, didOpen, hover, shutdown."""

import json
import subprocess
import sys

MSG = [
    # Initialize
    {"jsonrpc": "2.0", "method": "initialize", "id": 1, "params": {"rootUri": "file:///test", "capabilities": {}}},
    # Initialized notification
    {"jsonrpc": "2.0", "method": "initialized", "params": {}},
    # Open a document with a Twig filter
    {"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {"textDocument": {"uri": "file:///test.twig", "text": "{{ name|upper }}"}}},
    # Hover on 'upper' (position after 'u')
    {"jsonrpc": "2.0", "method": "textDocument/hover", "id": 2, "params": {"textDocument": {"uri": "file:///test.twig"}, "position": {"line": 0, "character": 10}}},
    # Completion
    {"jsonrpc": "2.0", "method": "textDocument/completion", "id": 3, "params": {"textDocument": {"uri": "file:///test.twig"}, "position": {"line": 0, "character": 3}}},
    # Shutdown
    {"jsonrpc": "2.0", "method": "shutdown", "id": 4},
    {"jsonrpc": "2.0", "method": "exit"},
]


def send(proc, msg):
    body = json.dumps(msg)
    header = f"Content-Length: {len(body.encode())}\r\n\r\n"
    proc.stdin.write((header + body).encode())
    proc.stdin.flush()


def recv(proc):
    header = b""
    while not header.endswith(b"\r\n\r\n"):
        ch = proc.stdout.read(1)
        if not ch:
            return None
        header += ch
    cl = int(header.decode().split(":")[1].strip())
    body = proc.stdout.read(cl)
    return json.loads(body.decode())


def main():
    proc = subprocess.Popen(
        [sys.executable, "-m", "twig_analyzer.lsp_server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    results = []
    for i, msg in enumerate(MSG):
        send(proc, msg)
        if "id" in msg:
            r = recv(proc)
            results.append((msg["method"], msg["id"], r))

    proc.terminate()
    proc.wait(timeout=5)

    # Validate
    passed = 0
    failed = 0
    for method, mid, result in results:
        if method == "initialize":
            ok = result and "result" in result and "capabilities" in result["result"]
        elif method == "textDocument/hover":
            ok = result is not None  # null is valid (word not always found)
        elif method == "textDocument/completion":
            ok = result and "result" in result and "items" in result["result"]
        elif method == "shutdown":
            ok = result and "result" in result
        else:
            ok = True

        status = "✅" if ok else "❌"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"{status} {method} (id={mid})")

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
