"""Recent roots: `docs/spec/08-recent-roots.md`, RR-3 to RR-6 (EIP-8272).

The EIP derives a source id, an entry and its storage key with keccak256 over
fixed-width encodings. Here they are injective functions of the same inputs,
which is the property the EIP uses the hashes for (RR-3, decision record 0023).
"""

from __future__ import annotations

import hashlib

from . import errors as E
from .errors import TxError
from .model import State
from .tx import VERIFY_MODE, Frame

TUPLE_BYTES = 72  # RECENT_ROOT_TUPLE_BYTES


def source_id(address: str, salt: str) -> str:
    """RR-3: the root source an address writes to with a salt."""
    return f"{address}/{salt}"


def _int(*parts) -> int:
    return int.from_bytes(hashlib.sha256("/".join(map(str, parts)).encode()).digest(), "big")


def storage_key(source: str, index: int) -> int:
    """RR-3: where index `index` of `source`'s ring buffer is stored at the contract."""
    return _int("RECENT_ROOT_STORAGE", source, index)


def entry(source: str, slot: int, root: str) -> int:
    """RR-3: what a write of `root` by `source` at `slot` stores."""
    return _int("RECENT_ROOT_ENTRY", source, slot, root)


def write_root(state: State, cfg, source: str, slot: int, root: str | None) -> None:
    """RR-3: the entry at index `slot` mod L becomes (source, slot, root); `root` None empties it."""
    storage = state.edit(cfg.recent_root_address).storage
    key = storage_key(source, slot % cfg.recent_root_length)
    if root is None:
        storage.pop(key, None)
    else:
        storage[key] = entry(source, slot, root)


def apply_writes(state: State, writes, slot: int, cfg) -> None:
    """RR-3: a transaction's `root_writes`, in a block at `slot`, under a profile with `recent_roots`."""
    if not cfg.recent_roots:
        return
    for address, salt, root in writes:
        write_root(state, cfg, source_id(address, salt), slot, root)


def is_verifier(frame: Frame, cfg) -> bool:
    """RR-4: whether `frame` is a `recent_root_verify` frame."""
    k = len(frame.roots)
    return (cfg.recent_roots and frame.mode == VERIFY_MODE and frame.target == cfg.recent_root_address
            and frame.flags == 0 and frame.value == 0 and frame.state_gas == 0
            and 1 <= k <= cfg.max_recent_root_references and frame.data_size == TUPLE_BYTES * k)


def check(frame: Frame, state: State, cfg, current_slot: int, margin: int, deps: dict) -> tuple[int, int]:
    """RR-5, recording RR-6's dependencies in `deps`. Returns the oldest and newest slot referenced."""
    address = cfg.recent_root_address
    code = state.code(address)
    deps[("code", address)] = code
    if code != cfg.recent_root_code:
        raise TxError(E.ErrFramePrefixReverted)
    usable = cfg.recent_root_length - 1
    for source, slot, root in frame.roots:
        if slot >= current_slot:
            raise TxError(E.ErrFrameRootFuture)
        if current_slot - slot > usable - margin:
            raise TxError(E.ErrFrameRootExpired)
        key = storage_key(source, slot % cfg.recent_root_length)
        held = state.storage(address, key)
        deps[("storage", address, key)] = held
        if held != entry(source, slot, root):
            raise TxError(E.ErrFrameRootUnknown)
    if frame.reverts:
        raise TxError(E.ErrFramePrefixReverted)
    slots = [slot for _, slot, _ in frame.roots]
    return min(slots), max(slots)
