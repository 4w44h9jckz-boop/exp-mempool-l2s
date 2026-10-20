# 0015. Sealed floods are measured against an eviction order that keeps what has a place

Date: 2026-10-08. Status: accepted.

## Context

Experiment 07 asks what LU-8's three readings of "no chance of getting
included" admit of a flood of sealed transactions, and how long a cheap
sealed payment waits. A trial run on the network showed that none of the
three keeps payments in a pool against a flood whose transactions each come
first when sent: every policy admits such a transaction, and LU-10, which
drops the last in commitment order, then drops the honest ones. The fault
is in the eviction order as much as in the policy, so the experiment needs
a second order to measure against, and the experiment's own choices of
load, adversary and scale need writing down.

## Decision

1. **An eviction variant, `evict_first` `unplaced`** (LU-1, LU-10). A full
   pool's victim is the last, in commitment order, of the transactions that
   the selection (LU-7) over the pool and the newcomer does not take; the
   newcomer is admitted if it comes before the victim, or if the selection
   takes it and not the victim. What the next block would pass over is what
   has "no chance" now, so it goes first. The selection includes the newcomer
   because a newcomer that pushes a held transaction out of its place should
   drop that one, not one that still has a place. `last` stays the profile's,
   since it is the only order the EIP gives (decision record 0014), and
   `unplaced` is a variant to be measured, as `evict_first` `tip` is for the
   frame pool (decision record 0010).
2. **Two honest loads, read from an earlier explainer of LUCID.** A payment
   bids no ToB fee and tolerates 31 commitments before it, the most a block
   can have, because that explainer reads a private payment as one that pays
   a minimal ToB fee and relies on being uninteresting; it has 100,000 gas
   and 512 bytes. A trade bids a ToB fee
   drawn uniformly between $10^{12}$ and $10^{15}$ wei and tolerates between
   1 and 8 commitments, the range of the explainer's worked example and its
   table of $m$, with 300,000 gas, at 2 a slot. The gas limit is 60,000,000,
   the largest in the explainer's table, so a block commits at most 32 and
   the count binds before the ToB segment's gas does. These are choices, not
   measurements of any deployment.
3. **A flood that tolerates no commitment before it.** A block commits at
   most one such transaction, and only first, so a flood of them costs its
   sender one ticket a block at most. Its transactions use the least gas
   LU-4 allows and are revealed, because a revealed commitment refunds the
   unused gas and $(F-1)/F$ of the ToB fee, which makes revealing the cheaper
   choice. Two kinds: *cheap*, at 1 wei of ToB fee, which stands for any bid
   between the payments' and the honest top; and *escalating*, each 1 wei
   above the last from above every honest bid, so that each comes first when
   it is sent. The flood sends from one sender per transaction, since a pool
   holds one per sender, and stops at a node's first refusal.
4. **The network's pools have 256 slots under a flood**, as experiment 05's
   frame pools do, so that a flood re-sent to every node after every block
   fits the model's budget. Section 1 of the experiment shows the same flood
   against one pool of the profile's 4096 slots, which takes a sender for
   each slot.
5. **Wallets resend after every block that leaves them out, and may
   reseal.** Resending the same sealed transaction does not spread it again,
   because a node never sends a peer a transaction it knows the peer has
   (decision record 0004), and the model's nodes never forget what a peer
   knows. Resealing, encrypting again,
   gives the transaction a new hash and so a new place among those that bid
   the same; it is what decision record 0014's consequence says a sender can
   do and the model did not.

## Consequences

- `06-lucid.md` version 1 carries `evict_first` from the start, with vectors
  for both orders.
- The experiment's numbers depend on the loads above; a deployment with
  payments that bid a ToB fee, or with more than 32 commitments of demand,
  needs its own run.
- Whether `unplaced` should be proposed for the EIP is an open question in
  the plan.
