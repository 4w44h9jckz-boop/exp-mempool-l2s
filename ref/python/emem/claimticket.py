"""A claim's ticket: the bytes an issuer signs, when a node takes it as valid, where a transaction carries it, and
whether it is bound to that transaction (`docs/spec/10-claim-gated-admission.md`, CG-8 to CG-10 and CG-12)."""

from __future__ import annotations

from dataclasses import dataclass

from .bls import Invalid, g2_from_2537, verify_2537
from .keccak import keccak256
from .secp256k1 import N as SECP256K1_N
from .secp256k1 import recover

NAMESPACE = b"FRAME_TICKET_V1"
PAY_DATA = 168  # CG-10: epoch (8), salt (32), the signature (128)
BOUND_PAY_DATA = 188  # CG-10: epoch (8), salt (32), the binder (20), the signature (128)
U64, U256 = 2**64, 2**256
# CG-10: the ticket-paymaster template, then a 256-byte key and 32 bytes
TEMPLATE_LENGTH = 1105
TEMPLATE_KECCAK = bytes.fromhex("ec9f3f855524392a3891f2f2eb554781236d5565520d68388e455be74bdf3fe0")


@dataclass(frozen=True)
class TicketClaim:
    """A claim's fields as a ticket names them, with the chain it is for."""

    chain_id: int
    epoch: int
    sender: bytes
    nonce_seq: int
    nonce_keys: tuple[int, ...]
    salt: bytes
    binder: bytes = b""


def nonce_keys_hash(keys: tuple[int, ...]) -> bytes:
    """EIP-8250's, the word `TXPARAM(0x0F)` returns."""
    return keccak256(b"".join(x.to_bytes(32, "big") for x in (len(keys), *keys)))


def message(c: TicketClaim) -> bytes | None:
    """CG-8: the message, or None when the claim has none."""
    if c.chain_id >= U256 or any(k >= U256 for k in c.nonce_keys):
        return None
    if c.epoch >= U64 or c.nonce_seq >= U64 or len(c.sender) != 20 or len(c.salt) != 32:
        return None
    if len(c.binder) not in (0, 20):
        return None
    return (
        c.chain_id.to_bytes(32, "big")
        + c.sender
        + nonce_keys_hash(c.nonce_keys)
        + c.nonce_seq.to_bytes(8, "big")
        + c.epoch.to_bytes(8, "big")
        + c.salt
        + c.binder
    )


def valid(c: TicketClaim, issuer: bytes, signature: bytes) -> bool:
    """CG-9: step 1 here, steps 2 and 3 in `bls.verify_2537`."""
    m = message(c)
    return m is not None and verify_2537(issuer, NAMESPACE, m, signature)


def paymaster_key(code: bytes, template: tuple[int, bytes] = (TEMPLATE_LENGTH, TEMPLATE_KECCAK)) -> bytes | None:
    """CG-10: the key of a paymaster whose code is `template`, given as its length and keccak256, then a key and 32
    bytes, or None if it is not one."""
    length, digest = template
    if len(code) != length + 256 + 32 or keccak256(code[:length]) != digest:
        return None
    key = code[length:length + 256]
    try:
        return key if g2_from_2537(key) is not None else None
    except Invalid:
        return None


def from_pay_data(data: bytes, bound: bool = False) -> tuple[int, bytes, bytes, bytes] | None:
    """CG-10: a ticket paymaster's frame data as (epoch, salt, binder, signature), or None if it is not one; a bound
    ticket paymaster's carries the binder after the salt, any other's no binder."""
    if len(data) != (BOUND_PAY_DATA if bound else PAY_DATA):
        return None
    if bound:
        return int.from_bytes(data[:8], "big"), data[8:40], data[40:60], data[60:]
    return int.from_bytes(data[:8], "big"), data[8:40], b"", data[40:]


@dataclass(frozen=True)
class TxSignature:
    """An entry of a frame transaction's `signatures` as EIP-8141 encodes it."""

    scheme: int
    signer: bytes
    msg: bytes
    signature: bytes


SECP256K1 = 1


def bound(binder: bytes, sender: bytes, signatures: list[TxSignature], sig_hash: bytes) -> bool:
    """CG-12: whether some `secp256k1` signature with an empty msg, resolved to `binder`, verifies over the
    signature hash as EIP-8141's `validate_signature` verifies it."""
    if len(binder) != 20:
        return False
    for s in signatures:
        if s.scheme != SECP256K1 or s.msg or (s.signer or sender) != binder or len(s.signature) != 65:
            continue
        v, r, s_ = s.signature[0], int.from_bytes(s.signature[1:33], "big"), int.from_bytes(s.signature[33:], "big")
        if v > 1 or not 0 < r < SECP256K1_N or not 0 < s_ <= SECP256K1_N // 2:
            continue
        if recover(sig_hash, v, r, s_) == binder:
            return True
    return False


@dataclass(frozen=True)
class TicketFrame:
    """A frame as CG-10 reads it: its mode, its target's 20 bytes and its data."""

    mode: int
    target: bytes
    data: bytes


VERIFY = 1


def carried(c: TicketClaim, frames: list[TicketFrame], codes: dict[bytes, bytes],
            bound_template: tuple[int, bytes] | None = None
            ) -> tuple[tuple[int | None, bytes | None, bytes | None, bytes], bool] | None:
    """CG-10: the claim a transaction carries as (epoch, salt, binder, issuer) with CG-9's verdict, or None; the
    binder is None for a ticket paymaster's claim, which has none.

    `c` gives the transaction's chain, sender and nonces; its epoch, salt and binder are ignored. `codes` is the code
    at the node's head of each account a frame targets; an account it leaves out has none. `bound_template` is the
    profile's bound template as its length and keccak256 (CG-1), or None if it names none."""
    for f in frames:
        if f.mode != VERIFY:
            continue
        code = codes.get(f.target, b"")
        is_bound, issuer = False, paymaster_key(code)
        if issuer is None and bound_template is not None:
            is_bound, issuer = True, paymaster_key(code, bound_template)
        if issuer is None:
            continue
        parsed = from_pay_data(f.data, is_bound)
        if parsed is None:
            return (None, None, None, issuer), False
        epoch, salt, binder, signature = parsed
        claim = TicketClaim(c.chain_id, epoch, c.sender, c.nonce_seq, c.nonce_keys, salt, binder)
        return (epoch, salt, binder if is_bound else None, issuer), valid(claim, issuer, signature)
    return None
