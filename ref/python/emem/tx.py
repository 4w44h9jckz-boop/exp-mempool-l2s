"""Transactions: `docs/spec/00-model.md`, MD-5 to MD-7, FEE-3 and FEE-4."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, fields
from functools import cached_property

from .model import effective_tip

LEGACY, ACCESS_LIST, DYNAMIC_FEE, BLOB, SET_CODE, FRAME = 0, 1, 2, 3, 4, 6

DEFAULT_TO = "sink"


def _canonical(value):
    """A deterministic, hashable rendering of a field value (sets are sorted)."""
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(_canonical(v) for v in value))
    if isinstance(value, (list, tuple)):
        return tuple(_canonical(v) for v in value)
    if hasattr(value, "__dataclass_fields__"):
        return (type(value).__name__,) + tuple(_canonical(getattr(value, f.name)) for f in fields(value)
                                               if not (f.metadata.get("omit_none") and getattr(value, f.name) is None)
                                               and not f.metadata.get("not_identity"))
    return value


def _hash(obj) -> str:
    """MD-7: a deterministic function of every field, label included."""
    return "0x" + hashlib.sha256(repr(_canonical(obj)).encode()).hexdigest()


# --- account-nonce transactions (types 0 to 4) -------------------------------

INTRINSIC_BASE = 21000
INTRINSIC_CREATE = 32000
CALLDATA_NONZERO = 16
PER_AUTHORIZATION = 25000
TOKENS_PER_NONZERO_BYTE = 4


@dataclass(frozen=True, eq=False)
class Tx:
    """MD-5. Defaults match `conformance/README.md`."""

    sender: str
    nonce: int = 0
    gas: int = 21000
    max_fee: int = 100
    tip: int = 10
    value: int = 0
    to: str | None = DEFAULT_TO
    type: int = DYNAMIC_FEE
    data_size: int = 0
    size: int | None = None
    authorities: tuple[str | tuple[str, int], ...] = ()  # each an address, or (address, tuple nonce)
    delegate: str | None = None
    valid_signature: bool = True
    gas_used: int | None = None
    writes: tuple[tuple[str, int, int], ...] = ()
    root_writes: tuple[tuple[str, str, str], ...] = ()  # RR-3: (source_address, salt, root)
    label: str = ""
    state_gas_used: int | None = field(default=None, metadata={"omit_none": True})  # MD-5; absent, the hash is as it was
    # MD-5 version 8: what the execution pulls into `to` and pays out of it, and the gas a revert uses (BB-5);
    # absent, the hash is as it was under version 7
    pulls: tuple[tuple[str, int], ...] | None = field(default=None, metadata={"omit_none": True})
    pays: tuple[tuple[str, int], ...] | None = field(default=None, metadata={"omit_none": True})
    atomic: bool | None = field(default=None, metadata={"omit_none": True})  # None is true
    revert_gas_used: int | None = field(default=None, metadata={"omit_none": True})

    @cached_property
    def hash(self) -> str:
        return _hash(self)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Tx) and other.hash == self.hash

    def __hash__(self) -> int:
        return hash(self.hash)

    @property
    def encoded_size(self) -> int:
        return self.size if self.size is not None else 110 + self.data_size

    @property
    def cost(self) -> int:
        """MD-5: gas * max_fee + value."""
        return self.gas * self.max_fee + self.value

    @property
    def gas_limit(self) -> int:
        return self.gas

    @property
    def used(self) -> int:
        return self.gas if self.gas_used is None else self.gas_used

    @property
    def state_used(self) -> int:
        """MD-5: the part of `used` that is EIP-8037 state gas."""
        return 0 if self.state_gas_used is None else self.state_gas_used

    @property
    def reverted_used(self) -> int:
        """MD-5: the gas it uses if its execution reverts (BB-5)."""
        return self.used if self.revert_gas_used is None else self.revert_gas_used

    def effective_tip(self, base_fee: int) -> int:
        return effective_tip(self.max_fee, self.tip, base_fee)

    def name(self) -> str:
        return self.label or self.hash[:10]


def intrinsic_gas(tx: Tx) -> int:
    """FEE-3."""
    gas = INTRINSIC_BASE + CALLDATA_NONZERO * tx.data_size + PER_AUTHORIZATION * len(tx.authorities)
    if tx.to is None:
        gas += INTRINSIC_CREATE
    return gas


def authorizations(tx: Tx) -> list[tuple[str, int | None]]:
    """MD-5: each authorization tuple's authority, and the nonce it carries, or None for its authority's own."""
    return [(a, None) if isinstance(a, str) else (a[0], a[1]) for a in tx.authorities]


def authority_addresses(tx: Tx) -> list[str]:
    return [a for a, _ in authorizations(tx)]


def floor_data_gas(tx: Tx, floor_cost_per_token: int) -> int:
    """FEE-3, the EIP-7623 floor."""
    return INTRINSIC_BASE + floor_cost_per_token * TOKENS_PER_NONZERO_BYTE * tx.data_size


# --- frame transactions (type 6) ---------------------------------------------

DEFAULT_MODE, VERIFY_MODE, SENDER_MODE = 0, 1, 2
DEP_VERIFY_MODE = 3  # EIP-8288, `docs/spec/05-aggregation.md`
LEANSPHINCS, LEANSTARK = 0x10, 0x11
APPROVE_PAYMENT, APPROVE_EXECUTION, APPROVE_SCOPE_MASK = 0x1, 0x2, 0x3
ATOMIC_BATCH_FLAG = 0x4

FRAME_TX_INTRINSIC_COST = 12000
FRAME_TX_PER_FRAME_COST = 475
TX_VALUE_COST = 6000
STANDARD_TOKEN_COST = 4
TOTAL_COST_FLOOR_PER_TOKEN = 16
TX_MAX_GAS_LIMIT = 16_777_216
MAX_FRAMES = 64

SIGNATURE_GAS = {"secp256k1": 2800, "p256": 6700, "arbitrary": 100}
SIGNATURE_BYTES = {"secp256k1": 65, "p256": 128}


@dataclass(frozen=True)
class Signature:
    """MD-6."""

    scheme: str = "secp256k1"
    signer: str | None = None
    canonical_msg: bool = True
    valid: bool = True
    length: int = 0

    @property
    def data_bytes(self) -> int:
        signature = SIGNATURE_BYTES.get(self.scheme, self.length)
        return (20 if self.signer is not None else 0) + (0 if self.canonical_msg else 32) + signature

    @property
    def verify_gas(self) -> int:
        return SIGNATURE_GAS.get(self.scheme, 0)


@dataclass(frozen=True)
class Claim:
    """MD-6, CG-2: an admission claim for one slot in one epoch; `valid` says whether its issuer's signature verifies."""

    sender: str
    nonce_seq: int
    epoch: int
    nonce_keys: tuple[int, ...] = (0,)
    valid: bool = True
    salt: str = ""

    @property
    def slot(self) -> tuple:
        return (self.sender, self.nonce_keys, self.nonce_seq)


