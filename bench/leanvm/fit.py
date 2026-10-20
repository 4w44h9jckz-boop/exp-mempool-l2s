r"""Tables and fitted proving costs from a run of `bench/leanvm/run.sh` (decision record 0033).

    python3 bench/leanvm/fit.py bench/results/2026-10-13-leanvm.txt > bench/results/2026-10-13-leanvm.md

Reads the raw output and prints, for every benchmark, the proving time, its
spread, the peak memory, the proof size and the verifying time, and beside
them the figures leanVM's README gives for the same benchmark on the
implementers' machine. It then fits two lines by least squares:

- the proving time of an aggregate of $n$ leanSPHINCS signatures, against
  $n$, whose intercept is AG-9's `prove_base` and whose slope is `prove_sig`;
- the proving time of a recursion over $k$ children of 16 signatures each,
  against $k$, whose slope is `prove_recursive`.

A leanSTARK dependency is a user's own STARK, which the aggregate verifies
as it verifies a child, so `prove_stark` is taken as `prove_recursive`
(decision record 0034). `costs()` returns the four, in ms, rounded to a tenth,
and `laptop_costs()` the same scaled to the README's machine: `prove_base` and
`prove_sig` by the ratio of the README's time to ours for its aggregation of
245 leanSPHINCS signatures, `prove_recursive` and `prove_stark` by the ratio
for its 2-to-1 recursion. A run that failed, as one the out-of-memory killer
stopped, is listed with its exit status and fitted from nothing.
Standard library only; deterministic from the raw file.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "bench" / "results" / "2026-10-13-leanvm.txt"

# leanVM's README at the same commit, 1f9e4c4f, "machine: M4 Max MacBook Pro (12
# performance cores, 4 efficiency cores, 48GB RAM)": seconds, GiB, KiB, ms.
README = {
    "aggregate --sphincs 245 --log-inv-rate 1": (0.831, 9.275, 299.9, 3.644),
    "aggregate --xmss 900 --log-inv-rate 1": (0.545, 7.385, 317.4, 3.977),
    "recursion --n 2 --xmss-per-leaf 900 --log-inv-rate 2": (0.272, 8.388, 190.2, 3.457),
}

NUMBER = r"([0-9][0-9,]*(?:\.[0-9]+)?)"


def number(text: str) -> float:
    return float(text.replace(",", ""))


def parse(path: Path = RAW) -> tuple[dict[str, str], list[dict]]:
    """The header's fields, and one record per benchmark in the order run."""
    header: dict[str, str] = {}
    runs: list[dict] = []
    current: dict | None = None
    for line in path.read_text().splitlines():
        if line.startswith("$ leanvm "):
            current = {"command": line[len("$ leanvm "):].strip()}
            runs.append(current)
        elif current is None:
            if ": " in line and not line.startswith("#"):
                key, value = line.split(": ", 1)
                header[key.strip()] = value.strip()
        elif m := re.search(r"proving time\s*:\s*" + NUMBER + r" s(?:\s*\+-\s*" + NUMBER + r"%)?\s+peak memory "
                            + NUMBER + " GiB", line):
            current["seconds"] = number(m.group(1))
            current["spread"] = number(m.group(2)) if m.group(2) else None
            current["gib"] = number(m.group(3))
        elif m := re.search(r"proof size\s*:\s*" + NUMBER + " KiB", line):
            current["kib"] = number(m.group(1))
        elif m := re.search(r"verifying\s*:\s*" + NUMBER + " ms", line):
            current["verify_ms"] = number(m.group(1))
        elif m := re.search(r"cycles \(VM steps\)\s*:\s*" + NUMBER, line):
            current["cycles"] = int(number(m.group(1)))
        elif m := re.search(r"exit status\s*:\s*([0-9]+)", line):
            current["status"] = int(m.group(1))
    return header, runs


