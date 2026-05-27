# LSP Server & Docker

The Twig Analyzer runs in Docker across **test, dev, and production** environments.

## Quick Start — `run/up.sh` / `run/down.sh`

```bash
./run/up.sh              # production LSP (TCP :2087)
./run/up.sh --dev        # development with hot-reload (TCP :2088)
./run/test.sh            # run pytest (local venv)
./run/test.sh --docker   # run pytest (Docker container)
./run/up.sh --cli "analyze templates/"   # run CLI
./run/up.sh --stdio      # stdio mode for editor pipe
./run/up.sh --build      # force rebuild images

./run/down.sh            # stop all
./run/down.sh --clean    # stop + remove images & volumes
```

## Architecture — Multi-Stage Dockerfile

```
┌─────────────────────────────────────────────────────┐
│  Dockerfile (multi-stage)                            │
│                                                      │
│  builder ──→ runtime ──→ dev                        │
│  (wheel)     (LSP)       (watchdog + reload)         │
│              │                                       │
│              └──→ test                               │
│                   (pytest + coverage)                │
└─────────────────────────────────────────────────────┘
```

| Stage | Image | Size | Purpose |
|---|---|---|---|
| `builder` | — | — | Builds Python wheel |
| `runtime` | `twig-analyzer-lsp` | ~120 MB | Production LSP |
| `dev` | `twig-analyzer-dev` | ~150 MB | Hot-reload + pytest |
| `test` | `twig-analyzer-test` | ~140 MB | CI test runner |

## Docker Compose Services

| Service | Profile | Port | Purpose |
|---|---|---|---|
| `lsp` | (default) | 2087 | Production LSP |
| `lsp-dev` | `dev` | 2088 | Dev with auto-reload |
| `test` | `ci` | — | pytest + coverage |
| `cli` | `tools` | — | `twig-analyze` CLI |

## Environment Matrix

| Environment | Command | What runs |
|---|---|---|
| **Test** | `./run/test.sh` | pytest 137 tests (local venv) |
| **Test (Docker)** | `./run/test.sh --docker` | pytest + coverage + JUnit XML |
| **Dev** | `./run/up.sh --dev` | LSP + watchdog auto-restart |
| **Prod** | `./run/up.sh` | LSP with healthcheck, resource limits |
| **CLI** | `./run/up.sh --cli "analyze templates/"` | One-shot analysis |
| **Stdio** | `./run/up.sh --stdio` | Direct editor pipe |

## CI/CD Integration

### GitHub Actions

```yaml
name: Test
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker compose --profile ci run --rm test
      - uses: actions/upload-artifact@v4
        with:
          name: test-reports
          path: test-reports/
```

### GitLab CI

```yaml
test:
  image: docker:latest
  services:
    - docker:dind
  script:
    - docker compose --profile ci run --rm test
  artifacts:
    paths:
      - test-reports/
```

## Direct Docker Commands

```bash
# Build specific stage
docker build --target runtime -t twig-analyzer-lsp .
docker build --target dev     -t twig-analyzer-dev .
docker build --target test    -t twig-analyzer-test .

# Run tests
docker run --rm -v $(pwd):/workspace twig-analyzer-test

# Run CLI
docker run --rm -v $(pwd):/workspace twig-analyzer-lsp twig-analyze analyze templates/

# LSP stdio
docker run -i --rm -v $(pwd):/workspace:ro twig-analyzer-lsp
```

### Editor Configuration

**VS Code** (via TCP):

```json
{
  "twig-language-server": {
    "command": "docker",
    "args": ["run", "-i", "--rm", "twig-analyzer-lsp"],
    "filetypes": ["twig", "html.twig"]
  }
}
```

**Neovim** (via stdio):

```lua
-- Using nvim-lspconfig
require('lspconfig').twig_analyzer.setup({
  cmd = { 'docker', 'run', '-i', '--rm', '-v', vim.fn.getcwd()..':/workspace:ro', 'twig-analyzer-lsp' },
  filetypes = { 'twig', 'html.twig' },
})
```

---

