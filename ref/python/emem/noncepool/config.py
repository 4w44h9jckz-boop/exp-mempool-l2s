"""NP-1: the `geth` profile."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class NoncePoolConfig:
    price_limit: int = 1
    price_bump: int = 10
    account_slots: int = 16
    global_slots: int = 4096 + 1024
    account_queue: int = 64
    global_queue: int = 1024
    lifetime: float = 3 * 3600
    eviction_interval: float = 60
    max_size: int = 4 * 32 * 1024
    slot_size: int = 32 * 1024
    max_tx_gas: int | None = 16_777_216
    max_initcode_size: int = 49152
    floor_cost_per_token: int = 10

    def with_(self, **changes) -> NoncePoolConfig:
        return replace(self, **changes)


GETH = NoncePoolConfig()