def series(runs: list[dict], pattern: str) -> list[tuple[int, float]]:
    """(size, seconds) for every run whose command matches `pattern`, its first group the size."""
    out = []
    for run in runs:
        m = re.fullmatch(pattern, run["command"])
        if m and "seconds" in run:
            out.append((int(m.group(1)), run["seconds"]))
    return out


def line(points: list[tuple[int, float]]) -> tuple[float, float]:
    """Least-squares intercept and slope."""
    n = len(points)
    mx = sum(x for x, _ in points) / n
    my = sum(y for _, y in points) / n
    sxx = sum((x - mx) ** 2 for x, _ in points)
    sxy = sum((x - mx) * (y - my) for x, y in points)
    slope = sxy / sxx
    return my - slope * mx, slope


SPHINCS = r"aggregate --sphincs ([0-9]+) --log-inv-rate 1"
CHILDREN = r"recursion --n ([0-9]+) --xmss-per-leaf 0 --sphincs-per-leaf 16 --log-inv-rate 1"


def costs(path: Path = RAW) -> dict[str, float]:
    """AG-9's four constants, in ms, fitted from the run at `path`."""
    _, runs = parse(path)
    base, sig = line(series(runs, SPHINCS))
    _, child = line(series(runs, CHILDREN))
    return {"prove_base": round(base * 1000, 1), "prove_sig": round(sig * 1000, 1),
            "prove_recursive": round(child * 1000, 1), "prove_stark": round(child * 1000, 1)}


AGGREGATION = "aggregate --sphincs 245 --log-inv-rate 1"
RECURSION = "recursion --n 2 --xmss-per-leaf 900 --log-inv-rate 2"


def ratios(path: Path = RAW) -> dict[str, float]:
    """The README's time over ours, for its aggregation and for its recursion: two machines, one benchmark each."""
    _, runs = parse(path)
    ours = {r["command"]: r["seconds"] for r in runs if "seconds" in r}
    return {"aggregation": round(README[AGGREGATION][0] / ours[AGGREGATION], 3),
            "recursion": round(README[RECURSION][0] / ours[RECURSION], 3)}


def laptop_costs(path: Path = RAW) -> dict[str, float]:
    """AG-9's four constants scaled to the README's machine, each by the ratio for its kind of work."""
    c, r = costs(path), ratios(path)
    return {"prove_base": round(c["prove_base"] * r["aggregation"], 1),
            "prove_sig": round(c["prove_sig"] * r["aggregation"], 1),
            "prove_recursive": round(c["prove_recursive"] * r["recursion"], 1),
            "prove_stark": round(c["prove_stark"] * r["recursion"], 1)}


def proof_kib(path: Path = RAW) -> float:
    """The mean size of the recursions' proofs over children of 16 signatures, in KiB: what an aggregate weighs."""
    _, runs = parse(path)
    sizes = [r["kib"] for r in runs if re.fullmatch(CHILDREN, r["command"]) and "kib" in r]
    return round(sum(sizes) / len(sizes), 1)


def verify_ms(path: Path = RAW) -> float:
    """The mean time to verify those recursions' proofs, in ms: what checking one aggregate costs a node."""
    _, runs = parse(path)
    times = [r["verify_ms"] for r in runs if re.fullmatch(CHILDREN, r["command"]) and "verify_ms" in r]
    return round(sum(times) / len(times), 1)


def fmt(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:,.{digits}f}"


