#!/usr/bin/env python3
"""A stub of `exp-e2e-frames` experiment 19's prover (`prover/src/main.rs` at `47f5496`), for AG-11's vectors.

It keeps the prover's contract and not its cryptography (decision record 0083):

    prover-stub.py aggregate <claims.json> <out.bin>
    prover-stub.py verify-aggregate <proof.bin> <claims.json>
    prover-stub.py sphincs <seed hex> <message hex>   (a key and a signature, as the prover's own mode makes them)
    prover-stub.py verify-sphincs <publicKey hex> <message hex> <signature hex>   (11-surface.md, SF-10; the prover's
                                                                                  mode since 3209255)

Like the prover, it reads hex with or without 0x, and `sphincs` prints its key and signature as bare hex.

Each prints one JSON line; a refusal is `{"error": ...}` and exit status 2. A claim's `publicKey` and `message` are
32 bytes of hex. Its stand-in signature is SHA-256 over b"stub-leanSPHINCS", the key and the message; the stand-in
aggregate is b"stub-aggregate" followed by SHA-256 over the sorted, deduplicated keys and messages, each key
before its message; and the stand-in key of a 32-byte seed is SHA-256 over b"stub-key" and the seed.
"""

import hashlib
import json
import sys


def refuse(why: str) -> None:
    print(json.dumps({"error": why}))
    sys.exit(2)


def raw(claim: dict, field: str, size: int | None = None) -> bytes:
    value = claim.get(field)
    if not isinstance(value, str):
        refuse(f"no {field}")
    try:
        out = bytes.fromhex(value.removeprefix("0x"))
    except ValueError:
        refuse(f"{field} is not hex")
    if size is not None and len(out) != size:
        refuse(f"a {size}-byte {field}")
    return out


def signature(key: bytes, message: bytes) -> bytes:
    return hashlib.sha256(b"stub-leanSPHINCS" + key + message).digest()


def aggregate_of(pairs: list[tuple[bytes, bytes]]) -> bytes:
    return b"stub-aggregate" + hashlib.sha256(b"".join(k + m for k, m in sorted(set(pairs)))).digest()


def claims_of(path: str) -> list:
    try:
        with open(path) as f:
            claims = json.load(f)
    except (OSError, ValueError):
        refuse("the claims")
    if not isinstance(claims, list):
        refuse("a list of claims")
    return claims


def main() -> None:
    args = sys.argv[1:]
    if len(args) == 3 and args[0] == "aggregate":
        pairs = []
        for c in claims_of(args[1]):
            key, message = raw(c, "publicKey", 32), raw(c, "message", 32)
            if raw(c, "signature") != signature(key, message):
                refuse("a signature that does not open at its message")
            pairs.append((key, message))
        proof = aggregate_of(pairs)
        with open(args[2], "wb") as f:
            f.write(proof)
        print(json.dumps({"claims": len(pairs), "proofBytes": len(proof), "aggregateMs": 0.0, "peakRssBytes": 0}))
    elif len(args) == 3 and args[0] == "verify-aggregate":
        try:
            with open(args[1], "rb") as f:
                proof = f.read()
        except OSError:
            refuse("the proof")
        pairs = [(raw(c, "publicKey", 32), raw(c, "message", 32)) for c in claims_of(args[2])]
        if proof != aggregate_of(pairs):
            refuse("the proof does not cover these claims")
        print(json.dumps({"verified": True, "verifyMs": 0.0}))
    elif len(args) == 4 and args[0] == "verify-sphincs":
        key, message = raw({"publicKey": args[1]}, "publicKey", 32), raw({"message": args[2]}, "message", 32)
        sig = raw({"signature": args[3]}, "signature")
        print(json.dumps({"verified": sig == signature(key, message), "verifyMs": 0.0}))
    elif len(args) == 3 and args[0] == "sphincs":
        seed, message = raw({"seed": args[1]}, "seed", 32), raw({"message": args[2]}, "message", 32)
        key = hashlib.sha256(b"stub-key" + seed).digest()
        sig = signature(key, message)
        print(json.dumps({"publicKey": key.hex(), "signature": sig.hex(), "signatureBytes": len(sig),
                          "verified": True}))
    else:
        print("usage: prover-stub.py aggregate <claims.json> <out.bin> | verify-aggregate <proof.bin> <claims.json> "
              "| sphincs <seed> <message> | verify-sphincs <publicKey> <message> <signature>", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
