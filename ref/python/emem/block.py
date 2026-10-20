"""Block building and the model's state transition: `docs/spec/03-block-building.md`, BB-6's two dimensions and BB-7's
builders that drop what reverts included, with
AG-8 of `05-aggregation.md`, LU-12 and LU-13 of `06-lucid.md`, IL-7 of `07-focil.md`, and RR-2, RR-3 and
RR-8 of `08-recent-roots.md`."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Callable

from . import errors as E
from .dependencies import block_gas
from .errors import TxError
from .focil import OFF as FOCIL_OFF
from .focil import FocilConfig, admitted, delivered_order, valid_at_end
from .framepool.config import FramePoolConfig
from .framepool.prefix import DEPLOY, analyse, expiring, seen_slot, simulate
from .model import Head, State, delegation_to, is_delegation
from .recentroots import apply_writes
from .sealed import SealedTx, fees, select
from .tx import SENDER_MODE, SET_CODE, AnyTx, FrameTx, Tx, authorizations

MIN_TX_GAS = 21000
MIN_TX_GAS_TWO = 12000  # BB-6: go-ethereum's TxBaseCost2780 under Amsterdam
TX_MAX_EXEC_RESERVATION = 1 << 24  # BB-6: EIP-7825's cap on an account-nonce transaction's execution reservation
ONE, TWO = "one", "two"
DEFAULT_MIN_TIP = 1_000_000  # go-ethereum miner GasPrice, params.GWei / 1000
SLOT_TIME = 12


@dataclass(frozen=True)
class Commitment:
    """LU-12: a sealed transaction a block committed to, and the ToB fee its ticket paid."""

    tx: SealedTx
    tob: int


@dataclass
class GasPool:
    """The gas a block has left: BB-3 and BB-4's single sum under `one`, BB-6's execution and state sums
    under `two`."""

    limit: int
    dimensions: str = ONE
    execution: int = 0  # under `one`, the single sum
    state: int = 0

    def __post_init__(self):
        if self.dimensions not in (ONE, TWO):
            raise ValueError(self.dimensions)

    @property
    def left(self) -> int:
        """Under `one`, the gas left; under `two`, the smaller room."""
        if self.dimensions == ONE:
            return self.limit - self.execution
        return min(self.limit - self.execution, self.limit - self.state)

    @property
    def used(self) -> int:
        """BB-4's `gas_used`, or BB-6's larger sum."""
        return self.execution if self.dimensions == ONE else max(self.execution, self.state)

    def more(self) -> bool:
        """BB-3's loop condition, or BB-6's in each dimension."""
        if self.dimensions == ONE:
            return self.left >= MIN_TX_GAS
        return self.limit - self.execution >= MIN_TX_GAS_TWO and self.limit - self.state >= MIN_TX_GAS_TWO

    @staticmethod
    def reservation(tx: AnyTx) -> tuple[int, int]:
        """BB-6: what a transaction reserves in execution and in state."""
        if isinstance(tx, FrameTx):
            return tx.gas_limit - tx.state_limit, tx.state_limit
        return min(tx.gas_limit, TX_MAX_EXEC_RESERVATION), tx.gas_limit

    def fits(self, tx: AnyTx, extra: int = 0) -> bool:
        """BB-3's gas left, or BB-6's reservation in each dimension; `extra` is AG-8's charge."""
        if self.dimensions == ONE:
            return tx.gas_limit + extra <= self.left
        r_x, r_s = self.reservation(tx)
        return r_x + extra <= self.limit - self.execution and r_s <= self.limit - self.state

    def charge(self, tx: AnyTx, extra: int = 0, reverted: bool = False) -> None:
        """An included transaction's gas, and AG-8's charge, which BB-6 counts as execution, as it does all of
        the gas of a transaction that reverted (BB-5)."""
        used = min(tx.reverted_used if reverted else tx.used, tx.gas_limit)
        state = min(tx.state_used, used) if self.dimensions == TWO and not reverted else 0
        self.execution += used - state + extra
        self.state += state

    def charge_execution(self, gas: int) -> None:
        """LU-13's decrypted transactions, execution under BB-6."""
        self.execution += gas


@dataclass(frozen=True)
class Block:
    head: Head
    txs: tuple[AnyTx, ...]
    failed: tuple[tuple[AnyTx, str], ...]
    commitments: tuple[Commitment, ...] = ()  # LU-12
    decrypted: tuple[SealedTx, ...] = ()  # LU-13: the parent's commitments it executed
    gas: GasPool | None = field(default=None, compare=False)  # what the block left, for IL-6
    reverted: tuple = field(default=(), compare=False)  # BB-5 and LU-13: what it included, or decrypted, that reverted


