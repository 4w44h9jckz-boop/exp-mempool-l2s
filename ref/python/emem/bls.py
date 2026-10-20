"""BLS12-381 verification of an admission ticket (`docs/spec/10-claim-gated-admission.md`, CG-9).

Signatures in G1 and keys in G2, the variant that keeps signatures short; the
message hashed to G1 by RFC 9380's suite BLS12381G1_XMD:SHA-256_SSWU_RO_;
points in EIP-2537's encoding, as a ticket carries them, or in the compressed
form of the zkcrypto serialization, as Commonware writes them. Standard
library only, and slow: a verification takes about a second, which
conformance can afford and a node cannot.
"""

from __future__ import annotations

import hashlib

P = 0x1A0111EA397FE69A4B1BA7B6434BACD764774B84F38512BF6730D2A0F6B0F6241EABFFFEB153FFFFB9FEFFFFFFFFAAAB
R = 0x73EDA753299D7D483339D80809A1D80553BDA402FFFE5BFEFFFFFFFF00000001
X_ABS = 0xD201000000010000  # |x|, the curve's parameter; x itself is negative
H_EFF = 0xD201000000010001  # RFC 9380, section 8.8.1
DST = b"BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_POP_"

G2_GEN = (
    (
        0x024AA2B2F08F0A91260805272DC51051C6E47AD4FA403B02B4510B647AE3D1770BAC0326A805BBEFD48056C8C121BDB8,
        0x13E02B6052719F607DACD3A088274F65596BD0D09920B61AB5DA61BBDC7F5049334CF11213945D57E5AC7D055D042B7E,
    ),
    (
        0x0CE5D527727D6E118CC9CDC6DA2E351AADFD9BAA8CBDD3A76D429A695160D12C923AC9CC3BACA289E193548608B82801,
        0x0606C4A02EA734CC32ACD2B02BC28B99CB3E287E85A763AF267492AB572E99AB3F370D275CEC1DA1AAA9075FF05F79BE,
    ),
)

# Simplified SWU on the curve 11-isogenous to G1's (RFC 9380, section 8.8.1).
_A = 0x144698A3B8E9433D693A02C96D4982B0EA985383EE66A8D8E8981AEFD881AC98936F8DA0E0F97F5CF428082D584C1D
_B = 0x12E2908D11688030018B12E8753EEE3B2016C1F0F24F4070A0B9C14FCEF35EF55A23215A316CEAA5D1CC48E98E172BE0
_Z = 11

