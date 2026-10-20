"""MD-11: the three subpools behind one reservation tracker."""

from __future__ import annotations

import itertools

from .framepool.config import EIP_8141, FramePoolConfig
from .framepool.erc8421 import StandardPool
from .framepool.pool import FramePool
from .model import Head, State
from .noncepool.config import GETH, NoncePoolConfig
from .noncepool.pool import NoncePool
from .reserver import Reserver
from .sealed import OFF, SealedPoolConfig, SealedTx
from .sealedpool import SealedPool
from .tx import AnyTx, FrameTx


class TxPool:
    def __init__(self, head: Head, state: State, nonce_config: NoncePoolConfig = GETH,
                 frame_config: FramePoolConfig = EIP_8141, now: float = 0,
                 sealed_config: SealedPoolConfig = OFF):
        self.head = head
        self.state = state
        self.reserver = Reserver()
        sequence = itertools.count().__next__  # one arrival order across the subpools
        self.nonce = NoncePool(head, state, nonce_config, self.reserver, now, sequence)
        pool = StandardPool if frame_config.ruleset == "erc-8421" else FramePool  # 14-erc-8421.md
        self.frame = pool(head, state, frame_config, self.reserver, now, sequence)
        self.sealed = SealedPool(head, state, sealed_config, self.reserver, now, sequence)

    def add(self, txs: list[AnyTx], now: float = 0) -> list[str]:
        """Each subpool gets its share in order, the account-nonce pool's first and the sealed pool's last."""
        self.nonce.tick(now)
        results: list[str] = [""] * len(txs)
        frames = [i for i, tx in enumerate(txs) if isinstance(tx, FrameTx)]
        sealed = [i for i, tx in enumerate(txs) if isinstance(tx, SealedTx)]
        others = set(frames) | set(sealed)
        plain = [i for i in range(len(txs)) if i not in others]
        for share, pool in ((plain, self.nonce), (frames, self.frame), (sealed, self.sealed)):
            if share:
                for i, r in zip(share, pool.add([txs[i] for i in share], now)):
                    results[i] = r
        return results

    def reset(self, head: Head, state: State, now: float = 0, verdicts: dict[str, str] | None = None) -> None:
        """MD-8; `verdicts` maps a pending frame transaction's hash to its client's verdict at `head`."""
        self.head, self.state = head, state
        self.nonce.reset(head, state, now)
        self.frame.reset(head, state, now, verdicts)
        self.sealed.reset(head, state, now)

    def tick(self, now: float) -> None:
        self.nonce.tick(now)
        self.frame.tick(now)
        self.sealed.tick(now)

    def finalize(self, blocks: list[tuple[int, dict[str, int]]], now: float = 0) -> None:
        """MD-8: only the frame pool keeps anything from finality, and only under `matcha`."""
        self.frame.finalize(blocks, now)

    def content(self) -> tuple[dict[str, list[AnyTx]], dict[str, list[AnyTx]]]:
        pending, queued = self.nonce.content()
        merged: dict[str, list[AnyTx]] = {s: list(txs) for s, txs in pending.items()}
        for pool in (self.frame, self.sealed):
            for sender, txs in pool.content().items():
                merged.setdefault(sender, []).extend(txs)
        return merged, dict(queued)

    def status(self, tx_hash: str) -> str:
        for pool in (self.nonce, self.frame, self.sealed):
            status = pool.status(tx_hash)
            if status != "unknown":
                return status
        return "unknown"

    def get(self, tx_hash: str) -> AnyTx | SealedTx | None:
        tx = self.nonce.all.get(tx_hash)
        if tx is None and tx_hash in self.frame.entries:
            tx = self.frame.entries[tx_hash].tx
        return tx if tx is not None else self.sealed.get(tx_hash)

    def arrival(self, tx: AnyTx) -> int:
        if isinstance(tx, FrameTx):
            return self.frame.arrival(tx.hash)
        if isinstance(tx, SealedTx):
            return self.sealed.arrival(tx.hash)
        return self.nonce.arrival.get(tx.hash, 0)

    def __len__(self) -> int:
        return len(self.nonce.all) + len(self.frame.entries) + len(self.sealed.entries)
