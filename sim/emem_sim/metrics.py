"""What a run records, and the summaries experiments report."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class TxRecord:
    tx: object
    submitted_at: float
    origin: str
    first_seen: dict[str, float] = field(default_factory=dict)  # node -> time it became pending there
    results: Counter = field(default_factory=Counter)  # admission results across nodes
    included_at: float | None = None
    block: int | None = None
    dropped: Counter = field(default_factory=Counter)  # drop reasons across nodes
    via: dict[str, str] = field(default_factory=dict)  # node -> how it was admitted there from a wrapper
    skipped: int = 0  # announcements not fetched because their budget hint was above the node's bound
    listed_at: float | None = None  # when an includer first listed it (IL-2)
    listed: int = 0  # how many ILs listed it


HASH_BYTES = 32
TRIPLE_BYTES = 96


class Recorder:
    def __init__(self) -> None:
        self.txs: dict[str, TxRecord] = {}
        self.blocks: list[dict] = []
        self.missed_slots: list[dict] = []  # slots without a block (IL-8)
        self.samples: list[dict] = []
        self.wrappers: Counter = Counter()  # EIP-8288 wrapper traffic, by (kind, quantity)
        self.refused_wrappers: Counter = Counter()  # by code

    def submitted(self, tx, at: float, origin: str) -> None:
        self.txs.setdefault(tx.hash, TxRecord(tx, at, origin))

    def admission(self, tx, node: str, result: str) -> None:
        rec = self.txs.get(tx.hash)
        if rec is not None:
            rec.results[result] += 1

    def pending(self, tx, node: str, at: float) -> None:
        rec = self.txs.get(tx.hash)
        if rec is not None and node not in rec.first_seen:
            rec.first_seen[node] = at

    def skipped(self, h: str) -> None:
        rec = self.txs.get(h)
        if rec is not None:
            rec.skipped += 1

    def dropped(self, tx, node: str, reason: str) -> None:
        rec = self.txs.get(tx.hash)
        if rec is not None:
            rec.dropped[reason] += 1

    def listed(self, tx, at: float) -> None:
        rec = self.txs.get(tx.hash)
        if rec is not None:
            rec.listed += 1
            if rec.listed_at is None:
                rec.listed_at = at

    def missed(self, at: float, proposer: str, extra: dict | None = None) -> None:
        self.missed_slots.append({"at": at, "proposer": proposer, **(extra or {})})

    def block(self, number: int, at: float, txs, base_fee: int, gas_used: int, gas_limit: int,
              failed=(), proposer: str = "", commitments=(), decrypted=(), extra: dict | None = None) -> None:
        """A block, with `failed`, the (transaction, error) pairs its builder skipped (BB-3), and its sealed
        `commitments` (LU-12) and `decrypted` transactions (LU-13). A sealed transaction is included when
        it is committed."""
        self.blocks.append({"number": number, "at": at, "txs": len(txs), "base_fee": base_fee,
                            "gas_used": gas_used, "gas_limit": gas_limit, "proposer": proposer,
                            "failed": Counter(err for _, err in failed), "commitments": tuple(commitments),
                            "decrypted": len(decrypted), **(extra or {})})
        for tx in list(txs) + [c.tx for c in commitments]:
            rec = self.txs.get(tx.hash)
            if rec is not None and rec.included_at is None:
                rec.included_at, rec.block = at, number

    def wrapper_sent(self, wrapper, node: str, kind: str) -> None:
        """One wrapper on one link: its count, its STARKs, its direct proofs, and its bytes but the proofs'."""
        w = self.wrappers
        w[(kind, "messages")] += 1
        w[(kind, "starks")] += 1 if wrapper.mode == 1 else 0
        w[(kind, "proofs")] += len(wrapper.proofs)
        w[(kind, "tx_bytes")] += sum(e.encoded_size for e in wrapper.txs if not isinstance(e, str))
        w[(kind, "hash_bytes")] += HASH_BYTES * sum(1 for e in wrapper.txs if isinstance(e, str))
        w[(kind, "dep_bytes")] += TRIPLE_BYTES * len(wrapper.deps)
        w[(kind, "entries")] += len(wrapper.txs)

    def wrapper_received(self, wrapper, node: str, results, kind: str = "") -> None:
        """`kind` says where it came from: `user`, `aggregate` or `forwarded`."""
        if isinstance(results, str):
            self.refused_wrappers[results] += 1
            return
        for entry, result in zip(wrapper.txs, results):
            if result == "ok" and not isinstance(entry, str):
                rec = self.txs.get(entry.hash)
                if rec is not None:
                    rec.via.setdefault(node, kind)

    def sample(self, at: float, **values) -> None:
        self.samples.append({"at": at, **values})

    # --- summaries ---------------------------------------------------------------

    def inclusion_delays(self) -> list[float]:
        return [r.included_at - r.submitted_at for r in self.txs.values() if r.included_at is not None]

    def propagation_times(self, nodes: int, fraction: float) -> list[float]:
        """Per transaction, the time from submission until `fraction` of nodes held it pending."""
        need = max(1, math.ceil(fraction * nodes))
        out = []
        for r in self.txs.values():
            seen = sorted(r.first_seen.values())
            if len(seen) >= need:
                out.append(seen[need - 1] - r.submitted_at)
        return out


def percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile; None for no data."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[rank - 1]


def fmt(value, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def table(headers: list[str], rows: list[list]) -> str:
    """A markdown table, ASCII only."""
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(" --- " for _ in headers) + "|"]
    lines += ["| " + " | ".join(fmt(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)
