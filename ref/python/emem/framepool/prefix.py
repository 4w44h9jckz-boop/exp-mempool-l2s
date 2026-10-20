"""The validation prefix: static checks and simulation, `docs/spec/02-frame-pool.md` FP-3 to FP-10,
with the dependency frames of `05-aggregation.md` (AG-2 to AG-4) and the recent root verifier frame of
`08-recent-roots.md` (RR-4, RR-5) under a profile that admits them.

Nothing here runs the EVM. A frame carries what a node simulating it would
observe (MD-6), and these functions apply the EIP-8141 rules to those
observations. Decision record 0003.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .. import errors as E
from .. import recentroots
from ..dependencies import check_frame, check_limits
from ..errors import TxError
from ..model import Head, State, is_delegation
from ..tx import (APPROVE_EXECUTION, APPROVE_PAYMENT, APPROVE_SCOPE_MASK, ATOMIC_BATCH_FLAG, DEFAULT_MODE,
                  MAX_FRAMES, SENDER_MODE, SIGNATURE_GAS, TX_MAX_GAS_LIMIT, VERIFY_MODE, Frame,
                  FrameTx)
from .config import FramePoolConfig

EXPIRY, DEPLOY, SELF_VERIFY, ONLY_VERIFY, PAY, OTHER = (
    "expiry_verify", "deploy", "self_verify", "only_verify", "pay", "other")
ROOT = "recent_root_verify"  # RR-4

RECOGNIZED = {
    (SELF_VERIFY,),
    (DEPLOY, SELF_VERIFY),
    (ONLY_VERIFY, PAY),
    (DEPLOY, ONLY_VERIFY, PAY),
}

BANNED_OPCODES = frozenset({
    "GASPRICE", "BLOCKHASH", "COINBASE", "TIMESTAMP", "NUMBER", "PREVRANDAO", "GASLIMIT", "BASEFEE",
    "BLOBBASEFEE", "SLOTNUM", "GAS", "INVALID", "SELFDESTRUCT", "BALANCE", "SELFBALANCE",
    "CREATE", "CREATE2", "SETDELEGATE", "SSTORE",
})
ALLOWED_IN_DEPLOY = frozenset({"CREATE", "CREATE2", "SETDELEGATE", "SSTORE"})


def _fail(code: str):
    raise TxError(code)


@dataclass(frozen=True)
class Prefix:
    """FP-4: the prefix's length, the classification (FP-5) of its frames, its frames and those after it.

    The frames are the transaction's without its dependency frames (AG-3), so
    `length` counts those the prefix runs.
    """

    length: int
    kinds: tuple[str, ...]
    frames: tuple[Frame, ...] = ()
    rest: tuple[Frame, ...] = ()


@dataclass
class Simulation:
    """FP-10: who pays, in which class, and what the prefix depends on."""

    payer: str
    payer_class: str
    deps: dict[tuple, object]
    deadline: int | None
    roots: tuple[int, int] | None = None  # RR-6: the oldest and newest slot its verifier frame references
    verdict: str | None = None  # FP-10: the client's verdict it was judged by, a dependency of its own


def classify(frame: Frame, sender: str, cfg: FramePoolConfig) -> str:
    """FP-5's frame classes, with RR-4's."""
    if frame.mode == VERIFY_MODE and frame.target == cfg.expiry_verifier:
        return EXPIRY
    if cfg.recent_roots and recentroots.is_verifier(frame, cfg):
        return ROOT
    if frame.mode == DEFAULT_MODE and frame.flags & APPROVE_SCOPE_MASK == 0:
        return DEPLOY
    if frame.mode == VERIFY_MODE and frame.target in (None, sender):
        if frame.flags == 0x3:
            return SELF_VERIFY
        if frame.flags == 0x2:
            return ONLY_VERIFY
    if frame.mode == VERIFY_MODE and frame.flags == 0x1:
        return PAY
    return OTHER


def executed(tx: FrameTx, cfg: FramePoolConfig) -> tuple[Frame, ...]:
    """AG-3: the frames FP-4 to FP-6 see, which are all of them unless the profile admits dependency frames."""
    if not cfg.dependency_frames:
        return tx.frames
    return tuple(f for f in tx.frames if f.mode != cfg.dep_frame_mode)


def analyse(tx: FrameTx, cfg: FramePoolConfig) -> Prefix | None:
    """FP-4: the frames up to and including the first that carries APPROVE_PAYMENT."""
    frames = executed(tx, cfg)
    for i, frame in enumerate(frames):
        if frame.flags & APPROVE_PAYMENT:
            return Prefix(i + 1, tuple(classify(f, tx.sender, cfg) for f in frames[:i + 1]),
                          frames[:i + 1], frames[i + 1:])
    return None


def check_static(tx: FrameTx, head: Head, cfg: FramePoolConfig) -> Prefix:
    """FP-3, FP-5 and FP-6: everything decidable without state.

    A pure function of the transaction, the head's gas limit and the profile,
    so its answer is remembered: every node of a simulation asks it about the
    same transactions.
    """
    result = _check_static(tx, head.gas_limit, cfg)
    if isinstance(result, str):
        raise TxError(result)
    return result


@lru_cache(maxsize=1 << 16)
def _check_static(tx: FrameTx, gas_limit: int, cfg: FramePoolConfig) -> Prefix | str:
    try:
        return _static(tx, gas_limit, cfg)
    except TxError as err:
        return err.code


def check_fp3(tx: FrameTx, gas_limit: int, cfg: FramePoolConfig) -> None:
    """FP-3: the EIP's static constraints, with EN-3's and AG-2's under a profile that admits them."""
    frames, sender = tx.frames, tx.sender
    if not 1 <= len(frames) <= MAX_FRAMES:
        _fail(E.ErrFrameMalformed)
    keys = tx.nonce_keys
    if not keys or any(k < 0 for k in keys) or any(a >= b for a, b in zip(keys, keys[1:])):
        _fail(E.ErrFrameMalformed)
    if not 0 <= tx.nonce_seq < 2**64:
        _fail(E.ErrFrameMalformed)
    if cfg.expiring and cfg.expiring_key in keys and (len(keys) > 1 or tx.nonce_seq):  # EN-3
        _fail(E.ErrFrameMalformed)
    expiry_frames = 0
    for i, f in enumerate(frames):
        if f.mode == cfg.dep_frame_mode and cfg.dependency_frames:  # AG-2 in place of the rules below
            check_frame(f, cfg)
            if not cfg.dep_in_batch and i and frames[i - 1].flags & ATOMIC_BATCH_FLAG:
                _fail(E.ErrDepFrameMalformed)
            continue
        if f.mode not in (DEFAULT_MODE, VERIFY_MODE, SENDER_MODE) or not 0 <= f.flags < 8:
            _fail(E.ErrFrameMalformed)
        if f.value < 0 or f.exec_gas < 0 or f.state_gas < 0 or (f.value and f.mode != SENDER_MODE):
            _fail(E.ErrFrameMalformed)
        if f.flags & APPROVE_EXECUTION and f.target not in (None, sender):
            _fail(E.ErrFrameMalformed)
        if f.flags & ATOMIC_BATCH_FLAG:
            if f.mode == VERIFY_MODE or i + 1 >= len(frames) or frames[i + 1].mode == VERIFY_MODE:
                _fail(E.ErrFrameMalformed)
        in_batch = f.flags & ATOMIC_BATCH_FLAG or (i > 0 and frames[i - 1].flags & ATOMIC_BATCH_FLAG)
        if in_batch and f.flags & APPROVE_SCOPE_MASK:
            _fail(E.ErrFrameMalformed)
        if f.mode == VERIFY_MODE and f.target == cfg.expiry_verifier:
            expiry_frames += 1
            if f.flags or f.value or f.state_gas or f.data_size != 8 or f.deadline is None:
                _fail(E.ErrFrameMalformed)
    if expiry_frames > 1 or any(s.scheme not in SIGNATURE_GAS for s in tx.signatures):
        _fail(E.ErrFrameMalformed)
    gas = tx.gas
    if max(gas.intrinsic + sum(f.exec_gas for f in frames), gas.floor) > TX_MAX_GAS_LIMIT:
        _fail(E.ErrGasLimitTooHigh)
    if any(not s.valid for s in tx.signatures):
        _fail(E.ErrInvalidSender)
    if tx.tip > tx.max_fee:
        _fail(E.ErrTipAboveFeeCap)
    if tx.tip < cfg.price_limit:
        _fail(E.ErrTxGasPriceTooLow)
    if gas.max_gas > gas_limit:
        _fail(E.ErrGasLimit)


