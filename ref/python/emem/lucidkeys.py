"""The key round of EIP-8184 (LUCID): `docs/spec/06-lucid.md`, LU-14 to LU-19.

Between the block that commits sealed transactions and the block that runs
them: the commitments, a key message's validity, when a key publisher may
release, a committee member's vote, the next slot's tally, and what the
record says of a key the tally finds missing. Decision record 0070.

Every function here reads the ticket, the block, key messages, times and
votes. The one step that reads a ciphertext, LU-15's step 6, goes through a
`Decrypt` callable, so a caller can see exactly which ciphertexts were read
and when; the default reads the sealed transaction's `decrypts` field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .keccak import keccak256
from .sealed import SealedPoolConfig, SealedTx

# LU-15's reasons, in the order they are checked
CHAIN, BLOCK, INDEX, LENGTH, KEY, DECRYPT, VALID = "chain", "block", "index", "length", "key", "decrypt", "valid"
MISSING, OBSERVED = "missing", "observed"
UNDECRYPTABLE, LATE, WITHHELD, UNVOTED = "undecryptable", "late", "withheld", "unvoted"


@dataclass(frozen=True)
class STCommitment:
    """LU-14: one entry of the bid's `st_commitments`, for a standalone sealed transaction."""

    root: str  # commitment_root, the ticket's hash
    key: bytes  # commitment_key
    gas_obligation: int
    executable: tuple[int, ...] = ()


@dataclass(frozen=True)
class SchedulingBlock:
    """A block that carries commitments, named by its root and slot (LU-14)."""

    root: str
    slot: int
    sealed: tuple[SealedTx, ...]  # LU-12's commitments, in commitment order
    gas_limit: int = 30_000_000
    attested: bool = True

    def commitments(self) -> list[STCommitment]:
        """LU-14: read from each ticket alone."""
        return [STCommitment(st.hash, st.commitment_key, st.gas_limit) for st in self.sealed]


@dataclass(frozen=True)
class KeyMessage:
    """LU-15: a `LucidKeyMessage`."""

    chain_id: int
    root: str
    slot: int
    commit_index: int
    k_dems: tuple[bytes, ...]


Decrypt = Callable[[SchedulingBlock, int, bytes], bool]


def read_decrypts(block: SchedulingBlock, j: int, k_dem: bytes) -> bool:
    """LU-15 step 6 in the model: whether commitment j's ciphertext decrypts under the key."""
    st = block.sealed[j]
    return st.decrypts is None or st.decrypts


class Blocks:
    """The scheduling blocks a node holds, by root and slot."""

    def __init__(self, blocks: Iterable[SchedulingBlock], chain_id: int = 1):
        self.chain_id = chain_id
        self._by_name = {(b.root, b.slot): b for b in blocks}

    def get(self, root: str, slot: int) -> SchedulingBlock | None:
        return self._by_name.get((root, slot))


def public_check(msg: KeyMessage, blocks: Blocks) -> str | None:
    """LU-15 steps 1 to 5: the reason a message is refused, or None. Reads no ciphertext."""
    if msg.chain_id != blocks.chain_id:
        return CHAIN
    block = blocks.get(msg.root, msg.slot)
    if block is None:
        return BLOCK
    if not 0 <= msg.commit_index < len(block.sealed):
        return INDEX
    if len(msg.k_dems) != 1:
        return LENGTH
    if keccak256(msg.k_dems[0]) != block.sealed[msg.commit_index].commitment_key:
        return KEY
    return None


def check(msg: KeyMessage, blocks: Blocks, decrypt: Decrypt = read_decrypts) -> str:
    """LU-15: `valid`, or the first check that applies."""
    reason = public_check(msg, blocks)
    if reason is not None:
        return reason
    block = blocks.get(msg.root, msg.slot)
    return VALID if decrypt(block, msg.commit_index, msg.k_dems[0]) else DECRYPT


def may_release(block: SchedulingBlock, publisher: str, cfg: SealedPoolConfig, observed: bool = True) -> list[int]:
    """LU-16: the indices of the commitments whose key `publisher` may release."""
    if not observed or not block.attested:
        return []
    if sum(st.gas_limit for st in block.sealed) > cfg.tob_gas_limit(block.gas_limit):
        return []
    return [j for j, st in enumerate(block.sealed)
            if publisher in (st.key_publisher, st.sender) and j <= st.max_preceding]


