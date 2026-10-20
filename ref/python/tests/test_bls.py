"""BLS12-381 pieces the ticket vectors reach only through whole tickets: hashing to G1 and the encodings."""

import unittest

from emem import bls

# RFC 9380, appendix J.9.1: BLS12381G1_XMD:SHA-256_SSWU_RO_ under its test tag.
QUUX = b"QUUX-V01-CS02-with-BLS12381G1_XMD:SHA-256_SSWU_RO_"
HASH_TO_G1 = (
    ("",
     0x052926add2207b76ca4fa57a8734416c8dc95e24501772c814278700eed6d1e4e8cf62d9c09db0fac349612b759e79a1,
     0x08ba738453bfed09cb546dbb0783dbb3a5f1f566ed67bb6be0e8c67e2e81a4cc68ee29813bb7994998f3eae0c9c6a265),
    ("abc",
     0x03567bc5ef9c690c2ab2ecdf6a96ef1c139cc0b2f284dca0a9a7943388a49a3aee664ba5379a7655d3c68900be2f6903,
     0x0b9c15f3fe6e5cf4211f346271d7b01c8f3b28be689c8429c85b67af215533311f0b8dfaaa154fa6b88176c229f2885d),
    ("abcdef0123456789",
     0x11e0b079dea29a68f0383ee94fed1b940995272407e3bb916bbf268c263ddd57a6a27200a784cbc248e84f357ce82d98,
     0x03a87ae2caf14e8ee52e51fa2ed8eefe80f02457004ba4d486d6aa1f517c0889501dc7413753f9599b099ebcbbd2d709),
    ("q128_" + "q" * 128,
     0x15f68eaa693b95ccb85215dc65fa81038d69629f70aeee0d0f677cf22285e7bf58d7cb86eefe8f2e9bc3f8cb84fac488,
     0x1807a1d50c29f430b8cafc4f8638dfeeadf51211e1602a5f184443076715f91bb90a48ba1e370edce6ae1062f5e6dd38),
    ("a512_" + "a" * 512,
     0x082aabae8b7dedb0e78aeb619ad3bfd9277a2f77ba7fad20ef6aabdc6c31d19ba5a6d12283553294c1825c4b3ca2dcfe,
     0x05b84ae5a942248eea39e1d91030458c40153f3b654ab7872d779ad1e942856a20c438e8d99bc8abfbf74729ce1f7ac8),
)


class HashToG1(unittest.TestCase):
    def test_rfc_9380_vectors(self):
        for msg, x, y in HASH_TO_G1:
            with self.subTest(msg=msg[:12]):
                self.assertEqual(bls.hash_to_g1(msg.encode(), QUUX), (x, y))


class Points(unittest.TestCase):
    def test_generator_is_in_g2(self):
        self.assertIsNotNone(bls.G2_GEN)
        self.assertIsNone(bls._mul(bls._FP2, bls.G2_GEN, bls.R))
        self.assertEqual(bls.g2_decode(bls.g2_encode(bls.G2_GEN)), bls.G2_GEN)

    def test_round_trips(self):
        for secret in (1, 2, bls.R - 1):
            with self.subTest(secret=secret):
                pk = bls.public_key(secret)
                self.assertEqual(bls.g2_encode(bls.g2_decode(pk)), pk)
                sig = bls.sign(secret, b"ns", b"m")
                self.assertEqual(bls.g1_encode(bls.g1_decode(sig)), sig)
                self.assertTrue(bls.verify(pk, b"ns", b"m", sig))

    def test_eip_2537_round_trips(self):
        pk = bls.g2_decode(bls.public_key(7))
        self.assertEqual(bls.g2_from_2537(bls.g2_to_2537(pk)), pk)
        sig = bls.g1_decode(bls.sign(7, b"ns", b"m"))
        self.assertEqual(bls.g1_from_2537(bls.g1_to_2537(sig)), sig)
        self.assertTrue(bls.verify_2537(bls.g2_to_2537(pk), b"ns", b"m", bls.g1_to_2537(sig)))
        self.assertIsNone(bls.g1_from_2537(bytes(128)))

    def test_eip_2537_generator(self):
        """EIP-2537 lists G2's generator coordinate by coordinate, c0 before c1."""
        enc = bls.g2_to_2537(bls.G2_GEN)
        self.assertEqual(enc[16:64].hex()[:8], "024aa2b2")
        self.assertEqual(enc[80:128].hex()[:8], "13e02b60")

    def test_a_point_of_order_3_is_refused(self):
        with self.assertRaises(bls.Invalid):
            bls.g1_decode(bls.g1_encode((0, bls.P - 2)))

    def test_union_unique_prefixes_a_varint(self):
        self.assertEqual(bls.union_unique(b"FRAME_TICKET_V1", b"m"), b"\x0fFRAME_TICKET_V1m")
        self.assertEqual(bls.union_unique(b"x" * 200, b"")[:2], bytes([0xC8, 0x01]))


if __name__ == "__main__":
    unittest.main()
