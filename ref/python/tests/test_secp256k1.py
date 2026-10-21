"""secp256k1 recovery, which CG-12 reaches only through whole transactions."""

import unittest

from emem import secp256k1

# A signature over a frame transaction's signature hash, made by exp-frames' signer (viem) at 85ee60d for
# conformance/vectors/claim-gated/cg-12-bound-copies.json, and the address of the key that made it.
DIGEST = bytes.fromhex("c560a1895327fe2463707ee3db0be5671600c932118d9f8ee8344d3742246c03")
SIGNATURE = bytes.fromhex("01cbb8de9b503adb711dc921de30e7e1d176872fc99fd938a550bf2f23439354c169ccd1692b90ab4dac27ad23fcde80fa73f6e1d3e061459c0104c948c6af9152")
SIGNER = bytes.fromhex("4960d61e699ab1daf195b1a3ee8bdcede2b6a80c")


class Recover(unittest.TestCase):
    def test_known_addresses(self):
        # The addresses of private keys 1 and 2, as every Ethereum library gives them.
        self.assertEqual(secp256k1.address(1).hex(), "7e5f4552091a69125d5dfcb7b8c2659029395bdf")
        self.assertEqual(secp256k1.address(2).hex(), "2b5ad5c4795c026514f8317c7a215e218dccd6cf")

    def test_a_signature_another_library_made(self):
        v, r, s = SIGNATURE[0], int.from_bytes(SIGNATURE[1:33], "big"), int.from_bytes(SIGNATURE[33:], "big")
        self.assertEqual(secp256k1.recover(DIGEST, v, r, s), SIGNER)
        self.assertNotEqual(secp256k1.recover(DIGEST, 1 - v, r, s), SIGNER)
        self.assertNotEqual(secp256k1.recover(bytes(32), v, r, s), SIGNER)

    def test_out_of_range(self):
        v, r, s = SIGNATURE[0], int.from_bytes(SIGNATURE[1:33], "big"), int.from_bytes(SIGNATURE[33:], "big")
        for bad in ((2, r, s), (v, 0, s), (v, r, 0), (v, secp256k1.N, s), (v, r, secp256k1.N)):
            self.assertIsNone(secp256k1.recover(DIGEST, *bad))


if __name__ == "__main__":
    unittest.main()