def _static(tx: FrameTx, gas_limit: int, cfg: FramePoolConfig) -> Prefix:
    sender = tx.sender
    check_fp3(tx, gas_limit, cfg)

    # AG-4: limits per transaction
    if cfg.dependency_frames:
        check_limits(tx, cfg)

    # FP-5: structure, over the frames AG-3 leaves
    kinds = [classify(f, sender, cfg) for f in executed(tx, cfg)]
    if any(k == EXPIRY for k in kinds[1:]):
        _fail(E.ErrFrameExpiryNotFirst)
    roots = [i for i, k in enumerate(kinds) if k == ROOT]  # RR-4: at most one, first after an expiry frame
    if len(roots) > 1 or (roots and roots[0] != (1 if kinds[0] == EXPIRY else 0)):
        _fail(E.ErrFrameRootPosition)
    prefix = analyse(tx, cfg)
    if prefix is None:
        _fail(E.ErrFrameNoPayer)
    prefix_frames = prefix.frames
    if any(f.flags & ATOMIC_BATCH_FLAG for f in prefix_frames):
        _fail(E.ErrFrameAtomicInPrefix)
    shape = prefix.kinds[1:] if prefix.kinds[0] == EXPIRY else prefix.kinds
    shape = shape[1:] if shape[:1] == (ROOT,) else shape  # RR-4
    if shape not in RECOGNIZED:
        _fail(E.ErrFrameUnrecognizedPrefix)
    if any(f.mode == VERIFY_MODE for f in prefix.rest):
        _fail(E.ErrFrameVerifyAfterPrefix)

    # FP-6: budgets
    if sum(f.exec_gas for f in prefix_frames) + sum(s.verify_gas for s in tx.signatures) > cfg.max_verify_gas:
        _fail(E.ErrFrameVerifyGas)
    if cfg.max_verify_state_gas is not None and sum(f.state_gas for f in prefix_frames) > cfg.max_verify_state_gas:
        _fail(E.ErrFrameVerifyStateGas)
    return prefix