@dataclass(frozen=True, order=True)
class Dependency:
    """MD-6, AG-2: a (scheme, data_hash, verification_key_hash) triple; ordered as AG-5 sorts them."""

    scheme: int
    data_hash: str
    vk_hash: str


@dataclass(frozen=True)
class Frame:
    """MD-6: the EIP-8141 fields, then what a node simulating the frame would observe."""

    mode: int
    flags: int = 0
    target: str | None = None
    exec_gas: int = 0
    state_gas: int = 0
    value: int = 0
    data_size: int = 0
    approves: int | None = None
    reverts: bool = False
    opcodes: frozenset[str] = frozenset()
    reads: tuple[tuple, ...] = ()  # (address, slot, expected[, associated]), MD-6
    writes: tuple[tuple, ...] = ()  # (address, slot, value[, associated]), MD-6
    calls: tuple[str, ...] = ()
    installs_code: str | None = None
    deadline: int | None = None
    deps: tuple[Dependency, ...] = ()  # a dependency frame's triples (AG-2)
    roots: tuple[tuple[str, int, str], ...] = ()  # a recent root verifier frame's (source_id, slot, root) (RR-4)


def rlp_int_len(x: int) -> int:
    """FEE-4: the length of a canonical RLP integer; zero is the single byte 0x80."""
    return 1 if x < 128 else 1 + (x.bit_length() + 7) // 8


def rlp_list_len(payload: int) -> int:
    """FEE-4: the length of an RLP list whose items encode in `payload` bytes."""
    return 1 + payload if payload <= 55 else 1 + (payload.bit_length() + 7) // 8 + payload


def nonce_bytes(nonce_keys: tuple[int, ...], nonce_seq: int) -> int:
    """FEE-4's N: rlp(nonce_keys) || rlp(nonce_seq), EIP-8250 "Transaction payload"."""
    return rlp_list_len(sum(rlp_int_len(k) for k in nonce_keys)) + rlp_int_len(nonce_seq)


@dataclass(frozen=True)
class FrameGas:
    intrinsic: int
    floor: int
    max_gas: int


