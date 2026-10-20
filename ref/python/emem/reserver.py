"""The shared reservation tracker of NP-8 and FP-13: a sender lives in one subpool at a time.

go-ethereum `core/txpool/reserver.go`.
"""

from __future__ import annotations


class Reserver:
    def __init__(self) -> None:
        self._owner: dict[str, object] = {}

    def hold(self, addr: str, pool: object) -> bool:
        """Take `addr` for `pool`. False if another subpool holds it."""
        owner = self._owner.get(addr)
        if owner is not None and owner is not pool:
            return False
        self._owner[addr] = pool
        return True

    def release(self, addr: str, pool: object) -> None:
        if self._owner.get(addr) is pool:
            del self._owner[addr]

    def held_by_other(self, addr: str, pool: object) -> bool:
        owner = self._owner.get(addr)
        return owner is not None and owner is not pool
