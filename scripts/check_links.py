#!/usr/bin/env python3
"""Every file a document cites exists on the branch.

Checks relative markdown links, and backticked paths whose first component is a
top-level entry of this repository (so `docs/spec/README.md` is checked, while
go-ethereum paths such as `core/txpool/validation.go` and other repositories'
paths are not). Reads `git ls-files`: run it after `git add`.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
TICKED = re.compile(r"`([A-Za-z0-9_./-]+)`")


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return out.stdout.split()


def main() -> int:
    files = tracked()
    top = {f.split("/")[0] for f in files}
    existing = set(files) | {str(Path(f).parent) for f in files} | {str(p) for f in files for p in Path(f).parents}
    problems = []
    for doc in (f for f in files if f.endswith(".md")):
        text = (ROOT / doc).read_text()
        base = Path(doc).parent
        for target in LINK.findall(text):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            path = target.split("#")[0]
            resolved = (ROOT / base / path).resolve()
            try:
                rel = str(resolved.relative_to(ROOT))
            except ValueError:
                problems.append(f"{doc}: link outside the repository: {target}")
                continue
            if rel != "." and rel not in existing:
                problems.append(f"{doc}: broken link: {target}")
        for path in TICKED.findall(text):
            if "/" not in path or path.split("/")[0] not in top or "*" in path:
                continue
            if re.search(r"[A-Z]{2,}", path):  # a template such as experiments/NN-name/ or log/YYYY-MM-DD.md
                continue
            if path.rstrip("/") not in existing:
                problems.append(f"{doc}: cites a path that does not exist: {path}")
    for p in problems:
        print(p)
    if not problems:
        print("links: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