class PriceAndNonce:
    """BB-2, go-ethereum `TransactionsByPriceAndNonce`, with frame transactions as heads of their own."""

    def __init__(self, nonce_view: dict[str, list[Tx]], frame_view: list[FrameTx], base_fee: int,
                 arrival: Callable[[AnyTx], int]):
        self.base_fee = base_fee
        self.arrival = arrival
        self.heap: list = []
        self.rest: dict[tuple, list[AnyTx]] = {}
        for sender in sorted(nonce_view):
            self._push(("nonce", sender), list(nonce_view[sender]))
        for ftx in frame_view:
            self._push(("frame", ftx.hash), [ftx])

    def _push(self, key: tuple, txs: list[AnyTx]) -> None:
        head = txs[0]
        if head.max_fee < self.base_fee:
            return
        self.rest[key] = txs[1:]
        heapq.heappush(self.heap, (-head.effective_tip(self.base_fee), self.arrival(head), key, head))

    def peek(self) -> AnyTx | None:
        return self.heap[0][3] if self.heap else None

    def shift(self) -> None:
        """Replace the best head with its sender's next transaction."""
        _, _, key, _ = heapq.heappop(self.heap)
        rest = self.rest.pop(key)
        if rest:
            self._push(key, rest)

    def pop(self) -> None:
        """Drop the best head and the rest of its sender."""
        _, _, key, _ = heapq.heappop(self.heap)
        self.rest.pop(key, None)


def build_block(pool, parent: Head, state: State, min_tip: int = DEFAULT_MIN_TIP,
                coinbase: str = "coinbase", slot_time: int = SLOT_TIME,
                scheduled: tuple[Commitment, ...] = (), ils: tuple[tuple[AnyTx, ...], ...] = (),
                focil: FocilConfig = FOCIL_OFF, skip: Callable[[AnyTx], bool] | None = None,
                own: tuple[AnyTx, ...] = (), slot: int | None = None,
                dimensions: str = ONE, drop_reverting: bool = False) -> tuple[Block, State]:
    """BB-1 to BB-4 under `dimensions` (BB-6), with AG-8's charge, LU-12 and LU-13, and IL-7 for the slot's `ils`. `pool` is a
    `TxPool`, and `scheduled` is the parent's commitments. With `drop_reverting` the builder leaves out
    what would revert (BB-7). Returns the block and its post-state; the caller resets the pool to them.

    `skip` and `own` are a builder's own choices, which no clause makes: transactions it leaves out
    of its block, sealed transactions among them, and transactions of its own it appends last. The
    simulator's builders that filter use them (decision records 0018 and 0032). `slot` is the slot the block is built for, by default the parent's
    plus one (RR-2)."""
    base_fee = parent.next_base_fee()
    block_head = Head(parent.number + 1, parent.timestamp + slot_time, parent.gas_limit, 0, base_fee,
                      parent.slot + 1 if slot is None else slot)
    post = state.copy()
    gas = GasPool(parent.gas_limit, dimensions)
    cfg = pool.sealed.config
    commitments = []
    if cfg.sealed:  # LU-12
        held = [st for st in pool.sealed.txs() if skip is None or not skip(st)]
        for st in select(held, state, base_fee, min_tip, parent.gas_limit, cfg):
            f = fees(st, base_fee)
            sender = post.edit(st.sender)
            sender.nonce += 1
            sender.balance -= f.ticket_fee
            post.edit(coinbase).balance += f.priority
            commitments.append(Commitment(st, f.tob))
    decrypted = []
    reverted: list = []
    for c in scheduled:  # LU-13
        st = c.tx
        if not st.revealed:
            continue
        used = st.dual_gas_used
        if st.pulls or st.pays:  # executed as BB-5 executes them; a committed one is never dropped (BB-7)
            moves = _moves(post, st.to, None, 0, st.pulls, st.pays, st.atomic)
            if moves is None:
                used = st.reverted_used
                reverted.append(st)
            else:
                _move(post, moves)
        gas.charge_execution(used)
        refund = parent.base_fee * (st.gas_limit - used) + c.tob * (cfg.tob_fee_fraction - 1) // cfg.tob_fee_fraction
        if refund:
            post.edit(st.sender).balance += refund
        if st.key_fee:
            post.edit(st.fee_recipient).balance += st.key_fee
        decrypted.append(st)
    order = PriceAndNonce(pool.nonce.pending_view(min_tip, base_fee),
                          pool.frame.pending_view(min_tip, base_fee), base_fee, pool.arrival)
    included: list[AnyTx] = []
    failed: list[tuple[AnyTx, str]] = []
    while gas.more():
        tx = order.peek()
        if tx is None:
            break
        if skip is not None and skip(tx):
            order.pop()
            continue
        extra = block_gas(tx) if isinstance(tx, FrameTx) else 0  # AG-8
        if not gas.fits(tx, extra):
            order.pop()
            continue
        err, rev = apply_outcome(post, tx, block_head, coinbase, pool.frame.config, drop_reverting)
        if err is None:
            included.append(tx)
            gas.charge(tx, extra, rev)
            if rev:
                reverted.append(tx)
            order.shift()
        elif err == E.ErrNonceTooLow:
            order.shift()
        else:
            failed.append((tx, err))
            order.pop()
    if focil.enabled and ils:  # IL-7
        _append_listed(post, included, gas, ils, block_head, coinbase, pool.frame.config, focil, skip, reverted,
                       drop_reverting)
    for tx in own:
        extra = block_gas(tx) if isinstance(tx, FrameTx) else 0
        if not gas.fits(tx, extra):
            continue
        err, rev = apply_outcome(post, tx, block_head, coinbase, pool.frame.config, drop_reverting)
        if err is None:
            included.append(tx)
            gas.charge(tx, extra, rev)
            if rev:
                reverted.append(tx)
    head = Head(block_head.number, block_head.timestamp, block_head.gas_limit, gas.used, base_fee, block_head.slot)
    return Block(head, tuple(included), tuple(failed), tuple(commitments), tuple(decrypted), gas,
                 tuple(reverted)), post


