# 0005. A shared sender is measured with a relayer and without, against a one-knob variant

Date: 2026-10-07. Status: accepted.

## Context

The plan's item 1 asks for spends an hour against demand for a shared sender
under FP-12's `one` and `disjoint-keys`, "with the wallet waiting rule of
`FrameLoad`". Three things are left open by that sentence.

- **Who submits.** A wallet that waits for its last transaction's inclusion is
  well defined when the wallet is the sender. When the sender is a pool and the
  users are many, either somebody holds the queue (a relayer) or the users
  submit their own spends and find out from the node's answer.
- **Which `disjoint-keys`.** The `hegota-testnet` profile has
  `per_sender = disjoint-keys`, but it also differs from `eip-8141` in three
  other knobs, and which `per_sender` value the live testnet runs is disputed:
  `exp-frames` reports `disjoint-keys` on 2026-10-07, while an earlier
  measurement found `one` on 2026-09-10 and again on the relaunched chain on
  2026-09-18.
- **What the spend is.** EIP-8250's leading example is a single shared sender,
  and an earlier design study's voucher pool is the worked instance.

## Decision

1. **Two submission rules.** `relayer` is `FrameLoad`'s rule held by one party
   per sender: send the next spend when your node imports the block that
   included the last, and under `disjoint-keys`, where nothing is refused, send
   each at once. `direct` users submit their own spend to a random node and
   resubmit it to a random node after every block that does not include it.
   The relayer optionally waits a fixed time after its import, because the
   first runs showed that sending at the instant of import races the block.
2. **The comparison changes one knob.** `disjoint-keys` is `eip-8141` with
   `per_sender = disjoint-keys` and nothing else, so a difference is FP-12's.
   The spend reaches none of the other three knobs: its prefix uses 17,800 of
   the 100,000 verification gas, no state gas, and its payer is its sender.
3. **The spend is the voucher pool's without its expiry frame**: the pool
   is the sender and pays, its nullifier is a fresh nonce key at sequence 0, and
   one signature entry by the user commits the fees. The expiry frame's deadline
   is an epoch away and would play no part.
4. **Exposure is measured from the first submission to any node**, because
   that is when a node holds the nullifier, whether or not it admits it. A
   relayer learns each spend earlier, at the user's request; that is a cost of
   trusting the relayer and is not in the number.

## Consequences

- The experiment can separate the ceiling (a property of FP-12) from what a
  submitter does about it, which is where the privacy cost moves.
- A user who submits directly is assumed to know only the answer of the node
  it submitted to and the blocks its node imports, and to have no relayer it
  trusts. A wallet that reads the public mempool and backs off would sit
  between the two rules and is not measured.