def check_trace(frame: Frame, sender: str, deploy: bool, state: State, cfg: FramePoolConfig) -> None:
    """FP-9, in the order the clause lists the rules."""
    for op in frame.opcodes:
        if op in BANNED_OPCODES and not (deploy and op in ALLOWED_IN_DEPLOY):
            _fail(E.ErrFrameBannedOpcode)
    for addr, *_ in frame.writes:
        if not (deploy and addr == sender):
            _fail(E.ErrFrameStateWrite)
    for addr, *_ in frame.reads:
        if addr != sender:
            _fail(E.ErrFrameStorageReadNonSender)
    for addr in frame.calls:
        if addr == sender or addr in cfg.precompiles:
            continue
        code = state.code(addr)
        if code == "" or is_delegation(code):
            _fail(E.ErrFrameCallTarget)


def default_code_approves(tx: FrameTx, scope: int, target: str) -> bool:
    """FP-8: the default code's signature lookup (EIP-8141, Default code)."""
    index = 0 if scope & APPROVE_EXECUTION else 1
    if index >= len(tx.signatures):
        return False
    sig = tx.signatures[index]
    signer = sig.signer if sig.signer is not None else tx.sender
    return sig.scheme == "secp256k1" and sig.valid and sig.canonical_msg and signer == target


def expiring(tx: FrameTx, cfg: FramePoolConfig) -> bool:
    """EN-3: whether `tx` is in expiring-nonce mode."""
    return cfg.expiring and tx.nonce_keys == (cfg.expiring_key,)


def seen_slot(tx_hash: str) -> int:
    """EN-2: the storage slot at `nonce_ring` that holds seen(h), the hash read as an integer."""
    return int(tx_hash, 16)