# The 11-isogeny's coefficients, lowest degree first (RFC 9380, appendix E.2);
# the denominators' leading coefficients are 1 and not listed.
_XNUM = (
    0x11a05f2b1e833340b809101dd99815856b303e88a2d7005ff2627b56cdb4e2c85610c2d5f2e62d6eaeac1662734649b7,
    0x17294ed3e943ab2f0588bab22147a81c7c17e75b2f6a8417f565e33c70d1e86b4838f2a6f318c356e834eef1b3cb83bb,
    0xd54005db97678ec1d1048c5d10a9a1bce032473295983e56878e501ec68e25c958c3e3d2a09729fe0179f9dac9edcb0,
    0x1778e7166fcc6db74e0609d307e55412d7f5e4656a8dbf25f1b33289f1b330835336e25ce3107193c5b388641d9b6861,
    0xe99726a3199f4436642b4b3e4118e5499db995a1257fb3f086eeb65982fac18985a286f301e77c451154ce9ac8895d9,
    0x1630c3250d7313ff01d1201bf7a74ab5db3cb17dd952799b9ed3ab9097e68f90a0870d2dcae73d19cd13c1c66f652983,
    0xd6ed6553fe44d296a3726c38ae652bfb11586264f0f8ce19008e218f9c86b2a8da25128c1052ecaddd7f225a139ed84,
    0x17b81e7701abdbe2e8743884d1117e53356de5ab275b4db1a682c62ef0f2753339b7c8f8c8f475af9ccb5618e3f0c88e,
    0x80d3cf1f9a78fc47b90b33563be990dc43b756ce79f5574a2c596c928c5d1de4fa295f296b74e956d71986a8497e317,
    0x169b1f8e1bcfa7c42e0c37515d138f22dd2ecb803a0c5c99676314baf4bb1b7fa3190b2edc0327797f241067be390c9e,
    0x10321da079ce07e272d8ec09d2565b0dfa7dccdde6787f96d50af36003b14866f69b771f8c285decca67df3f1605fb7b,
    0x6e08c248e260e70bd1e962381edee3d31d79d7e22c837bc23c0bf1bc24c6b68c24b1b80b64d391fa9c8ba2e8ba2d229,
)
_XDEN = (
    0x8ca8d548cff19ae18b2e62f4bd3fa6f01d5ef4ba35b48ba9c9588617fc8ac62b558d681be343df8993cf9fa40d21b1c,
    0x12561a5deb559c4348b4711298e536367041e8ca0cf0800c0126c2588c48bf5713daa8846cb026e9e5c8276ec82b3bff,
    0xb2962fe57a3225e8137e629bff2991f6f89416f5a718cd1fca64e00b11aceacd6a3d0967c94fedcfcc239ba5cb83e19,
    0x3425581a58ae2fec83aafef7c40eb545b08243f16b1655154cca8abc28d6fd04976d5243eecf5c4130de8938dc62cd8,
    0x13a8e162022914a80a6f1d5f43e7a07dffdfc759a12062bb8d6b44e833b306da9bd29ba81f35781d539d395b3532a21e,
    0xe7355f8e4e667b955390f7f0506c6e9395735e9ce9cad4d0a43bcef24b8982f7400d24bc4228f11c02df9a29f6304a5,
    0x772caacf16936190f3e0c63e0596721570f5799af53a1894e2e073062aede9cea73b3538f0de06cec2574496ee84a3a,
    0x14a7ac2a9d64a8b230b3f5b074cf01996e7f63c21bca68a81996e1cdf9822c580fa5b9489d11e2d311f7d99bbdcc5a5e,
    0xa10ecf6ada54f825e920b3dafc7a3cce07f8d1d7161366b74100da67f39883503826692abba43704776ec3a79a1d641,
    0x95fc13ab9e92ad4476d6e3eb3a56680f682b4ee96f7d03776df533978f31c1593174e4b4b7865002d6384d168ecdd0a,
)
_YNUM = (
    0x90d97c81ba24ee0259d1f094980dcfa11ad138e48a869522b52af6c956543d3cd0c7aee9b3ba3c2be9845719707bb33,
    0x134996a104ee5811d51036d776fb46831223e96c254f383d0f906343eb67ad34d6c56711962fa8bfe097e75a2e41c696,
    0xcc786baa966e66f4a384c86a3b49942552e2d658a31ce2c344be4b91400da7d26d521628b00523b8dfe240c72de1f6,
    0x1f86376e8981c217898751ad8746757d42aa7b90eeb791c09e4a3ec03251cf9de405aba9ec61deca6355c77b0e5f4cb,
    0x8cc03fdefe0ff135caf4fe2a21529c4195536fbe3ce50b879833fd221351adc2ee7f8dc099040a841b6daecf2e8fedb,
    0x16603fca40634b6a2211e11db8f0a6a074a7d0d4afadb7bd76505c3d3ad5544e203f6326c95a807299b23ab13633a5f0,
    0x4ab0b9bcfac1bbcb2c977d027796b3ce75bb8ca2be184cb5231413c4d634f3747a87ac2460f415ec961f8855fe9d6f2,
    0x987c8d5333ab86fde9926bd2ca6c674170a05bfe3bdd81ffd038da6c26c842642f64550fedfe935a15e4ca31870fb29,
    0x9fc4018bd96684be88c9e221e4da1bb8f3abd16679dc26c1e8b6e6a1f20cabe69d65201c78607a360370e577bdba587,
    0xe1bba7a1186bdb5223abde7ada14a23c42a0ca7915af6fe06985e7ed1e4d43b9b3f7055dd4eba6f2bafaaebca731c30,
    0x19713e47937cd1be0dfd0b8f1d43fb93cd2fcbcb6caf493fd1183e416389e61031bf3a5cce3fbafce813711ad011c132,
    0x18b46a908f36f6deb918c143fed2edcc523559b8aaf0c2462e6bfe7f911f643249d9cdf41b44d606ce07c8a4d0074d8e,
    0xb182cac101b9399d155096004f53f447aa7b12a3426b08ec02710e807b4633f06c851c1919211f20d4c04f00b971ef8,
    0x245a394ad1eca9b72fc00ae7be315dc757b3b080d4c158013e6632d3c40659cc6cf90ad1c232a6442d9d3f5db980133,
    0x5c129645e44cf1102a159f748c4a3fc5e673d81d7e86568d9ab0f5d396a7ce46ba1049b6579afb7866b1e715475224b,
    0x15e6be4e990f03ce4ea50b3b42df2eb5cb181d8f84965a3957add4fa95af01b2b665027efec01c7704b456be69c8b604,
)
_YDEN = (
    0x16112c4c3a9c98b252181140fad0eae9601a6de578980be6eec3232b5be72e7a07f3688ef60c206d01479253b03663c1,
    0x1962d75c2381201e1a0cbd6c43c348b885c84ff731c4d59ca4a10356f453e01f78a4260763529e3532f6102c2e49a03d,
    0x58df3306640da276faaae7d6e8eb15778c4855551ae7f310c35a5dd279cd2eca6757cd636f96f891e2538b53dbf67f2,
    0x16b7d288798e5395f20d23bf89edb4d1d115c5dbddbcd30e123da489e726af41727364f2c28297ada8d26d98445f5416,
    0xbe0e079545f43e4b00cc912f8228ddcc6d19c9f0f69bbb0542eda0fc9dec916a20b15dc0fd2ededda39142311a5001d,
    0x8d9e5297186db2d9fb266eaac783182b70152c65550d881c5ecd87b6f0f5a6449f38db9dfa9cce202c6477faaf9b7ac,
    0x166007c08a99db2fc3ba8734ace9824b5eecfdfa8d0cf8ef5dd365bc400a0051d5fa9c01a58b1fb93d1a1399126a775c,
    0x16a3ef08be3ea7ea03bcddfabba6ff6ee5a4375efa1f4fd7feb34fd206357132b920f5b00801dee460ee415a15812ed9,
    0x1866c8ed336c61231a1be54fd1d74cc4f9fb0ce4c6af5920abc5750c4bf39b4852cfe2f7bb9248836b233d9d55535d4a,
    0x167a55cda70a6e1cea820597d94a84903216f763e13d87bb5308592e7ea7d4fbc7385ea3d529b35e346ef48bb8913f55,
    0x4d2f259eea405bd48f010a01ad2911d9c6dd039bb61a6290e591b36e636a5c871a5c29f4f83060400f8b49cba8f6aa8,
    0xaccbb67481d033ff5852c1e48c50c477f94ff8aefce42d28c0f9a88cea7913516f968986f7ebbea9684b529e2561092,
    0xad6b9514c767fe3c3613144b45f1496543346d98adf02267d5ceef9a00d9b8693000763e3b90ac11e99b138573345cc,
    0x2660400eb2e4f3b628bdd0d53cd76f2bf565b94e72927c1cb748df27942480e420517bd8714cc80d1fadc1326ed06f7,
    0xe0fa1d816ddc03e6b24255e0d7819c171c40f65e273b853324efcd6356caa205ca2f570f13497804415473a1d634b8f,
)


