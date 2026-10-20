"""MATCHA's charge: `docs/spec/04-matcha.md`, MA-2."""

from __future__ import annotations

import math
from fractions import Fraction

from ..tx import TX_VALUE_COST, FrameTx
from .prefix import Prefix


def admission_gas(tx: FrameTx, prefix: Prefix) -> int:
    """FEE-4's intrinsic gas without the value-transfer term, plus the prefix's declared execution limits."""
    value_frames = sum(1 for f in tx.frames if f.value > 0 and f.target is not None and f.target != tx.sender)
    return tx.gas.intrinsic - TX_VALUE_COST * value_frames + sum(f.exec_gas for f in prefix.frames)


def charge(tx: FrameTx, prefix: Prefix, safety_factor: int | float) -> int:
    """ceil(safety_factor * admission_gas), exactly: the factor is read as the decimal it is written as."""
    return math.ceil(Fraction(str(safety_factor)) * admission_gas(tx, prefix))
