r"""Tables and fitted memory costs from a run of `bench/leanvm-memory/run.sh` (decision records 0033 and 0041).

    python3 bench/leanvm-memory/fit.py bench/results/2026-10-13-leanvm-memory.txt > bench/results/2026-10-13-leanvm-memory.md

Reads the raw output and prints, for each subject, what the process held
before the aggregate, its peak resident set while proving it, the time and
the proof. It then fits the peak against the number of inputs by least
squares, a line $m(n) = a + b n$ in MiB for each kind of subject, and both
kinds together as $a + b r + c s$ for $r$ recursive inputs and $s$
signatures, AG-10's form, which `cost()` returns, and the same slopes with
the base raised until the line is above every peak measured, which
`envelope()` returns for experiments to budget against (decision record
0042). Last, it prints how many recursive inputs an aggregate took within the
memory of a machine of 8, 16, 32 and 64 GiB, among the subjects measured.

A subject that ran out of memory has an exit status and no peak; it is
listed, and kept out of the fit. Standard library only; deterministic from
the raw file.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "bench" / "results" / "2026-10-13-leanvm-memory.txt"
KIB_PER_MIB = 1024
MACHINES_GIB = (8, 16, 32, 64)  # geth's minimum is 8GB RAM and its recommendation 16GB+ (decision record 0041)


def parse(path: Path = RAW) -> tuple[dict[str, str], list[dict]]:
    """The header's fields, and one record per subject in the order run."""
    header: dict[str, str] = {}
    runs: list[dict] = []
    for line in path.read_text().splitlines():
        if line.startswith("subject: "):
            fields = dict(kv.split("=") for kv in line[len("subject: "):].split()[1:])
            run = {"kind": line.split()[1], "n": int(fields["n"]), "per leaf": int(fields["per_leaf"])}
            if not runs or any(runs[-1][k] != v for k, v in run.items()):  # else the runner's note of its exit
                runs.append(run)
        elif not runs:
            if ": " in line and not line.startswith("#"):
                key, value = line.split(": ", 1)
                header[key] = value
        elif ": " in line:
            key, value = line.strip().split(": ", 1)
            if key not in ("kind", "n", "per leaf"):  # the subject line has them
                runs[-1][key] = value
    return header, runs


def proved(run: dict) -> bool:
    return "peak kib" in run and run.get("verified") == "yes"


def fit(points: list[tuple[float, float]]) -> tuple[float, float]:
    """Least squares: the intercept and slope of y against x."""
    n = len(points)
    mx = sum(x for x, _ in points) / n
    my = sum(y for _, y in points) / n
    sxx = sum((x - mx) ** 2 for x, _ in points)
    slope = sum((x - mx) * (y - my) for x, y in points) / sxx
    return my - slope * mx, slope


def line(kind: str, per_leaf: int, runs: list[dict]) -> tuple[float, float]:
    return fit([(r["n"], int(r["peak kib"]) / KIB_PER_MIB) for r in runs
                if r["kind"] == kind and r["per leaf"] == per_leaf and proved(r)])


def joint(runs: list[dict]) -> tuple[float, float, float]:
    """Least squares over the recursive subjects of one signature a leaf and the signature subjects together:
    the peak as $a + b r + c s$ in MiB, for $r$ recursive inputs and $s$ signatures verified directly, which is
    AG-10's form, one base for both."""
    rows = [(1.0, float(r["n"]) if r["kind"] == "recursive" else 0.0, float(r["n"]) if r["kind"] == "sphincs" else 0.0,
             int(r["peak kib"]) / KIB_PER_MIB)
            for r in runs if proved(r) and (r["kind"] == "sphincs" or r["per leaf"] == 1)]
    m = [[sum(x[i] * x[j] for x in rows) for j in range(3)] + [sum(x[i] * x[3] for x in rows)] for i in range(3)]
    for i in range(3):  # Gauss-Jordan on the normal equations
        pivot = m[i][i]
        m[i] = [v / pivot for v in m[i]]
        for k in range(3):
            if k != i:
                m[k] = [a - m[k][i] * b for a, b in zip(m[k], m[i])]
    return m[0][3], m[1][3], m[2][3]


def cost(path: Path = RAW) -> dict[str, float]:
    """AG-10's costs in MiB, rounded to a tenth, from the joint fit."""
    _, runs = parse(path)
    base, recursive, sig = joint(runs)
    return {"memory_base": round(base, 1), "memory_recursive": round(recursive, 1), "memory_sig": round(sig, 1)}


def joined(runs: list[dict]) -> list[tuple[int, int, float]]:
    """The subjects of the joint fit: recursive inputs of one signature, signatures verified directly, peak MiB."""
    return [((r["n"], 0) if r["kind"] == "recursive" else (0, r["n"])) + (int(r["peak kib"]) / KIB_PER_MIB,)
            for r in runs if proved(r) and (r["kind"] == "sphincs" or r["per leaf"] == 1)]


def envelope(path: Path = RAW) -> dict[str, float]:
    """AG-10's costs in MiB that no subject of the joint fit exceeded: its slopes, and its base raised by the most
    any peak lay above it, rounded up to a tenth. A node that budgets against these ran out of no memory measured."""
    _, runs = parse(path)
    c = cost(path)
    over = max(peak - (c["memory_base"] + c["memory_recursive"] * rec + c["memory_sig"] * sig)
               for rec, sig, peak in joined(runs))
    return {**c, "memory_base": math.ceil((c["memory_base"] + over) * 10 - 1e-9) / 10}