def check_expiring(tx: FrameTx, prefix: Prefix, state: State, cfg: FramePoolConfig, now: int) -> None:
    """EN-4, in FP-7's place, with `now` the pool's head timestamp plus its margin, or a block's timestamp."""
    deadlines = [f.deadline for f, k in zip(prefix.frames, prefix.kinds) if k == EXPIRY]
    if not deadlines:
        _fail(E.ErrFrameExpiryMissing)
    d = deadlines[0]
    if d < now:
        _fail(E.ErrFrameExpired)
    if d > now + cfg.max_expiry_secs:
        _fail(E.ErrFrameExpiryTooFar)
    if state.storage(cfg.nonce_ring, seen_slot(tx.hash)) >= now:
        _fail(E.ErrNonceTooLow)


def check_nonce(tx: FrameTx, state: State) -> list[int]:
    """FP-7: exact nonce sequences; returns the sender's sequence for each key."""
    seqs = [state.nonce_seq(tx.sender, k) for k in tx.nonce_keys]
    if any(s > tx.nonce_seq for s in seqs):
        _fail(E.ErrNonceTooLow)
    if any(s < tx.nonce_seq for s in seqs):
        _fail(E.ErrNonceTooHigh)
    return seqs


def classify_payer(payer: str, code: str, sender: str, cfg: FramePoolConfig) -> str:
    """FP-10: the payer's class, from its code."""
    if payer == sender:
        return "sender"
    if code == cfg.canonical_paymaster_code:
        return "canonical"
    if code == "":
        return "default"
    return "noncanonical"


def static_payer(tx: FrameTx, prefix: Prefix, state: State, cfg: FramePoolConfig) -> tuple[str, str]:
    """Admission under `static_first`: the payer and class FP-10 gives, read from the prefix's shape.

    The payer is the resolved target of the prefix's last frame, the one with
    `APPROVE_PAYMENT` (FP-4). No prefix frame installs code anywhere but at
    `sender`, whose class is `sender` whatever its code.
    """
    last = prefix.frames[-1]
    payer = last.target if last.target is not None else tx.sender
    return payer, classify_payer(payer, state.code(payer), tx.sender, cfg)