def _append_listed(post: State, included: list[AnyTx], gas: GasPool, ils: tuple[tuple[AnyTx, ...], ...],
                   block: Head, coinbase: str, frame_cfg: FramePoolConfig, focil: FocilConfig,
                   skip: Callable[[AnyTx], bool] | None, reverted: list, drop_reverting: bool) -> None:
    """IL-7: walk the listed transactions, appending each valid at the end of the payload that fits,
    until a walk appends none."""
    enforceable = set(admitted(ils, block, frame_cfg, focil)) if focil.frames else set()
    candidates = [tx for tx in delivered_order(ils, focil) if skip is None or not skip(tx)]
    present = {tx.hash for tx in included}
    appended = True
    while appended:
        appended = False
        for tx in candidates:
            if tx.hash in present:
                continue
            extra = block_gas(tx) if isinstance(tx, FrameTx) else 0
            if not gas.fits(tx, extra) or not valid_at_end(tx, post, block, frame_cfg, focil, enforceable):
                continue
            err, rev = apply_outcome(post, tx, block, coinbase, frame_cfg, drop_reverting)
            if err is None:
                included.append(tx)
                present.add(tx.hash)
                gas.charge(tx, extra, rev)
                if rev:
                    reverted.append(tx)
                appended = True


def apply_tx(state: State, tx: AnyTx, block: Head, coinbase: str, frame_config: FramePoolConfig,
             drop_reverting: bool = False) -> str | None:
    """BB-5. Mutates `state` and returns None, or returns an error code and leaves it alone; with
    `drop_reverting`, a transaction whose execution would revert is the error `ErrExecutionReverted` (BB-7)."""
    return apply_outcome(state, tx, block, coinbase, frame_config, drop_reverting)[0]


