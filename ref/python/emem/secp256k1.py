"""secp256k1 public key recovery, as EIP-8141's `validate_signature` uses it for a `SECP256K1` entry
(`docs/spec/10-claim-gated-admission.md`, CG-12), with the standard library only."""

from __future__ import annotations

from .keccak import keccak256

P = 2**256 - 2**32 - 977
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
     0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)

_Jacobian = tuple[int, int, int]
_INFINITY: _Jacobian = (0, 1, 0)


def _double(a: _Jacobian) -> _Jacobian:
    x, y, z = a
    if z == 0 or y == 0:
        return _INFINITY
    s = 4 * x * y * y % P
    m = 3 * x * x % P
    x3 = (m * m - 2 * s) % P
    return x3, (m * (s - x3) - 8 * pow(y, 4, P)) % P, 2 * y * z % P


def _add(a: _Jacobian, b: _Jacobian) -> _Jacobian:
    if a[2] == 0:
        return b
    if b[2] == 0:
        return a
    x1, y1, z1 = a
    x2, y2, z2 = b
    z1z1, z2z2 = z1 * z1 % P, z2 * z2 % P
    u1, u2 = x1 * z2z2 % P, x2 * z1z1 % P
    s1, s2 = y1 * z2 * z2z2 % P, y2 * z1 * z1z1 % P
    if u1 == u2:
        return _double(a) if s1 == s2 else _INFINITY
    h, r = (u2 - u1) % P, (s2 - s1) % P
    hh = h * h % P
    hhh = h * hh % P
    x3 = (r * r - hhh - 2 * u1 * hh) % P
    return x3, (r * (u1 * hh - x3) - s1 * hhh) % P, h * z1 * z2 % P


def _mul(k: int, a: _Jacobian) -> _Jacobian:
    out = _INFINITY
    for bit in bin(k % N)[2:]:
        out = _double(out)
        if bit == "1":
            out = _add(out, a)
    return out


def _affine(a: _Jacobian) -> tuple[int, int] | None:
    if a[2] == 0:
        return None
    zi = pow(a[2], P - 2, P)
    return a[0] * zi * zi % P, a[1] * zi * zi * zi % P


def recover(digest: bytes, v: int, r: int, s: int) -> bytes | None:
    """The 20-byte address whose key signed `digest` with (v, r, s), or None. The caller checks EIP-8141's ranges
    (v 0 or 1, 0 < r < N, 0 < s <= N // 2); this needs only 0 < r, s < N."""
    if v not in (0, 1) or not (0 < r < N and 0 < s < N):
        return None
    y2 = (pow(r, 3, P) + 7) % P
    y = pow(y2, (P + 1) // 4, P)
    if y * y % P != y2:
        return None
    if y % 2 != v:
        y = P - y
    e = int.from_bytes(digest, "big") % N
    r_inv = pow(r, N - 2, N)
    point = _affine(_add(_mul(s * r_inv, (r, y, 1)), _mul(-e * r_inv % N, (*G, 1))))
    if point is None:
        return None
    return keccak256(point[0].to_bytes(32, "big") + point[1].to_bytes(32, "big"))[12:]


def address(private_key: int) -> bytes:
    """The address of a private key; for the reference's tests only."""
    x, y = _affine(_mul(private_key, (*G, 1)))
    return keccak256(x.to_bytes(32, "big") + y.to_bytes(32, "big"))[12:]
