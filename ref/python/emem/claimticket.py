"""A claim's ticket: the bytes an issuer signs, when a node takes it as valid, and where a
transaction carries it (`docs/spec/10-claim-gated-admission.md`, CG-8 to CG-10)."""

from __future__ import annotations

from dataclasses import dataclass

from .bls import Invalid, g2_from_2537, verify_2537
from .keccak import keccak256

NAMESPACE = b"FRAME_TICKET_V1"
PAY_DATA = 168  # CG-10: epoch (8), salt (32), the signature (128)
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


def nonce_keys_hash(keys: tuple[int, ...]) -> bytes:
    """EIP-8250's, the word `TXPARAM(0x0F)` returns."""
    return keccak256(b"".join(x.to_bytes(32, "big") for x in (len(keys), *keys)))


def message(c: TicketClaim) -> bytes | None:
    """CG-8: the message, or None when the claim has none."""
    if c.chain_id >= U256 or any(k >= U256 for k in c.nonce_keys):
        return None
    if c.epoch >= U64 or c.nonce_seq >= U64 or len(c.sender) != 20 or len(c.salt) != 32:
        return None
    return (
        c.chain_id.to_bytes(32, "big")
        + c.sender
        + nonce_keys_hash(c.nonce_keys)
        + c.nonce_seq.to_bytes(8, "big")
        + c.epoch.to_bytes(8, "big")
        + c.salt
    )


def valid(c: TicketClaim, issuer: bytes, signature: bytes) -> bool:
    """CG-9: step 1 here, steps 2 and 3 in `bls.verify_2537`."""
    m = message(c)
    return m is not None and verify_2537(issuer, NAMESPACE, m, signature)


def paymaster_key(code: bytes) -> bytes | None:
    """CG-10: the key of a ticket paymaster whose code this is, or None if it is not one."""
    if len(code) != TEMPLATE_LENGTH + 256 + 32 or keccak256(code[:TEMPLATE_LENGTH]) != TEMPLATE_KECCAK:
        return None
    key = code[TEMPLATE_LENGTH:TEMPLATE_LENGTH + 256]
    try:
        return key if g2_from_2537(key) is not None else None
    except Invalid:
        return None


def from_pay_data(data: bytes) -> tuple[int, bytes, bytes] | None:
    """CG-10: a ticket paymaster's frame data as (epoch, salt, signature), or None if it is not one."""
    if len(data) != PAY_DATA:
        return None
    return int.from_bytes(data[:8], "big"), data[8:40], data[40:]


@dataclass(frozen=True)
class TicketFrame:
    """A frame as CG-10 reads it: its mode, its target's 20 bytes and its data."""

    mode: int
    target: bytes
    data: bytes


VERIFY = 1


def carried(c: TicketClaim, frames: list[TicketFrame],
            codes: dict[bytes, bytes]) -> tuple[tuple[int | None, bytes | None, bytes], bool] | None:
    """CG-10: the claim a transaction carries as (epoch, salt, issuer) with CG-9's verdict, or None.

    `c` gives the transaction's chain, sender and nonces; its epoch and salt are ignored. `codes` is the code at
    the node's head of each account a frame targets; an account it leaves out has none."""
    for f in frames:
        issuer = paymaster_key(codes.get(f.target, b"")) if f.mode == VERIFY else None
        if issuer is None:
            continue
        parsed = from_pay_data(f.data)
        if parsed is None:
            return (None, None, issuer), False
        epoch, salt, signature = parsed
        claim = TicketClaim(c.chain_id, epoch, c.sender, c.nonce_seq, c.nonce_keys, salt)
        return (epoch, salt, issuer), valid(claim, issuer, signature)
    return None