def apply_outcome(state: State, tx: AnyTx, block: Head, coinbase: str, frame_config: FramePoolConfig,
                  drop_reverting: bool = False) -> tuple[str | None, bool]:
    """BB-5 and BB-7: an error code, or None and whether the transaction's execution reverted."""
    base_fee = block.base_fee
    if tx.max_fee < base_fee:
        return E.ErrFeeCapTooLow, False
    price = base_fee + min(tx.tip, tx.max_fee - base_fee)
    used = min(tx.used, tx.gas_limit)
    if isinstance(tx, FrameTx):
        return _apply_frame(state, tx, block, coinbase, frame_config, price, used), False
    nonce = state.nonce(tx.sender)
    if tx.nonce < nonce:
        return E.ErrNonceTooLow, False
    if tx.nonce > nonce:
        return E.ErrNonceTooHigh, False
    if state.balance(tx.sender) < tx.cost:
        return E.ErrInsufficientFunds, False
    executes = bool(tx.pulls or tx.pays)
    if executes:  # the sender's nonce and the authorizations move no balance, so the outcome is known here
        moves = _moves(state, tx.to, tx.sender, tx.value, tx.pulls, tx.pays, tx.atomic)
        if moves is None and drop_reverting:
            return E.ErrExecutionReverted, False
    sender = state.edit(tx.sender)
    sender.nonce += 1
    if tx.type == SET_CODE:  # after the sender's nonce, before the rest (EIP-7702, Behavior)
        for authority, nonce in authorizations(tx):
            acc = state.account(authority)
            if (acc.code == "" or is_delegation(acc.code)) and (nonce is None or nonce == acc.nonce):  # steps 5, 6
                acc = state.edit(authority)
                acc.code = delegation_to(tx.delegate or "")
                acc.nonce += 1
    if not executes:  # nothing it does can revert
        sender.balance -= used * price + tx.value
        if tx.to is not None:
            state.edit(tx.to).balance += tx.value
        state.edit(coinbase).balance += used * (price - base_fee)
        _write(state, tx, block, frame_config)
        return None, False
    if moves is None:  # reverted: none of the execution applies
        used = min(tx.reverted_used, tx.gas_limit)
    else:
        _move(state, moves)
        _write(state, tx, block, frame_config)
    state.edit(tx.sender).balance -= used * price
    state.edit(coinbase).balance += used * (price - base_fee)
    return None, moves is None


def _write(state: State, tx: Tx, block: Head, frame_config: FramePoolConfig) -> None:
    for addr, slot, value in tx.writes:
        state.edit(addr).storage[slot] = value
    apply_writes(state, tx.root_writes, block.slot, frame_config)  # RR-3


def _moves(state: State, to: str | None, sender: str | None, value: int, pulls, pays,
           atomic: bool | None) -> dict[str, int] | None:
    """BB-5's execution of a value, pulls and pays into and out of `to`: the balance changes it makes, or None if
    it reverts. Reads `state` and changes nothing."""
    if to is None:
        raise ValueError("a transaction that pulls or pays names its `to`")
    delta: dict[str, int] = {}

    def move(src: str, dst: str, amount: int) -> None:
        delta[src] = delta.get(src, 0) - amount
        delta[dst] = delta.get(dst, 0) + amount

    if value:
        move(sender, to, value)
    for account, amount in pulls or ():
        if state.balance(account) + delta.get(account, 0) >= amount:
            move(account, to, amount)
        elif atomic is not False:
            return None
    for account, amount in pays or ():
        if state.balance(to) + delta.get(to, 0) < amount:
            return None
        move(to, account, amount)
    return delta


def _move(state: State, moves: dict[str, int]) -> None:
    for addr, change in moves.items():
        if change:
            state.edit(addr).balance += change


def _apply_frame(state: State, tx: FrameTx, block: Head, coinbase: str, cfg: FramePoolConfig,
                 price: int, used: int) -> str | None:
    prefix = analyse(tx, cfg)
    if prefix is None:
        return E.ErrFrameNoPayer
    try:
        sim = simulate(tx, prefix, block, state, cfg)
    except TxError as err:
        return err.code
    if expiring(tx, cfg):  # EN-7: no sequence changes, and seen(h) becomes the deadline
        state.edit(cfg.nonce_ring).storage[seen_slot(tx.hash)] = sim.deadline
    else:
        for key in tx.nonce_keys:
            state.bump_nonce_seq(tx.sender, key)
    state.edit(sim.payer).balance -= used * price
    state.edit(coinbase).balance += used * (price - block.base_fee)
    for frame, kind in zip(prefix.frames, prefix.kinds):
        if kind == DEPLOY and frame.installs_code is not None:
            sender = state.edit(tx.sender)
            sender.code = frame.installs_code
            for addr, slot, value in frame.writes:
                sender.storage[slot] = value
    for frame in prefix.rest:
        if frame.mode == SENDER_MODE and frame.value:
            target = frame.target if frame.target is not None else tx.sender
            if state.balance(tx.sender) >= frame.value:
                state.edit(tx.sender).balance -= frame.value
                state.edit(target).balance += frame.value
    for addr, slot, value in tx.writes:
        state.edit(addr).storage[slot] = value
    apply_writes(state, tx.root_writes, block.slot, cfg)  # RR-3
    return None
