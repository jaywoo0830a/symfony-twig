# ═══════════════════════════════════════════════════════════════════════
# Twig Analyzer — Multi-stage Dockerfile
# ═══════════════════════════════════════════════════════════════════════
#
# Stages:
#   builder  → compiles the Python wheel
#   runtime  → production LSP server  (minimal, ~120 MB)
#   dev      → development with hot-reload, test tools
#   test     → CI runner: pytest, coverage
#
# Build targets:
#   docker build --target runtime -t twig-analyzer-lsp .
#   docker build --target dev     -t twig-analyzer-dev .
#   docker build --target test    -t twig-analyzer-test .
#
# Override entrypoint for CLI usage:
#   docker run --rm twig-analyzer-lsp twig-analyze templates/

# ═══════════════════════════════════════════
# Stage 0: Builder
# ═══════════════════════════════════════════
FROM python:3.14-slim AS builder

WORKDIR /build
COPY pyproject.toml .
COPY twig_analyzer/ twig_analyzer/
COPY README.md .

RUN pip install --no-cache-dir build && \
    python -m build --wheel && \
    pip install --no-cache-dir dist/*.whl

# ═══════════════════════════════════════════
# Stage 1: Production Runtime
# ═══════════════════════════════════════════
FROM python:3.14-slim AS runtime

LABEL org.opencontainers.image.title="Twig Analyzer LSP"
LABEL org.opencontainers.image.description="Language Server Protocol server for Twig 3.x templates"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.authors="twig-analyzer"

RUN pip install --no-cache-dir pyyaml==6.2

COPY --from=builder /usr/local/lib/python3.14/site-packages/ /usr/local/lib/python3.14/site-packages/
COPY --from=builder /usr/local/bin/twig-analyze /usr/local/bin/twig-analyze

RUN useradd --create-home --shell /bin/bash twig && \
    mkdir -p /workspace && chown twig:twig /workspace

USER twig
WORKDIR /workspace

# Default: LSP server over stdio
ENTRYPOINT ["python", "-m", "twig_analyzer.lsp_server"]
CMD []

# ═══════════════════════════════════════════
# Stage 2: Development
# ═══════════════════════════════════════════
FROM runtime AS dev

USER root
RUN pip install --no-cache-dir \
    watchdog==6.1 \
    pytest==8.3 \
    pytest-cov==6.0 \
    pyyaml==6.2

USER twig

# Default: LSP with auto-reload
CMD ["sh", "-c", "watchmedo auto-restart --pattern='*.py' --directory=/workspace/twig_analyzer -- python -m twig_analyzer.lsp_server"]

# ═══════════════════════════════════════════
# Stage 3: Test / CI
# ═══════════════════════════════════════════
FROM runtime AS test

USER root
RUN pip install --no-cache-dir \
    pytest==8.3 \
    pytest-cov==6.0

COPY tests/ /workspace/tests/
COPY examples/ /workspace/examples/
COPY .twig-analyzer.yml /workspace/

USER twig

# Run tests by default; override command for specific options
ENTRYPOINT ["python", "-m", "pytest"]
CMD ["tests/", "-v", "--tb=short"]
