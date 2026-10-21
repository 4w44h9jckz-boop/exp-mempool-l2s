"""Accounts, state, heads and the base fee: `docs/spec/00-model.md`, MD-1 to MD-4 and FEE-1."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

DELEGATION_PREFIX = "0xef0100"


def is_delegation(code: str) -> bool:
    """MD-2: a code value starting with 0xef0100 is an EIP-7702 delegation indicator."""
    return code.startswith(DELEGATION_PREFIX)


def delegation_to(delegate: str) -> str:
    return DELEGATION_PREFIX + delegate


@dataclass
class Account:
    """MD-2."""

    nonce: int = 0
    balance: int = 0
    code: str = ""
    storage: dict[int, int] = field(default_factory=dict)
    nonce_seqs: dict[int, int] = field(default_factory=dict)
    withdrawal: int = 0
    stake: int = 0  # MD-2, version 10: what ERC-8421's Staking Registry reports
    unstake_delay: int = 0
    withdrawing: bool = False

    def copy(self) -> Account:
        return Account(self.nonce, self.balance, self.code, dict(self.storage),
                       dict(self.nonce_seqs), self.withdrawal, self.stake, self.unstake_delay, self.withdrawing)


_EMPTY = Account()
_VERSIONS = itertools.count(1)


class State:
    """MD-3: addresses to accounts. An absent address reads as the default account.

    Pools only read a state. Whoever produces the next state (a builder) copies
    first, so a state handed to a pool never changes under it. A copy shares
    its accounts with the original until `edit` copies one, on either side, so
    copying costs a dictionary and an account nobody edited is the same object
    in both (`changed_since`).
    """

    def __init__(self, accounts: dict[str, Account] | None = None):
        self._accounts: dict[str, Account] = {a: acc.copy() for a, acc in (accounts or {}).items()}
        self._own: set[str] = set(self._accounts)  # accounts this state alone holds, and may change in place
        self._version = next(_VERSIONS)  # renewed at every copy, so a copy knows if it is its original's latest
        self._base = 0  # the version of the state this one was copied from

    def account(self, addr: str) -> Account:
        """A read-only view. Mutating it is a bug; use `edit`."""
        return self._accounts.get(addr, _EMPTY)

    def edit(self, addr: str) -> Account:
        if addr not in self._own:
            acc = self._accounts.get(addr)
            self._accounts[addr] = acc.copy() if acc is not None else Account()
            self._own.add(addr)
        return self._accounts[addr]

    def nonce(self, addr: str) -> int:
        return self.account(addr).nonce

    def balance(self, addr: str) -> int:
        return self.account(addr).balance

    def code(self, addr: str) -> str:
        return self.account(addr).code

    def storage(self, addr: str, slot: int) -> int:
        return self.account(addr).storage.get(slot, 0)

    def withdrawal(self, addr: str) -> int:
        return self.account(addr).withdrawal

    def stake(self, addr: str) -> tuple[int, int, bool]:
        """MD-2: the stake, unstake delay and withdrawal flag the Staking Registry reports for `addr`."""
        a = self.account(addr)
        return a.stake, a.unstake_delay, a.withdrawing

    def nonce_seq(self, addr: str, key: int) -> int:
        """MD-3: key 0 is the account nonce (EIP-8250)."""
        if key == 0:
            return self.nonce(addr)
        return self.account(addr).nonce_seqs.get(key, 0)

    def bump_nonce_seq(self, addr: str, key: int) -> None:
        acc = self.edit(addr)
        if key == 0:
            acc.nonce += 1
        else:
            acc.nonce_seqs[key] = acc.nonce_seqs.get(key, 0) + 1

    def addresses(self) -> list[str]:
        return list(self._accounts)

    def copy(self) -> State:
        new = State.__new__(State)
        new._accounts = dict(self._accounts)
        new._own = set()
        self._own = set()
        self._version, self._base = next(_VERSIONS), 0  # its edits so far are no longer its own to list
        new._version, new._base = next(_VERSIONS), self._version
        return new

    def changed_since(self, older: State) -> set[str]:
        """The addresses whose account may differ from `older`'s: every one edited since a common copy, at least.

        When this state is the latest copy of `older` and `older` has not been
        edited since, that is exactly the accounts this one has edited.
        """
        if self._base == older._version and not older._own:
            return set(self._own)
        mine, theirs = self._accounts, older._accounts
        out = {a for a, acc in mine.items() if theirs.get(a) is not acc}
        out.update(a for a in theirs if a not in mine)
        return out

    def __eq__(self, other: object) -> bool:
        return isinstance(other, State) and self._accounts == other._accounts


@dataclass(frozen=True)
class Head:
    """MD-4, with the slot of `08-recent-roots.md`, RR-2."""

    number: int = 0
    timestamp: int = 0
    gas_limit: int = 30_000_000
    gas_used: int = 15_000_000
    base_fee: int = 10
    slot: int = 0  # RR-2: EIP-7843's slotNumber

    def next_base_fee(self) -> int:
        return next_base_fee(self.gas_limit, self.gas_used, self.base_fee)


ELASTICITY_MULTIPLIER = 2
BASE_FEE_CHANGE_DENOMINATOR = 8


def next_base_fee(gas_limit: int, gas_used: int, base_fee: int) -> int:
    """FEE-1, go-ethereum `CalcBaseFee`."""
    target = gas_limit // ELASTICITY_MULTIPLIER
    if gas_used == target:
        return base_fee
    if gas_used > target:
        delta = base_fee * (gas_used - target) // target // BASE_FEE_CHANGE_DENOMINATOR
        return base_fee + max(1, delta)
    delta = base_fee * (target - gas_used) // target // BASE_FEE_CHANGE_DENOMINATOR
    return max(0, base_fee - delta)


def effective_tip(max_fee: int, tip: int, base_fee: int) -> int:
    """FEE-2. Negative when the fee cap is below the base fee."""
    return min(tip, max_fee - base_fee)