class Invalid(ValueError):
    """Bytes that are not a point of the group they claim."""


# Fp is int modulo P; Fp2 is a pair (a, b) for a + b u, with u^2 = -1.


def _inv(a: int) -> int:
    return pow(a, P - 2, P)


def _sqrt(a: int) -> int | None:
    r = pow(a, (P + 1) // 4, P)
    return r if r * r % P == a % P else None


def _f2_mul(x, y):
    return ((x[0] * y[0] - x[1] * y[1]) % P, (x[0] * y[1] + x[1] * y[0]) % P)


def _f2_inv(x):
    n = _inv(x[0] * x[0] + x[1] * x[1])
    return (x[0] * n % P, -x[1] * n % P)


def _f2_sqrt(x):
    """A square root in Fp2 through the norm, or None."""
    a, b = x[0] % P, x[1] % P
    if b == 0:
        r = _sqrt(a)
        if r is not None:
            return (r, 0)
        r = _sqrt(-a % P)
        return None if r is None else (0, r)
    g = _sqrt(a * a + b * b)
    if g is None:
        return None
    half = _inv(2)
    d = (a + g) * half % P
    r0 = _sqrt(d)
    if r0 is None:
        r0 = _sqrt((a - g) * half % P)
        if r0 is None:
            return None
    r = (r0, b * _inv(2 * r0) % P)
    return r if _f2_mul(r, r) == (a, b) else None


class _Field:
    """The arithmetic a curve's points need, for Fp or Fp2."""

    def __init__(self, add, sub, mul, inv, zero, small):
        self.add, self.sub, self.mul, self.inv, self.zero, self.small = add, sub, mul, inv, zero, small


_FP = _Field(
    lambda x, y: (x + y) % P, lambda x, y: (x - y) % P, lambda x, y: x * y % P, _inv, 0, lambda n: n % P
)
_FP2 = _Field(
    lambda x, y: ((x[0] + y[0]) % P, (x[1] + y[1]) % P),
    lambda x, y: ((x[0] - y[0]) % P, (x[1] - y[1]) % P),
    _f2_mul,
    _f2_inv,
    (0, 0),
    lambda n: (n % P, 0),
)


def _add(f: _Field, p, q):
    """Affine addition on y^2 = x^3 + b; None is the point at infinity."""
    if p is None:
        return q
    if q is None:
        return p
    if p[0] == q[0]:
        if f.add(p[1], q[1]) == f.zero:
            return None
        lam = f.mul(f.mul(f.small(3), f.mul(p[0], p[0])), f.inv(f.mul(f.small(2), p[1])))
    else:
        lam = f.mul(f.sub(q[1], p[1]), f.inv(f.sub(q[0], p[0])))
    x = f.sub(f.sub(f.mul(lam, lam), p[0]), q[0])
    return (x, f.sub(f.mul(lam, f.sub(p[0], x)), p[1]))


def _mul(f: _Field, p, n: int):
    out = None
    for bit in bin(n)[2:]:
        out = _add(f, out, out)
        if bit == "1":
            out = _add(f, out, p)
    return out


def _neg(f: _Field, p):
    return None if p is None else (p[0], f.sub(f.zero, p[1]))


# Points, compressed (zkcrypto): the top three bits of the first byte say
# compressed, infinity, and whether y is the larger of y and -y.


def _flags(data: bytes, size: int) -> tuple[bool, bool, int]:
    if len(data) != size:
        raise Invalid(f"{len(data)} bytes, not {size}")
    if not data[0] & 0x80:
        raise Invalid("not compressed")
    return bool(data[0] & 0x40), bool(data[0] & 0x20), int.from_bytes(bytes([data[0] & 0x1F]) + data[1:], "big")


def _large(y: int) -> bool:
    return y > (P - 1) // 2


def g1_decode(data: bytes):
    """A G1 point from 48 bytes, None for infinity; raises Invalid."""
    infinity, sign, x = _flags(data, 48)
    if infinity:
        if sign or x:
            raise Invalid("infinity with bits set")
        return None
    if x >= P:
        raise Invalid("x not reduced")
    y = _sqrt(x * x * x + 4)
    if y is None:
        raise Invalid("not on the curve")
    if _large(y) != sign:
        y = P - y
    point = (x, y)
    if _mul(_FP, point, R) is not None:
        raise Invalid("not in the subgroup")
    return point


def g2_decode(data: bytes):
    """A G2 point from 96 bytes, x's u coefficient first; raises Invalid."""
    infinity, sign, x1 = _flags(data, 96)
    x1, x0 = x1 >> 384, x1 & ((1 << 384) - 1)
    if infinity:
        if sign or x1 or x0:
            raise Invalid("infinity with bits set")
        return None
    if x0 >= P or x1 >= P:
        raise Invalid("x not reduced")
    x = (x0, x1)
    y = _f2_sqrt(_FP2.add(_f2_mul(_f2_mul(x, x), x), (4, 4)))
    if y is None:
        raise Invalid("not on the curve")
    if (_large(y[1]) if y[1] else _large(y[0])) != sign:
        y = ((-y[0]) % P, (-y[1]) % P)
    point = (x, y)
    if _mul(_FP2, point, R) is not None:
        raise Invalid("not in the subgroup")
    return point


def g1_encode(point) -> bytes:
    if point is None:
        return bytes([0xC0]) + bytes(47)
    out = bytearray(point[0].to_bytes(48, "big"))
    out[0] |= 0x80 | (0x20 if _large(point[1]) else 0)
    return bytes(out)


def g2_encode(point) -> bytes:
    if point is None:
        return bytes([0xC0]) + bytes(95)
    (x0, x1), (y0, y1) = point
    out = bytearray(x1.to_bytes(48, "big") + x0.to_bytes(48, "big"))
    out[0] |= 0x80 | (0x20 if (_large(y1) if y1 else _large(y0)) else 0)
    return bytes(out)


# Points in EIP-2537's encoding: each coordinate in Fp as 64 bytes, its top 16 zero; an Fp2
# element c0 + c1 u as c0 then c1; the point at infinity as zeros.


def _fp_2537(data: bytes) -> int:
    if any(data[:16]):
        raise Invalid("padding not zero")
    v = int.from_bytes(data[16:], "big")
    if v >= P:
        raise Invalid("coordinate not reduced")
    return v


def g1_from_2537(data: bytes):
    """A G1 point from EIP-2537's 128 bytes, None for infinity; raises Invalid."""
    if len(data) != 128:
        raise Invalid(f"{len(data)} bytes, not 128")
    x, y = _fp_2537(data[:64]), _fp_2537(data[64:])
    if x == 0 and y == 0:
        return None
    if (y * y - x * x * x - 4) % P:
        raise Invalid("not on the curve")
    if _mul(_FP, (x, y), R) is not None:
        raise Invalid("not in the subgroup")
    return (x, y)


def g2_from_2537(data: bytes):
    """A G2 point from EIP-2537's 256 bytes, None for infinity; raises Invalid."""
    if len(data) != 256:
        raise Invalid(f"{len(data)} bytes, not 256")
    x = (_fp_2537(data[:64]), _fp_2537(data[64:128]))
    y = (_fp_2537(data[128:192]), _fp_2537(data[192:]))
    if x == (0, 0) and y == (0, 0):
        return None
    if _FP2.sub(_f2_mul(y, y), _FP2.add(_f2_mul(_f2_mul(x, x), x), (4, 4))) != (0, 0):
        raise Invalid("not on the curve")
    if _mul(_FP2, (x, y), R) is not None:
        raise Invalid("not in the subgroup")
    return (x, y)


def g1_to_2537(point) -> bytes:
    if point is None:
        return bytes(128)
    return b"".join(bytes(16) + c.to_bytes(48, "big") for c in point)


def g2_to_2537(point) -> bytes:
    if point is None:
        return bytes(256)
    (x0, x1), (y0, y1) = point
    return b"".join(bytes(16) + c.to_bytes(48, "big") for c in (x0, x1, y0, y1))


# Hashing to G1 (RFC 9380, sections 5.3.1, 6.6.2, 6.6.3 and 8.8.1).


def expand_message_xmd(msg: bytes, dst: bytes, length: int) -> bytes:
    ell = -(-length // 32)
    if ell > 255 or length > 65535 or len(dst) > 255:
        raise ValueError("expand_message_xmd out of range")
    dst_prime = dst + bytes([len(dst)])
    b0 = hashlib.sha256(bytes(64) + msg + length.to_bytes(2, "big") + b"\x00" + dst_prime).digest()
    b = hashlib.sha256(b0 + b"\x01" + dst_prime).digest()
    out = b
    for i in range(2, ell + 1):
        b = hashlib.sha256(bytes(x ^ y for x, y in zip(b0, b)) + bytes([i]) + dst_prime).digest()
        out += b
    return out[:length]


def _square(a: int) -> bool:
    return pow(a, (P - 1) // 2, P) in (0, 1)


def _swu(u: int) -> tuple[int, int]:
    """Simplified SWU onto the isogenous curve y^2 = x^3 + A x + B."""
    zu2 = _Z * u * u % P
    tv1 = (zu2 * zu2 + zu2) % P
    if tv1 == 0:
        x1 = _B * _inv(_Z * _A) % P
    else:
        x1 = (-_B) * _inv(_A) * (1 + _inv(tv1)) % P
    gx1 = (x1 * x1 * x1 + _A * x1 + _B) % P
    if _square(gx1):
        x, y = x1, _sqrt(gx1)
    else:
        x = zu2 * x1 % P
        y = _sqrt((x * x * x + _A * x + _B) % P)
    if u % 2 != y % 2:
        y = P - y
    return x, y


def _poly(coeffs, x: int, monic: bool = False) -> int:
    acc = 1 if monic else 0
    for c in reversed(coeffs):
        acc = (acc * x + c) % P
    return acc


def _iso(point: tuple[int, int]) -> tuple[int, int]:
    x, y = point
    xn, xd = _poly(_XNUM, x), _poly(_XDEN, x, monic=True)
    yn, yd = _poly(_YNUM, x), _poly(_YDEN, x, monic=True)
    return xn * _inv(xd) % P, y * yn * _inv(yd) % P


def hash_to_g1(msg: bytes, dst: bytes = DST):
    """hash_to_curve with BLS12381G1_XMD:SHA-256_SSWU_RO_."""
    uniform = expand_message_xmd(msg, dst, 128)
    u0 = int.from_bytes(uniform[:64], "big") % P
    u1 = int.from_bytes(uniform[64:], "big") % P
    q = _add(_FP, _iso(_swu(u0)), _iso(_swu(u1)))
    return _mul(_FP, q, H_EFF)


# The pairing. Fp12 is Fp[w] / (w^12 - 2 w^6 + 2): w^6 = u + 1, so an Fp2
# element a + b u is (a - b) + b w^6, and the twist maps (x, y) on
# y^2 = x^3 + 4 (u + 1) to (x / w^2, y / w^3) on y^2 = x^3 + 4.

_ONE = (1,) + (0,) * 11


def _f12_mul(a, b):
    c = [0] * 23
    for i, ai in enumerate(a):
        if ai:
            for j, bj in enumerate(b):
                c[i + j] += ai * bj
    for k in range(22, 11, -1):
        c[k - 6] += 2 * c[k]
        c[k - 12] -= 2 * c[k]
    return tuple(x % P for x in c[:12])


def _line(t, q, p):
    """The line through t and q (t again if equal), at p, times w^3."""
    if t == q:
        lam = _f2_mul(_f2_mul((3, 0), _f2_mul(t[0], t[0])), _f2_inv(_f2_mul((2, 0), t[1])))
    else:
        lam = _f2_mul(_FP2.sub(q[1], t[1]), _f2_inv(_FP2.sub(q[0], t[0])))
    c0 = _FP2.sub(_f2_mul(lam, t[0]), t[1])
    c2 = _f2_mul(lam, ((-p[0]) % P, 0))
    out = [0] * 12
    out[0], out[6] = (c0[0] - c0[1]) % P, c0[1]
    out[2], out[8] = (c2[0] - c2[1]) % P, c2[1]
    out[3] = p[1]
    return tuple(out)


def _miller(q, p):
    """Miller's loop over |x| for q in G2 and p in G1; lines scaled by w^3, a
    factor of Fp4 that the final exponentiation removes."""
    f, t = _ONE, q
    for bit in bin(X_ABS)[3:]:
        f = _f12_mul(_f12_mul(f, f), _line(t, t, p))
        t = _add(_FP2, t, t)
        if bit == "1":
            f = _f12_mul(f, _line(t, q, p))
            t = _add(_FP2, t, q)
    return f


def _final_exp(f):
    e = (P**12 - 1) // R
    out = _ONE
    for bit in bin(e)[2:]:
        out = _f12_mul(out, out)
        if bit == "1":
            out = _f12_mul(out, f)
    return out


def union_unique(namespace: bytes, msg: bytes) -> bytes:
    """The namespace's length as an unsigned LEB128 varint, the namespace, the message."""
    n, prefix = len(namespace), bytearray()
    while True:
        byte, n = n & 0x7F, n >> 7
        prefix.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(prefix) + namespace + msg


def verify_points(pk, namespace: bytes, msg: bytes, sig) -> bool:
    """Whether e(sig, G2) = e(H(union_unique(namespace, msg)), pk), for points already decoded."""
    if pk is None or sig is None:
        return False
    h = hash_to_g1(union_unique(namespace, msg))
    f = _f12_mul(_miller(G2_GEN, sig), _miller(_neg(_FP2, pk), h))
    return _final_exp(f) == _ONE


def verify(public: bytes, namespace: bytes, msg: bytes, signature: bytes) -> bool:
    """`verify_points` over the compressed encodings, Commonware's `ops::verify_message` for `MinSig`."""
    try:
        return verify_points(g2_decode(public), namespace, msg, g1_decode(signature))
    except Invalid:
        return False


def verify_2537(public: bytes, namespace: bytes, msg: bytes, signature: bytes) -> bool:
    """`verify_points` over EIP-2537's encodings, the key's 256 bytes and the signature's 128."""
    try:
        return verify_points(g2_from_2537(public), namespace, msg, g1_from_2537(signature))
    except Invalid:
        return False


def public_key(secret: int) -> bytes:
    return g2_encode(_mul(_FP2, G2_GEN, secret % R))


def sign(secret: int, namespace: bytes, msg: bytes) -> bytes:
    return g1_encode(_mul(_FP, hash_to_g1(union_unique(namespace, msg)), secret % R))
