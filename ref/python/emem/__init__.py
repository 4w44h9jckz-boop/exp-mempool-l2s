"""emem: the reference implementation of `docs/spec/`.

Standard library only, written for a reader. The specification is normative;
this code exists to show it is implementable and unambiguous.
"""

from .aggregation import Aggregator, Stark, Wrapper, wrap
from .block import Block, Commitment, apply_tx, build_block
from .errors import OK, TxError
from .focil import EIP_7805, EIP_8369, FOCIL_PROFILES, FocilConfig, build_il, omission
from .framepool.config import (CLAIM_GATED, EIP_8141, EIP_8266, EIP_8272, EIP_8288, HEGOTA_TESTNET, MATCHA,
                               PROFILES, FramePoolConfig)
from .framepool.pool import FramePool
from .model import Account, Head, State, effective_tip, next_base_fee
from .noncepool.config import GETH, NoncePoolConfig
from .noncepool.pool import NoncePool
from .sealed import EIP_8184, SEALED_PROFILES, SealedPoolConfig, SealedTx
from .sealedpool import SealedPool
from .tx import Claim, Dependency, FrameTx, Frame, Signature, Tx, floor_data_gas, intrinsic_gas
from .txpool import TxPool

__all__ = [
    "Account", "Aggregator", "Block", "CLAIM_GATED", "Claim", "Commitment", "Dependency", "EIP_7805", "EIP_8141", "EIP_8184", "EIP_8266",
    "EIP_8272", "EIP_8288",
    "EIP_8369", "FOCIL_PROFILES", "FocilConfig", "Frame", "FramePool", "FramePoolConfig", "FrameTx", "GETH",
    "HEGOTA_TESTNET", "Head", "MATCHA", "NoncePool", "NoncePoolConfig", "OK", "PROFILES", "SEALED_PROFILES", "SealedPool", "SealedPoolConfig", "SealedTx",
    "Signature", "Stark", "State", "Tx", "TxError", "TxPool", "Wrapper", "apply_tx", "build_block", "build_il",
    "effective_tip", "floor_data_gas", "intrinsic_gas", "next_base_fee", "omission", "wrap",
]
