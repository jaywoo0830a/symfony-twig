#!/usr/bin/env python3
"""Generate JSON data files for the VS Code extension from YAML definitions."""
import json
from pathlib import Path

import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / "twig_analyzer" / "data"
OUT_DIR = Path(__file__).resolve().parent.parent / "vscode-extension" / "data"
TWIG_DOCS = "https://twig.symfony.com/doc/3.x"


def main():
    tags = yaml.safe_load(open(DATA_DIR / "tags.yml"))
    filters = yaml.safe_load(open(DATA_DIR / "filters.yml"))
    functions = yaml.safe_load(open(DATA_DIR / "functions.yml"))
    tests = yaml.safe_load(open(DATA_DIR / "tests.yml"))
    signatures = yaml.safe_load(open(DATA_DIR / "signatures.yml"))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── hover-data.json ──
    hover = {}

    for name, info in tags.items():
        hover[name] = {
            "description": info.get("description", ""),
            "since": str(info.get("since", "—")),
            "example": info.get("example", ""),
            "link": f"{TWIG_DOCS}/tags/{name}.html",
        }

    for name, info in filters.items():
        hover[name] = {
            "description": info.get("description", f"Twig filter — {info.get('since', '—')}"),
            "since": str(info.get("since", "—")),
            "example": info.get("example", f"{{{{ data|{name} }}}}"),
            "link": f"{TWIG_DOCS}/filters/{name}.html",
        }

    for name, info in functions.items():
        hover[name] = {
            "description": info.get("description", f"Twig function — {info.get('since', '—')}"),
            "since": str(info.get("since", "—")),
            "example": info.get("example", f"{{{{ {name}() }}}}"),
            "link": f"{TWIG_DOCS}/functions/{name}.html",
        }

    for name, info in tests.items():
        clean = name.replace(" ", "")
        hover[name] = {
            "description": info.get("description", f"Twig test — {info.get('since', '—')}"),
            "since": str(info.get("since", "—")),
            "example": info.get("example", f"{{% if x is {name} %}}...{{% endif %}}"),
            "link": f"{TWIG_DOCS}/tests/{clean}.html",
        }

    # End tags
    block_tags = {n: i for n, i in tags.items() if i.get("block")}
    for name in block_tags:
        end = f"end{name}"
        hover[end] = {
            "description": f"Closes a {{% {name} %}} block",
            "since": "—",
            "example": f"{{% {end} %}}",
            "link": hover.get(name, {}).get("link", f"{TWIG_DOCS}/tags/{name}.html"),
        }

    json.dump(hover, open(OUT_DIR / "hover-data.json", "w"), indent=2, ensure_ascii=False)

    # ── signatures.json ──
    sig_out = {}
    for name, info in signatures.items():
        sig_out[name] = {
            "label": info["label"],
            "params": [{"name": p[0], "description": p[1]} for p in info.get("params", [])],
        }
    json.dump(sig_out, open(OUT_DIR / "signatures.json", "w"), indent=2, ensure_ascii=False)

    # ── completion-names.json ──
    json.dump(
        {
            "blockTags": sorted(block_tags.keys()),
            "inlineTags": sorted(n for n, i in tags.items() if not i.get("block")),
            "filterNames": sorted(filters.keys()),
            "functionNames": sorted(functions.keys()),
            "testNames": sorted(tests.keys()),
        },
        open(OUT_DIR / "completion-names.json", "w"),
        indent=2,
    )

    # ── end-tag-map.json ──
    end_tag_map = {n: f"end{n}" for n in block_tags}
    json.dump({"endTagMap": end_tag_map}, open(OUT_DIR / "end-tag-map.json", "w"), indent=2)

    print(f"Generated {len(hover)} hover entries, {len(sig_out)} signatures")
    print(f"  → {OUT_DIR}/hover-data.json")
    print(f"  → {OUT_DIR}/signatures.json")
    print(f"  → {OUT_DIR}/completion-names.json")
    print(f"  → {OUT_DIR}/end-tag-map.json")


if __name__ == "__main__":
    main()