def simulate(tx: FrameTx, prefix: Prefix, head: Head, state: State, cfg: FramePoolConfig,
             expiry_margin: int = 0, slot: int | None = None, root_margin: int = 0) -> Simulation:
    """FP-7 to FP-10, with RR-5; a pool passes its `expiry_margin` (FP-8), its current slot, which is its
    head's plus one, and its `root_margin` (RR-2, RR-5); a block being built passes none, and its own slot is
    the current one (RR-8)."""
    sender = tx.sender
    mode = expiring(tx, cfg)
    if mode:  # EN-4 in place of FP-7; seen(h) is a dependency, so a pool looks again when it changes (EN-6)
        check_expiring(tx, prefix, state, cfg, head.timestamp + expiry_margin)
        seen = seen_slot(tx.hash)
        deps: dict[tuple, object] = {("storage", cfg.nonce_ring, seen): state.storage(cfg.nonce_ring, seen)}
    else:
        seqs = check_nonce(tx, state)  # FP-7
        deps = {("nonce_seq", sender, k): s for k, s in zip(tx.nonce_keys, seqs)}
    deps[("code", sender)] = state.code(sender)
    deps[("balance", sender)] = state.balance(sender)
    if tx.verdict is not None:
        return _by_verdict(tx, prefix, state, cfg, deps)

    # FP-8: the prefix, frame by frame
    sender_code = state.code(sender)
    deployed_storage: dict[int, int] = {}
    deadline = roots = None
    payer = payer_code = None
    for frame, kind in zip(prefix.frames, prefix.kinds):
        if kind == ROOT:  # RR-5, evaluated directly
            roots = recentroots.check(frame, state, cfg, head.slot if slot is None else slot, root_margin, deps)
            continue
        if kind == EXPIRY:
            code = state.code(cfg.expiry_verifier)
            deps[("code", cfg.expiry_verifier)] = code
            if code != cfg.expiry_verifier_code:
                _fail(E.ErrFramePrefixReverted)
            deadline = frame.deadline
            if frame.deadline < head.timestamp + expiry_margin:
                _fail(E.ErrFrameExpired)
            continue
        target = frame.target if frame.target is not None else sender
        code = sender_code if target == sender else state.code(target)
        for addr, slot, *_ in frame.reads:
            if addr == sender:
                deps[("storage", sender, slot)] = state.storage(sender, slot)
        if kind == DEPLOY:
            deps[("code", target)] = code
            check_trace(frame, sender, True, state, cfg)
            if frame.reverts:
                _fail(E.ErrFramePrefixReverted)
            if code == "" or frame.installs_code is None or sender_code != "":
                _fail(E.ErrFrameDeployNoCode)
            sender_code = frame.installs_code
            deployed_storage.update({slot: value for addr, slot, value, *_ in frame.writes if addr == sender})
            continue
        scope = frame.flags & APPROVE_SCOPE_MASK
        if code == "":
            if not default_code_approves(tx, scope, target):
                _fail(E.ErrFramePrefixReverted)
        else:
            if not (kind == PAY and code == cfg.canonical_paymaster_code):
                check_trace(frame, sender, False, state, cfg)
            for addr, slot, expected, *_ in frame.reads:
                if addr == sender and slot in deployed_storage:
                    value = deployed_storage[slot]
                else:
                    value = state.storage(addr, slot)
                if expected is not None and value != expected:
                    _fail(E.ErrFramePrefixReverted)
            if frame.reverts:
                _fail(E.ErrFramePrefixReverted)
            if frame.approves != scope:
                _fail(E.ErrFrameMissingApprove)
        if scope & APPROVE_PAYMENT:
            if state.balance(target) < tx.max_cost:
                _fail(E.ErrInsufficientFunds)
            if mode and frame.exec_gas < cfg.expiring_nonce_gas:  # EN-5: APPROVE would halt out of gas
                _fail(E.ErrFramePrefixReverted)
            payer, payer_code = target, code

    # FP-10: the payer's class and its dependencies
    assert payer is not None  # check_static guarantees a payment frame
    payer_class = classify_payer(payer, payer_code, sender, cfg)
    deps[("balance", payer)] = state.balance(payer)
    deps[("code", payer)] = state.code(payer)
    if payer_class == "canonical":
        deps[("withdrawal", payer)] = state.withdrawal(payer)
    return Simulation(payer, payer_class, deps, deadline, roots)


def _by_verdict(tx: FrameTx, prefix: Prefix, state: State, cfg: FramePoolConfig,
                deps: dict[tuple, object]) -> Simulation:
    """FP-8 and FP-9 through a client's verdict, then FP-8's payment check and FP-10.

    The verdict stands for every prefix frame, so no observation is read; the
    payer is the one the prefix's shape names, as under `static_first`; the
    slots the prefix read are unknown, and the verdict is recorded in their place.
    """
    deadline = roots = None
    for frame, kind in zip(prefix.frames, prefix.kinds):
        if kind == EXPIRY:
            deps[("code", cfg.expiry_verifier)] = state.code(cfg.expiry_verifier)
            deadline = frame.deadline
        elif kind == ROOT:  # RR-6: the tuples' slots, read from the transaction, for RR-7
            slots = [slot for _, slot, _ in frame.roots]
            roots = (min(slots), max(slots))
    if tx.verdict != E.OK:
        _fail(tx.verdict)
    payer, payer_class = static_payer(tx, prefix, state, cfg)
    if state.balance(payer) < tx.max_cost:
        _fail(E.ErrInsufficientFunds)
    deps[("balance", payer)] = state.balance(payer)
    deps[("code", payer)] = state.code(payer)
    if payer_class == "canonical":
        deps[("withdrawal", payer)] = state.withdrawal(payer)
    return Simulation(payer, payer_class, deps, deadline, roots, tx.verdict)


def dep_value(state: State, key: tuple) -> object:
    kind = key[0]
    if kind == "nonce_seq":
        return state.nonce_seq(key[1], key[2])
    if kind == "code":
        return state.code(key[1])
    if kind == "balance":
        return state.balance(key[1])
    if kind == "storage":
        return state.storage(key[1], key[2])
    if kind == "withdrawal":
        return state.withdrawal(key[1])
    if kind == "stake":  # 14-erc-8421.md, AM-14
        return state.stake(key[1])
    raise ValueError(key)