@dataclass(frozen=True, eq=False)
class FrameTx:
    """MD-6."""

    sender: str
    frames: tuple[Frame, ...]
    nonce_keys: tuple[int, ...] = (0,)
    nonce_seq: int = 0
    signatures: tuple[Signature, ...] = (Signature(),)
    max_fee: int = 100
    tip: int = 10
    size: int | None = None
    writes: tuple[tuple[str, int, int], ...] = ()
    gas_used: int | None = None
    label: str = ""
    root_writes: tuple[tuple[str, str, str], ...] = ()  # RR-3: (source_address, salt, root)
    claim: Claim | None = field(default=None, metadata={"omit_none": True})  # CG-2; absent, it leaves the hash as it was
    state_gas_used: int | None = field(default=None, metadata={"omit_none": True})  # MD-6; likewise
    zero_bytes: int | None = field(default=None, metadata={"omit_none": True})  # MD-6, FEE-4's Z; likewise
    verdict: str | None = field(default=None, metadata={"not_identity": True})  # MD-6, MD-7: a client's answer, not part of the tx
    type: int = field(default=FRAME, init=False)

    @property
    def slot(self) -> tuple:
        """CG-2: the place only one transaction fills."""
        return (self.sender, self.nonce_keys, self.nonce_seq)

    @cached_property
    def hash(self) -> str:
        return _hash(self)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, FrameTx) and other.hash == self.hash

    def __hash__(self) -> int:
        return hash(self.hash)

    @cached_property
    def data_bytes(self) -> int:
        """FEE-4's D: frame data, signature bytes and the nonce fields."""
        return (sum(f.data_size for f in self.frames) + sum(s.data_bytes for s in self.signatures)
                + nonce_bytes(self.nonce_keys, self.nonce_seq))

    @cached_property
    def gas(self) -> FrameGas:
        """FEE-4."""
        n = len(self.frames)
        sig_gas = sum(s.verify_gas for s in self.signatures)
        value_gas = TX_VALUE_COST * sum(
            1 for f in self.frames if f.value > 0 and f.target is not None and f.target != self.sender)
        fixed = FRAME_TX_INTRINSIC_COST + n * FRAME_TX_PER_FRAME_COST + sig_gas + value_gas
        zero = self.zero_bytes or 0  # a zero byte is one token, any other four; the floor counts four for each
        intrinsic = fixed + STANDARD_TOKEN_COST * (TOKENS_PER_NONZERO_BYTE * (self.data_bytes - zero) + zero)
        floor = fixed + TOTAL_COST_FLOOR_PER_TOKEN * TOKENS_PER_NONZERO_BYTE * self.data_bytes
        exec_sum = sum(f.exec_gas for f in self.frames)
        state_sum = sum(f.state_gas for f in self.frames)
        return FrameGas(intrinsic, floor, max(intrinsic + exec_sum + state_sum, floor + state_sum))

    @cached_property
    def dependencies(self) -> tuple[Dependency, ...]:
        """AG-4: the sorted, deduplicated triples of its dependency frames."""
        return tuple(sorted({d for f in self.frames for d in f.deps}))  # only a dependency frame has deps (MD-6)

    @cached_property
    def declared(self) -> int:
        """AG-8: how many triples its dependency frames declare, duplicates included."""
        return sum(len(f.deps) for f in self.frames)

    @property
    def max_gas(self) -> int:
        return self.gas.max_gas

    @property
    def max_cost(self) -> int:
        return self.max_gas * self.max_fee

    @property
    def cost(self) -> int:
        return self.max_cost

    @property
    def gas_limit(self) -> int:
        return self.max_gas

    @property
    def nonce(self) -> int:
        return self.nonce_seq

    @property
    def encoded_size(self) -> int:
        return self.size if self.size is not None else 200 + self.data_bytes

    @property
    def used(self) -> int:
        return self.max_gas if self.gas_used is None else self.gas_used

    @property
    def state_limit(self) -> int:
        """FEE-4: the frames' state limits, which `max_gas` counts."""
        return sum(f.state_gas for f in self.frames)

    @property
    def state_used(self) -> int:
        """MD-6: the part of `used` that is EIP-8037 state gas."""
        return self.state_limit if self.state_gas_used is None else self.state_gas_used

    def effective_tip(self, base_fee: int) -> int:
        return effective_tip(self.max_fee, self.tip, base_fee)

    def name(self) -> str:
        return self.label or self.hash[:10]


AnyTx = Tx | FrameTx


def replaces(old: AnyTx, new: AnyTx, price_bump: int) -> bool:
    """NP-11 (and FP-12): both fee fields rise strictly and reach the floored threshold."""
    if old.max_fee >= new.max_fee or old.tip >= new.tip:
        return False
    fee_threshold = (100 + price_bump) * old.max_fee // 100
    tip_threshold = (100 + price_bump) * old.tip // 100
    return new.max_fee >= fee_threshold and new.tip >= tip_threshold