def main(path: Path) -> None:
    header, runs = parse(path)
    print("# leanVM benchmarks, " + header.get("date", "")[:10])
    print()
    print(f"From `bench/results/{path.name}`, printed by `bench/leanvm/run.sh`; this table and the fit are")
    print(f"printed from it by `python3 bench/leanvm/fit.py bench/results/{path.name}` (decision record 0033).")
    print()
    for key in ("date", "leanvm commit", "commit", "cpu", "cores", "memory",
                "memory limit of this process group", "rustc", "repeat"):
        if key in header:
            print(f"- {key}: {header[key]}")
    print()
    print("## Every run")
    print()
    print("Proving time is the mean of the measured passes after one warmup, with the CLI's spread;")
    print("peak memory is the process's, which for a recursion includes proving its children; the")
    print("README columns are leanVM's own figures for the same command at the same commit, on an M4")
    print("Max with 16 cores and 48 GB, quoted. A run with no time failed, with the exit status shown.")
    print()
    print("| command | cycles | proving s | spread % | peak GiB | proof KiB | verifying ms "
          "| README s | README GiB | this machine / README |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for run in runs:
        quoted = README.get(run["command"])
        ratio = run["seconds"] / quoted[0] if quoted and "seconds" in run else None
        cycles = f"{run['cycles']:,}" if "cycles" in run else "n/a"
        seconds = fmt(run.get("seconds")) if "status" not in run else f"exit status {run['status']}"
        print(f"| `{run['command']}` | {cycles} | {seconds} "
              f"| {fmt(run.get('spread'), 1)} | {fmt(run.get('gib'))} | {fmt(run.get('kib'), 1)} "
              f"| {fmt(run.get('verify_ms'))} | {fmt(quoted[0]) if quoted else ''} "
              f"| {fmt(quoted[1]) if quoted else ''} | {fmt(ratio, 2) if ratio else ''} |")
    print()
    print("## Fitted costs (AG-9)")
    print()
    sig_points, child_points = series(runs, SPHINCS), series(runs, CHILDREN)
    base, sig = line(sig_points)
    cbase, child = line(child_points)
    c = costs(path)
    print(f"- Aggregates of {', '.join(str(n) for n, _ in sig_points)} leanSPHINCS signatures: "
          f"intercept {base * 1000:.1f} ms, slope {sig * 1000:.2f} ms a signature.")
    print(f"- Recursions over {', '.join(str(k) for k, _ in child_points)} children of 16 signatures: "
          f"intercept {cbase * 1000:.1f} ms, slope {child * 1000:.2f} ms a child.")
    print()
    print("| AG-9 parameter | ms | taken from |")
    print("| --- | --- | --- |")
    print(f"| `prove_base` | {c['prove_base']} | the signature line's intercept |")
    print(f"| `prove_sig` | {c['prove_sig']} | the signature line's slope |")
    print(f"| `prove_recursive` | {c['prove_recursive']} | the recursion line's slope |")
    print(f"| `prove_stark` | {c['prove_stark']} | taken as `prove_recursive`, decision record 0034 |")
    print()
    r, lap = ratios(path), laptop_costs(path)
    print(f"Scaled to the README's machine, by its time over ours: {r['aggregation']} for "
          f"`{AGGREGATION}`, which scales `prove_base` and `prove_sig`, and {r['recursion']} for "
          f"`{RECURSION}`, which scales `prove_recursive` and `prove_stark`. Ratios between two machines on one "
          f"benchmark each, not a model of the laptop:")
    print()
    print("| AG-9 parameter | this machine, ms | the README's machine, ms |")
    print("| --- | --- | --- |")
    for key in ("prove_base", "prove_sig", "prove_recursive", "prove_stark"):
        print(f"| `{key}` | {c[key]} | {lap[key]} |")
    print()
    kib, ms = proof_kib(path), verify_ms(path)
    print(f"An aggregate's proof, the mean over those recursions, is {kib} KiB, and verifying it takes {ms} ms:")
    print(f"as long as a link of {kib * 1024 * 8 / (ms / 1000) / 1e6:.0f} Mbit/s takes to deliver it.")
    print()
    budget = 1000.0  # AGGREGATION_INTERVAL
    print("Within one `AGGREGATION_INTERVAL` of 1000 ms, an aggregate fits at most:")
    print()
    for name, k in (("this machine", c), ("the README's machine", lap)):
        room = max(0.0, budget - k["prove_base"])
        print(f"- on {name}, {int(room // k['prove_sig'])} leanSPHINCS triples verified directly, or "
              f"{int(room // k['prove_recursive'])} recursive inputs or leanSTARK triples.")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else RAW)