def release(block: SchedulingBlock, publisher: str, cfg: SealedPoolConfig, chain_id: int = 1,
            observed: bool = True) -> list[KeyMessage]:
    """LU-16: the key messages `publisher` may release, in commitment order."""
    return [KeyMessage(chain_id, block.root, block.slot, j, (block.sealed[j].dem_key,))
            for j in may_release(block, publisher, cfg, observed)]


def vote(block: SchedulingBlock, blocks: Blocks, received: Iterable[tuple[KeyMessage, int]], deadline: int,
         decrypt: Decrypt = read_decrypts) -> tuple[int, ...]:
    """LU-17: `keys_observed` from the messages received, each with the time it arrived.

    A message after the deadline is not checked, and one for a bit already set is not checked again,
    so `decrypt` is called only for a key received in time that passed LU-15's public checks.
    """
    bits = [0] * len(block.sealed)
    for msg, at in sorted(received, key=lambda r: r[1]):
        if at > deadline or (msg.root, msg.slot) != (block.root, block.slot):
            continue
        if 0 <= msg.commit_index < len(bits) and bits[msg.commit_index]:
            continue
        if check(msg, blocks, decrypt) == VALID:
            bits[msg.commit_index] = 1
    return tuple(bits)


@dataclass(frozen=True)
class Counts:
    """LU-18 for one key."""

    t1: int = 0
    t0: int = 0
    l1: int = 0
    l0: int = 0
    e: int = 0

    def allowed(self) -> tuple[str, ...]:
        """The treatments the two conditions allow, sorted; at least one holds."""
        out = []
        if 2 * self.t1 <= self.t1 + self.t0 + self.l0 + self.e:
            out.append(MISSING)
        if 2 * (self.t1 + self.l1 + self.e) > self.t1 + self.t0 + self.l1 + self.e:
            out.append(OBSERVED)
        return tuple(out)


def tally(n: int, ptc: Iterable[str], vote_deadline: int, attestation: int,
          votes: Iterable[tuple[str, tuple[int, ...], int]]) -> list[Counts]:
    """LU-18: the counts for each of `n` commitments from the votes received, each `(member, bits, at)`."""
    members = set(ptc)
    first: dict[str, tuple[tuple[int, ...], int]] = {}
    equivocated: set[str] = set()
    for member, bits, at in sorted(votes, key=lambda v: v[2]):
        bits = tuple(bits)
        if member not in members or at > attestation or len(bits) != n:
            continue
        if member in first and first[member][0] != bits:
            equivocated.add(member)
        first.setdefault(member, (bits, at))
    e = len(equivocated)
    counts = []
    for j in range(n):
        c = dict(t1=0, t0=0, l1=0, l0=0)
        for member, (bits, at) in first.items():
            if member in equivocated:
                continue
            c[("t" if at <= vote_deadline else "l") + str(bits[j])] += 1
        counts.append(Counts(e=e, **c))
    return counts


def treat(allowed: tuple[str, ...]) -> str:
    """LU-19: the reference's builder treats a key as observed wherever the tally allows it."""
    return OBSERVED if OBSERVED in allowed else MISSING


def blame(block: SchedulingBlock, blocks: Blocks, counts: list[Counts], received: Iterable[tuple[KeyMessage, int]],
          deadline: int, decrypt: Decrypt = read_decrypts) -> tuple[list[int], dict[int, str]]:
    """LU-19: the indices revealed, and for each key treated as missing what the record says of it."""
    received = list(received)
    revealed, missing = [], {}
    for j, c in enumerate(counts):
        passing = [(m, at) for m, at in received
                   if (m.root, m.slot, m.commit_index) == (block.root, block.slot, j) and public_check(m, blocks) is None]
        in_time = [m for m, at in passing if at <= deadline]
        if treat(c.allowed()) == OBSERVED:
            if decrypt(block, j, block.sealed[j].dem_key):
                revealed.append(j)
            continue
        if in_time and not decrypt(block, j, in_time[0].k_dems[0]):
            missing[j] = UNDECRYPTABLE
        elif not in_time:
            missing[j] = LATE if passing else WITHHELD
        else:
            missing[j] = UNVOTED
    return revealed, missing