def main(path: Path) -> None:
    header, runs = parse(path)
    out = print
    out("# leanVM: the memory an aggregate takes to prove")
    out()
    out(f"From `{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}`, printed by "
        "`bench/leanvm-memory/fit.py` (decision records 0033 and 0041).")
    out()
    for key in ("date", "leanvm commit", "commit", "harness sha256", "cpu", "cores", "memory",
                "memory limit of this process group", "rustc", "log_inv_rate"):
        out(f"- {key}: {header[key]}")
    out()
    out("Each subject is a process of its own (`bench/leanvm-memory/memory.rs`). A recursive subject first makes")
    out("its inputs, leaf aggregates of the leanSPHINCS signatures per leaf shown; a signature subject verifies")
    out("its signatures directly. The process's peak is then reset, and one aggregate proved twice, the first")
    out("discarded: held is what the process had resident before, peak its highest resident set while proving,")
    out("which includes what it held, and time the second proof's.")
    out()
    out("## Runs")
    out()
    out("| kind | inputs | signatures per leaf | held MiB | peak MiB | peak GiB | prove ms | cycles | proof KiB |")
    out("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in runs:
        leaf = r["per leaf"] if r["kind"] == "recursive" else ""
        if not proved(r):
            out(f"| {r['kind']} | {r['n']} | {leaf} | | exit status {r.get('exit status', 'none')} | | | | |")
            continue
        peak = int(r["peak kib"]) / KIB_PER_MIB
        out(f"| {r['kind']} | {r['n']} | {leaf} | {int(r['held kib']) / KIB_PER_MIB:.1f} | {peak:.1f} | "
            f"{peak / 1024:.2f} | {float(r['prove ms']):.1f} | {int(r['cycles']):,} | "
            f"{int(r['proof bytes']) / 1024:.1f} |")
    out()
    out("## Fitted")
    out()
    out("The peak against the number of inputs, by least squares, $m(n) = a + b n$ in MiB, over the subjects that")
    out("proved:")
    out()
    out("| aggregate over | a, MiB | b, MiB an input |")
    out("| --- | --- | --- |")
    for label, kind, leaf in (("recursive inputs of 1 signature", "recursive", 1),
                              ("recursive inputs of 16 signatures", "recursive", 16),
                              ("leanSPHINCS signatures, directly", "sphincs", 0)):
        a, b = line(kind, leaf, runs)
        out(f"| {label} | {a:.1f} | {b:.1f} |")
    out()
    c = cost(path)
    out("Both kinds together, $m(r, s) = a + b r + c s$ for $r$ recursive inputs of one signature and $s$")
    out(f"signatures verified directly, which is AG-10's form (`docs/spec/05-aggregation.md`): `memory_base` "
        f"{c['memory_base']}, `memory_recursive` {c['memory_recursive']} and `memory_sig` {c['memory_sig']} MiB.")
    out("Each line is a summary: memory follows the VM's tables, each padded to a power of two, so it rises in")
    out("steps, and subjects whose tables pad alike peak alike.")
    out()
    out("| kind | inputs | peak GiB | by the joint fit, GiB | by the envelope, GiB |")
    out("| --- | --- | --- | --- | --- |")
    e = envelope(path)
    for rec, sig, peak in joined(runs):
        kind, n = ("recursive", rec) if rec else ("sphincs", sig)
        fitted = c["memory_base"] + c["memory_recursive"] * rec + c["memory_sig"] * sig
        bound = e["memory_base"] + e["memory_recursive"] * rec + e["memory_sig"] * sig
        out(f"| {kind} | {n} | {peak / 1024:.2f} | {fitted / 1024:.2f} | {bound / 1024:.2f} |")
    out()
    out(f"The envelope, the last column, is the joint fit with `memory_base` raised to {e['memory_base']} MiB, by "
        "the most any peak lay above the fit, so that no subject's peak exceeds it: the costs a node that must not "
        "run out of memory budgets against (decision record 0042).")
    out()
    out("## What a machine's memory holds")
    out()
    out("The most recursive inputs of one signature an aggregate took, among the subjects measured, with a peak")
    out("within a machine's memory and nothing else resident; and whether a subject with one more input was")
    out("measured to need more.")
    out()
    measured = sorted((r["n"], int(r["peak kib"]) / KIB_PER_MIB / 1024) for r in runs
                      if r["kind"] == "recursive" and r["per leaf"] == 1 and proved(r))
    failed = sorted(r["n"] for r in runs if r["kind"] == "recursive" and r["per leaf"] == 1 and not proved(r))
    out("| machine GiB | inputs | one more |")
    out("| --- | --- | --- |")
    for gib in MACHINES_GIB:
        fits = [n for n, peak in measured if peak <= gib]
        most = max(fits, default=0)
        over = [n for n, peak in measured if peak > gib and n > most]
        if over:
            out(f"| {gib} | {most} | {min(over)} inputs peaked at {dict(measured)[min(over)]:.2f} GiB |")
        else:
            out(f"| {gib} | at least {most} | none measured above it |")
    out()
    limit = int(header["memory limit of this process group"].split()[0]) / 2**30
    out(f"Subjects of {' and '.join(map(str, failed))} inputs ran out of this machine's limit of {limit:.2f} GiB, so")
    out("nothing above it was measured; leanVM takes at most `MAX_RECURSIONS`, 16, inputs in one aggregate.")

if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else RAW)
