"""Keccak-256, the hash Ethereum names a transaction by (`docs/spec/11-surface.md`, SF-3).

Python's `hashlib.sha3_256` is FIPS 202 SHA3-256, whose padding differs from the
original Keccak's, so this is the permutation written out, standard library only.
"""

from __future__ import annotations

_RC = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)
_ROT = (
    (0, 36, 3, 41, 18),
    (1, 44, 10, 45, 2),
    (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56),
    (27, 20, 39, 8, 14),
)
_MASK = (1 << 64) - 1
_RATE = 136  # bytes: 1600 bits less twice the 256-bit output


def _rotl(x: int, n: int) -> int:
    return ((x << n) | (x >> (64 - n))) & _MASK if n else x


def _permute(a: list[list[int]]) -> None:
    """Keccak-f[1600] on a 5 by 5 state of 64-bit lanes, indexed a[x][y]."""
    for rc in _RC:
        c = [a[x][0] ^ a[x][1] ^ a[x][2] ^ a[x][3] ^ a[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rotl(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                a[x][y] ^= d[x]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rotl(a[x][y], _ROT[x][y])
        for x in range(5):
            for y in range(5):
                a[x][y] = b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y])
        a[0][0] ^= rc


def keccak256(data: bytes) -> bytes:
    """Keccak-256 with the original padding, 0x01 ... 0x80."""
    padded = bytearray(data)
    padded.append(0x01)
    padded.extend(b"\x00" * (-len(padded) % _RATE))
    padded[-1] |= 0x80
    a = [[0] * 5 for _ in range(5)]
    for off in range(0, len(padded), _RATE):
        block = padded[off:off + _RATE]
        for i in range(_RATE // 8):
            a[i % 5][i // 5] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        _permute(a)
    out = b"".join(a[i % 5][i // 5].to_bytes(8, "little") for i in range(4))
    return out
