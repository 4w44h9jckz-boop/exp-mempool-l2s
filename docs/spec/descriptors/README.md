# Descriptors

The three descriptors of `docs/spec/13-descriptors.md`, DS-8. A file may be
written with any whitespace and member order; its identifier is that of its
canonical encoding (DS-2, DS-3), and a change to any value changes it.

| File | Identifier | Parent |
| --- | --- | --- |
| `eip-8141.json` | `bafkreic7kyifykopewlbznmhicjvfrmbxhmfwaaxglrdcgrttm2qw5blb4` | none |
| `claim-gated.json` | `bafkreid2yhoz2it5mzjhejpm2f3tthv5npcvxaahxujjhds63mwfpx4ahm` | `eip-8141.json` |
| `erc-8421.json` | `bafkreieanbgdpq22vtfsa4rz4zll2lhf4qofoi75hbubqqhlqzepvyvjsy` | `eip-8141.json` |

The identifiers were computed outside this repository's reference, by a
canonical encoder and a base32 written in TypeScript over `@noble/hashes`'
SHA-256, and checked against Python's `base64`; the descriptor vectors
(`conformance/vectors/descriptors/`) hold them.
