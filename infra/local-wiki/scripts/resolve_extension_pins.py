#!/usr/bin/env python3
"""Resolve each extension's symbolic ref to an exact commit SHA via `git ls-remote`.

Run on the host to create or bump pins:  uv run python scripts/resolve_extension_pins.py
Reads and rewrites extensions.json in place, preserving order and notes. Network required.

(The build-time cloner, fetch-extensions.sh, is bash because it runs inside the
php:7.4-apache image, which has no Python — this resolver runs on the dev host.)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


def resolve(repo: str, ref: str) -> str:
    """Return the commit SHA for `ref` in `repo`. A 40-char SHA is used as-is
    (off-branch pin). Otherwise resolve a branch first, then a tag, peeling
    annotated tags to their commit. Namespace-qualified so we never match an
    unrelated ref."""
    if _SHA_RE.match(ref):
        return ref
    for pattern in (f"refs/heads/{ref}", f"refs/tags/{ref}^{{}}", f"refs/tags/{ref}"):
        out = subprocess.run(
            ["git", "ls-remote", repo, pattern],
            capture_output=True, text=True, check=True,
        ).stdout
        if out.strip():
            return out.split()[0]
    sys.exit(f"ERROR: could not resolve {repo} @ {ref}")


def main() -> None:
    manifest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "extensions.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for ext in data["extensions"]:
        ext["commit"] = resolve(ext["repo"], ext["ref"])
        print(f"resolved {ext['name']} -> {ext['commit']}", file=sys.stderr)
    manifest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{manifest.name} updated.")


if __name__ == "__main__":
    main()
