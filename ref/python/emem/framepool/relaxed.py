"""`docs/spec/15-relaxed-mempool.md`: RM-1's declarations, and the reads, relaxations and reputation states that
RM-3 to RM-6 read from them. The pool's rules themselves are in `pool.py`."""

from __future__ import annotations

from ..model import is_delegation
from .config import FramePoolConfig

RELAXABLE = ("ErrFrameStorageReadNonSender", "ErrFramePaymasterBusy", "ErrFrameSenderBusy")  # RM-2
ACTIVE, THROTTLED, BANNED = "ACTIVE", "THROTTLED", "BANNED"  # RM-6


def declaration(cfg: FramePoolConfig, code: str) -> tuple | None:
    """RM-1: the declaration for `code`, or None. Empty code and an EIP-7702 delegation have none."""
    if not code or is_delegation(code):
        return None
    for d in cfg.declarations:
        if d[0] == code:
            return d
    return None


def declares(cfg: FramePoolConfig, code: str, slot: int) -> bool:
    """RM-1: whether `code` declares `slot` write-once."""
    d = declaration(cfg, code)
    return d is not None and any(first <= slot < first + count for first, count in d[1])


def state_of(violations: int, cfg: FramePoolConfig) -> str:
    """RM-6: a declared code's state from its count of violations."""
    if violations >= cfg.ban_violations:
        return BANNED
    if violations >= 1:
        return THROTTLED
    return ACTIVE
