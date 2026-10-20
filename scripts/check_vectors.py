#!/usr/bin/env python3
"""The vector set is consistent with the specification.

- every vector names a clause that exists in its `document`, lists in `also`
  only clauses that exist in some document, and was written against its
  document's current version;
- every clause of the FEE, NP, FP, BB, MA, AG, LU, IL, RR, EN, CG, SF, RP, DS and AM families has at least one vector,
  except those that only define parameters or terms (EXEMPT);
- vector files are well formed: known operation, a `distinguishes` sentence,
  named cases.

This checks the harness, not the implementation; `conformance/run.py` does that.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "spec"
VECTORS = ROOT / "conformance" / "vectors"
OPERATIONS = {"pool", "next_base_fee", "intrinsic_gas", "frame_gas", "ticket_fee", "surface", "replay",
              "claim_ticket", "descriptor", "key_round"}
NEEDS_VECTORS = ("FEE", "NP", "FP", "BB", "MA", "AG", "LU", "IL", "RR", "EN", "CG", "SF", "RP", "DS", "AM")
EXEMPT = {"NP-1", "FP-1", "MA-1", "AG-1", "LU-1", "LU-2", "IL-1", "RR-1", "EN-1", "CG-1", "SF-1", "AM-1",
          "AM-15"}  # profile tables and LU-2's object, exercised by every vector that uses them; AM-15 is not checked by a pool

CLAUSE = re.compile(r"^\*\*((?:MD|FEE|NP|FP|BB|MA|AG|LU|IL|RR|EN|CG|SF|RP|DS|AM)-\d+)\.", re.M)
VERSION = re.compile(r"^Version (\d+), ", re.M)


def main() -> int:
    clauses: dict[str, set[str]] = {}
    versions: dict[str, int] = {}
    for doc in sorted(SPEC.glob("[0-9]*.md")):
        text = doc.read_text()
        clauses[doc.name] = set(CLAUSE.findall(text))
        m = VERSION.search(text)
        versions[doc.name] = int(m.group(1)) if m else -1
    all_clauses = set().union(*clauses.values())
    problems, covered = [], set()
    for path in sorted(VECTORS.rglob("*.json")):
        name = path.relative_to(ROOT)
        try:
            vector = json.loads(path.read_text())
        except json.JSONDecodeError as err:
            problems.append(f"{name}: not JSON: {err}")
            continue
        doc = vector.get("document")
        if doc not in clauses:
            problems.append(f"{name}: unknown document {doc}")
            continue
        if vector.get("clause") not in clauses[doc]:
            problems.append(f"{name}: clause {vector.get('clause')} is not in {doc}")
        for clause in vector.get("also", []):
            if clause not in all_clauses:
                problems.append(f"{name}: also-clause {clause} is in no document")
        covered.update([vector.get("clause")] + vector.get("also", []))
        if vector.get("version") != versions[doc]:
            problems.append(f"{name}: written against version {vector.get('version')}, {doc} is at {versions[doc]}")
        if vector.get("operation") not in OPERATIONS:
            problems.append(f"{name}: unknown operation {vector.get('operation')}")
        if not vector.get("distinguishes"):
            problems.append(f"{name}: no distinguishes sentence")
        for case in vector.get("cases", []):
            if not case.get("name"):
                problems.append(f"{name}: a case without a name")
    for clause in sorted(all_clauses):
        if clause.startswith(NEEDS_VECTORS) and clause not in covered and clause not in EXEMPT:
            problems.append(f"{clause} has no vector")
    for p in problems:
        print(p)
    if not problems:
        print(f"vectorset: ok ({len(covered)} clauses covered)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
