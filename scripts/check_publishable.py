#!/usr/bin/env python3
"""Nothing tracked here points to a private source.

This repository is public. It must not name the owner's private
repositories, point into them, carry their record identifiers, point to an
unpublished paper, or name what has not been announced. Every name this
check looks for is kept here only as a SHA-256 hash, so that this file does
not publish it either. A pointer to a private source is replaced by the
public source it rests on, or by a plain statement with no link; this check
fails on what is left.

The patterns are deliberately broad. "the paper" is flagged wherever it
appears, so a public paper is named ("Merces's paper") rather than left
anonymous. The Python package under `ref/python/` keeps its name as a code
identifier, allowed in code and in paths; in a document, its bare name is
flagged, since a document names this repository by its own name.

Reads `git ls-files`, so run it after `git add`.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# The private repositories' names, matched as whole tokens of letters, digits,
# underscores and hyphens, as written.
PRIVATE = {
    "2530467418c6eee8c45943f4bf78ca20ecce0cbcfd429f350fb9ffbf961bfb60",
    "25c53c0acb448bfa257df9c4aa39c883209fd0eb4852bc62b5e29b5b98b88986",
    "56b6b7de8479ddcb9ad3bcef005008a316b4c5d35fa035ebd9a9a59e67457e4f",
    "573eceabfab2d795d6b375f1b9c3f0d12e3eeb12d78dd4276886e6d4be990bdd",
    "637585967eec911d261c8e19c95240637144bf7e7814d599a7daba176edb9931",
    "961b6dd3ede3cb8ecbaacbd68de040cd78eb2ed5889130cceb4c49268ea4d506",
    "bf776270176c7c3573211f52bcf87433e96448c1507c58845689b14501a11478",
    "c53cf1ff2dc337714990f603ab100c18c6b0d25f06cf7e575045118253cdd8fe",
    "c83e8c9b67765aff1bbc172da4f574f9e76ddbef6175793629b88ef3ea7478f2",
    "e9a1079182ff8c9ac16fae1bde3cf8aceb9f79091845d9c5f4aa3ab35f89cab3",
    "f95b812d3aca261fab7e8a53e4e0c5fdeaff585873c93ddbe7ebdaeeb970bb9b",
    "fd8d4dfc98c2ee7fe853ce4cdc209ad0a3210435b7b6f3e09e7d2c6de303b273",
}
# This repository's former name, a private repository's too.
FORMER = "b93df56252ba24bc7e00ee347df726dd2d2489824c6cecc1f5bc1b480562c455"
# The unpublished papers' working names, matched as whole tokens in any case.
PAPERS = {
    "441960680f0652d1271efbf0895ce6e14276f2ae9868fa358803084769dbba79",
    "cfcf3e35db09701d7bf41d5b305b8ef45ca7fdba7eb57f8fbc48ee1f618bea88",
    "e8f4f42b44ab8fe07a74e5be75ba4e19fff39834d8ec9b155ab89316918e835c",
}
WORD = re.compile(r"[\w-]+")
# A repository name, without a dot: none of the owner's has one, and a dot ends a sentence or starts ".git".
URL = re.compile(r"4w44h9jckz-boop/([\w-]+)")
PATTERNS = [
    ("a problem record identifier", re.compile(r"\bP\d{4}\b")),
    ("the paper", re.compile(r"paper/|\bvenue|draft paper|\bthe paper\b", re.I)),
]
# Names that must not appear, as SHA-256 hashes: a word, matched anywhere
# inside a longer token, and a domain, matched as the last labels of a host name.
HIDDEN_WORDS = {(10, "b279702a24a68e5697dd4a0a37ae81b3662abc24b2388b2822b80a16a00b6515")}
HIDDEN_DOMAINS = {"dd8a90df712c39165b71b0bd8f64992fa82406363afe3f39648f9c671ec30045"}
HOST = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
TOKEN = re.compile(r"[A-Za-z0-9]+")
# In a document: the package's name as a bare word, not in a path, an import or a dotted name, or in backticks.
BARE = re.compile(r"(?<![\w/.-])(?<!from )(?<!import )(\w+)(?![\w/.-])")
CODE = re.compile(r"`([^`]+)`")


def everywhere(line: str) -> list[tuple[str, str]]:
    found = []
    for word in WORD.findall(line):
        if _hash(word) in PRIVATE:
            found.append(("a private repository", word))
        elif _hash(word.lower()) in PAPERS:
            found.append(("the paper", word))
    for repo in URL.findall(line):
        if _hash(repo.lower()) in PRIVATE or _hash(repo.lower()) == FORMER:
            found.append(("a private repository's URL", repo))
    for what, pattern in PATTERNS:
        m = pattern.search(line)
        if m:
            found.append((what, m.group(0)))
    return found


def in_documents(line: str) -> list[tuple[str, str]]:
    words = BARE.findall(line) + CODE.findall(line)
    return [("this repository's former name", w) for w in words if _hash(w) == FORMER]


def hidden(line: str) -> str | None:
    """A hidden word or domain in `line`, as the text it matched, or None."""
    for token in TOKEN.findall(line):
        for size, digest in HIDDEN_WORDS:
            for i in range(len(token) - size + 1):
                if _hash(token[i:i + size].lower()) == digest:
                    return token
    for host in HOST.findall(line):
        labels = host.split(".")
        for i in range(len(labels) - 1):
            if _hash(".".join(labels[i:]).lower()) in HIDDEN_DOMAINS:
                return host
    return None


SKIP = {"scripts/check_publishable.py", "LICENSE"}


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [line for line in out.stdout.splitlines() if line]


def main() -> int:
    problems = []
    for name in tracked():
        if name in SKIP:
            continue
        path = ROOT / name
        try:
            text = path.read_text()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            found = everywhere(line) + (in_documents(line) if name.endswith(".md") else [])
            for what, match in dict.fromkeys(found):
                problems.append(f"{name}:{n}: {what}: {match!r}")
            if hidden(line):
                problems.append(f"{name}:{n}: a name kept out of this repository")
    for p in problems:
        print(p)
    if problems:
        print(f"publishable: {len(problems)} lines point to a private source")
        return 1
    print("publishable: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
