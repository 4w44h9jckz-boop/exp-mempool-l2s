"""Replay: a profile's verdict on a transaction a chain mined (`docs/spec/12-replay.md`, RP-1 to RP-6)."""

from __future__ import annotations

from dataclasses import replace
from itertools import combinations

from . import errors as E
from .errors import TxError
from .framepool.config import FramePoolConfig
from .framepool.prefix import check_static
from .model import Head
from .surface import SurfaceConfig, decode, tx_hash
from .tx import FrameTx

RECENT_ROOT_VERIFIER = "0x0000000000000000000000000000000000008272"
TESTNET_EXPIRY_VERIFIER = "0x0000000000000000000000000000000000008141"
NO_HEADER_GAS_LIMIT = 1 << 256  # RP-3: without a header, no max_gas is above the head's gas limit


def _same(tx: FrameTx) -> FrameTx:
    return tx


def _without_recent_root_frames(tx: FrameTx) -> FrameTx:
    return replace(tx, frames=tuple(f for f in tx.frames if f.target != RECENT_ROOT_VERIFIER))


DIFFERENCES = {  # RP-5, in its order: a change to the profile, and one to the transaction
    "max_verify_gas": (dict(max_verify_gas=500_000), _same),
    "max_verify_state_gas": (dict(max_verify_state_gas=None), _same),
    "expiry_verifier": (dict(expiry_verifier=TESTNET_EXPIRY_VERIFIER), _same),
    "recent-roots": ({}, _without_recent_root_frames),
}


def judge(tx: FrameTx, head: Head, cfg: FramePoolConfig) -> tuple[str, str | None]:
    """RP-3 after SF-2 and SF-3: FP-3 to FP-6, and FP-10's payer from the prefix's shape."""
    try:
        prefix = check_static(tx, head, cfg)
    except TxError as err:
        return err.code, None
    last = prefix.frames[-1]
    return E.OK, last.target if last.target is not None else tx.sender


def replay(raw: bytes, fixture_hash: str, receipt_payer: str, parent: dict | None,
           cfg: FramePoolConfig, surface: SurfaceConfig) -> dict:
    """RP-1 to RP-4 for one fixture under one profile."""
    if tx_hash(raw) != fixture_hash.lower():
        return {"comparison": "not replayed"}
    header = "read" if parent is not None else "missing"
    p = parent or {"number": 0, "timestamp": 0, "gas_used": 0, "base_fee": 0}
    head = Head(number=p["number"], timestamp=p["timestamp"],
                gas_limit=p.get("gas_limit", NO_HEADER_GAS_LIMIT) if parent is not None else NO_HEADER_GAS_LIMIT,
                gas_used=p["gas_used"], base_fee=p["base_fee"])

    def verdict_with(names: tuple[str, ...]) -> tuple[str, str | None]:
        c = cfg.with_(**{k: v for n in names for k, v in DIFFERENCES[n][0].items()})
        try:
            tx = decode(raw, c, surface)  # SF-3 reads deadlines against the profile's expiry verifier
        except TxError as err:
            return err.code, None
        for n in names:
            tx = DIFFERENCES[n][1](tx)
        return judge(tx, head, c)

    verdict, payer = verdict_with(())
    out = {"verdict": verdict, "header": header, "differences": []}
    if verdict == E.OK:
        out["payer"] = payer
        out["comparison"] = "agree" if payer == receipt_payer.lower() else "disagree"
        return out
    for k in (1, 2):
        for names in combinations(DIFFERENCES, k):
            if verdict_with(names)[0] == E.OK:
                out.update(comparison="explained", differences=list(names))
                return out
    out["comparison"] = "disagree"
    return out
