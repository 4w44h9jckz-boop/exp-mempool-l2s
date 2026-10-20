#!/usr/bin/env python3
"""Every benchmark table is still what its derivation prints from the raw output (decision record 0033).

A raw file `bench/results/<date>-<tool>.txt` is a machine's measurement and is
never rerun. Its table, `bench/results/<date>-<tool>.md`, is printed from it by
`bench/<tool>/fit.py`, which is deterministic; this check reruns that and fails
if the committed table has moved. Reads `git ls-files`: run it after `git add`.
"""

from __future__ import annotations

import difflib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = re.compile(r"bench/results/\d{4}-\d{2}-\d{2}-([a-z0-9-]+)\.txt")


def main() -> int:
    files = subprocess.run(["git", "ls-files", "bench/results"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.split()
    problems, checked = [], 0
    for raw in files:
        m = RAW.fullmatch(raw)
        if not m:
            continue
        table = raw[:-len(".txt")] + ".md"
        derive = f"bench/{m.group(1)}/fit.py"
        if table not in files:
            problems.append(f"{raw}: no {table} beside it")
            continue
        if not (ROOT / derive).exists():
            problems.append(f"{raw}: no {derive} to derive {table}")
            continue
        out = subprocess.run([sys.executable, derive, raw], cwd=ROOT, capture_output=True, text=True)
        if out.returncode != 0:
            problems.append(f"{derive} failed on {raw}:\n{out.stderr}")
            continue
        committed = (ROOT / table).read_text()
        if out.stdout != committed:
            diff = difflib.unified_diff(committed.splitlines(), out.stdout.splitlines(), table, "derived", lineterm="")
            problems.append(f"{table} is not what {derive} prints:\n" + "\n".join(list(diff)[:40]))
        checked += 1
    for p in problems:
        print(p)
    if not problems:
        print(f"bench: ok ({checked} tables)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
