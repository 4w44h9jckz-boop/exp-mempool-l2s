# 0006. FEE-4 prices the EIP-8250 nonce fields, and the floor counts them as tokens

Date: 2026-10-07. Status: accepted.

## Context

Version 1 of `docs/spec/00-model.md` priced a frame transaction's frame data
and signature bytes as EIP-8141 does, and nothing else. EIP-8250 at the
commit `docs/spec/README.md` pins replaces EIP-8141's `nonce` with
`nonce_keys` and `nonce_seq` and prices their encoding as data, in its section
"Transaction payload":

```text
nonce_calldata = rlp(nonce_keys) || rlp(nonce_seq)
nonce_calldata_cost = calldata_cost(nonce_calldata)
nonce_calldata_tokens = tokens_in(nonce_calldata)
```

with `nonce_calldata_cost` added to `standard_gas_limit` and
`nonce_calldata_tokens` added to `calldata_tokens`. The omission was found
while reading what MATCHA's `admission_gas` covers for experiment 02: it names
"transaction data" and "EIP-8250 nonce checks", so a charge computed from
version 1 would be short by the nonce bytes, and for a spend whose nonce key
is a 256-bit nullifier that is 35 bytes, 560 gas of intrinsic cost and 2240 of
floor.

Two readings of the floor are possible. EIP-8250 adds `tokens_in` of the
nonce bytes, the weighted count in which a zero byte is one token and any
other byte four, to `calldata_tokens`. EIP-8141 at the same commit has no
quantity of that name: its floor sums `floor_tokens_in`, four tokens for every
byte, into `calldata_floor_tokens`, following EIP-7976. EIP-8250 was
presumably written against an earlier EIP-8141 in which one token count served
both purposes.

## Decision

1. $D$ in FEE-4 gains $N$, the length of the canonical RLP encoding of the two
   nonce fields, counted as non-zero bytes like every other byte in the model.
   Version 2 of `00-model.md` gives $N$ as a formula, so that a vector can be
   checked by hand.
2. The floor gains $4N$ tokens. Under the model's assumption that every byte
   is non-zero, `tokens_in` and `floor_tokens_in` agree, so the choice between
   the two readings above makes no difference here; it is recorded because a
   model that counted zero bytes would have to make it.
3. The first-use state gas of a keyed nonce is listed as *Not modelled*,
   because the model has no state-gas dimension.
4. The vectors of FEE-4 are corrected by hand against version 2 and gain cases
   for the encoding's boundaries (an integer of 127 and of 128, a list of 55
   and of more than 55 bytes). Pool vectors whose expectations rest on a frame
   transaction's `max_cost` are re-derived by hand where version 2 moves them.

## Consequences

- Every frame transaction in every experiment costs 48 more intrinsic gas at
  the default nonce fields, and the spends of experiment 01, whose nonce keys
  are small integers, 48 to 80 more. Experiments 00 and 01 are regenerated in
  the same commit and their READMEs corrected.
- An EIP-8250 nonce key derived from a hash is 32 bytes, and its encoding is
  then the largest part of a small transaction's data after the signature.
  Experiment 02 uses such keys.
