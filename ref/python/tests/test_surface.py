"""The surface's own pieces that the vectors reach only through whole transactions: keccak256 and RLP."""

import unittest

from emem import errors as E
from emem.errors import TxError
from emem.framepool.config import PROFILES
from emem.keccak import keccak256
from emem.surface import SURFACE_PROFILES, Malformed, _item, decode


class Keccak(unittest.TestCase):
    def test_known_answers(self):
        self.assertEqual(keccak256(b"").hex(), "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        self.assertEqual(keccak256(b"abc").hex(), "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")

    def test_block_boundaries(self):
        """135, 136 and 137 bytes straddle the rate: padding fits, fills a block, or spills."""
        hashes = {keccak256(b"\x61" * n) for n in (135, 136, 137, 272)}
        self.assertEqual(len(hashes), 4)


class Rlp(unittest.TestCase):
    def test_canonical_forms(self):
        self.assertEqual(_item(b"\x7f", 0), (b"\x7f", 1))
        self.assertEqual(_item(b"\x81\x80", 0), (b"\x80", 2))
        self.assertEqual(_item(b"\xc2\x01\x02", 0), ([b"\x01", b"\x02"], 3))
        long = b"\xb8\x38" + b"\x01" * 56
        self.assertEqual(_item(long, 0), (b"\x01" * 56, 58))

    def test_non_canonical_forms(self):
        for bad in (b"\x81\x7f", b"\xb8\x05" + b"\x01" * 5, b"\xb9\x00\x38" + b"\x01" * 56, b"\xc3\x01\x02", b"\x82\x01"):
            with self.subTest(bad=bad.hex()), self.assertRaises(Malformed):
                _item(bad, 0)

    def test_decode_refuses_in_order(self):
        cfg, scfg = PROFILES["eip-8141"], SURFACE_PROFILES["eip-8141"]
        for raw, code in ((b"", E.ErrTxTypeNotSupported), (b"\x06", E.ErrFrameDecode),
                          (b"\x06\xc0", E.ErrFrameDecode), (b"\x06" + b"\x00" * 200000, E.ErrOversizedData)):
            with self.subTest(raw=raw[:4].hex()), self.assertRaises(TxError) as ctx:
                decode(raw, cfg, scfg)
            self.assertEqual(ctx.exception.code, code)


if __name__ == "__main__":
    unittest.main()
