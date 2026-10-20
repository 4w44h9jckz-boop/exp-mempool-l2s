# 0010. Eviction order is measured against transactions no builder includes, and against a tip-first variant

Date: 2026-10-08. Status: accepted.

## Context

The plan's item 4 asks what a flood of cheap transactions without a deadline
costs and what it displaces, given that FP-14 evicts "transactions with the
nearest expiry deadline, then transactions with the lowest effective priority
fee" (EIP-8141, Replacement and Eviction, at `258836f9`), and the same for
NP-9's underpriced eviction in the account-nonce pool. A pool evicts only when
it is full, so the question is what a newcomer must be to push a held
transaction out, and the cheapest newcomer is one that is never included and
so never pays. The sentence in the plan leaves open what such a transaction
is, how fast the adversary is, how honest wallets behave, and what to compare
the EIP's order with.

## Decision

1. **A variant of FP-14 with the effective tip first.** `02-frame-pool.md`
   version 3 adds `evict_first`, `expiry` in both profiles, as the EIP says.
   With `tip` the victim is the lowest effective tip, then the nearest
   deadline, then the latest received: the order a builder includes by
   (BB-2) and the account-nonce pool's urgent heap evicts by (NP-10), with the
   deadline kept as a tie-break. It is a proposal measured, not a reading of
   the EIP, and the experiment's README says so wherever it reports it.
2. **"Already invalid against the current head" stays empty.** The EIP uses
   the phrase for a prefix that no longer approves, in the paragraph on block
   producers that follows the eviction order. Reading a fee cap below the base
   fee into it would make a 1-wei transaction the first victim, but FP-3
   admits one and the mempool section sets no fee floor, and the same reading
   would evict a stranded backlog before anything else. FP-14 keeps its
   version 1 reading and now says why.
3. **Three kinds of transaction no builder includes**, each from a
   default-code sender of its own and paid for by a canonical paymaster
   instance, which no profile caps (experiment 03): *free*, a fee cap and tip
   of 1 wei, below the base fee and the builders' minimum tip; *sub-minimum*,
   a tip one wei below BB-1's default minimum and a fee cap above the base
   fee; and *expiring*, a deadline at the head's timestamp, which FP-8 admits
   and the next block cannot meet (FP-15's open question), at a tip above
   every honest one. The network sections use *free* only. An *expiring*
   flood must be sent afresh to every node at every block, which the model
   affords at one pool but not for twenty minutes on ten nodes; it belongs
   with the expiry timestamp question (the plan's item 5), and section 1
   measures what each one displaces.
4. **The adversary is as fast as the node.** At the start, and in the same
   instant a node imports a block, it sends that node directly what fills the
   pool and 16 more, so that whatever slipped in since is evicted. Its
   bandwidth is unlimited, as everyone's is in the model. This is the
   strongest adversary; a real one leaves a window of about a link's latency
   after each block.
5. **Honest wallets resend after every block and give up at their deadline.**
   This is the most forgiving wallet, for which an eviction costs a block
   rather than the transaction. Half of the transactions carry a deadline 10
   minutes out, tips are the simulator's default, and wallets pay for
   themselves with default code, so that no shared payer or sender code
   enters the result.
6. **One pool is filled at capacity in equal shares.** Section 1's honest
   transactions are a third each of three classes in the frame pool (half each
   of two in the account-nonce pool, which has no deadlines), one sender each,
   up to the profile's capacity: `max_pending`, 4096, and
   `global_slots + global_queue`, 6144, every transaction one slot.

## Consequences

- The numbers are for the strongest adversary and the most forgiving wallet.
  A slower adversary lets some deadline transactions in after each block; a
  wallet that does not resend loses an evicted transaction for good.
- `evict_first` `tip` closes the free flood and opens the expiring one, which
  only an admission check against the next block's timestamp closes. That is
  FP-15's open question, so the variant is reported as half an answer.
- FP-14 gains an open question: whether a deadline should rank before price.
- To run a full pool for an hour on ten nodes, the reference indexes pending
  frame transactions by the addresses they read and states share unchanged
  accounts with their copies (`ref/python/emem/framepool/pool.py`,
  `ref/python/emem/model.py`). No clause changes; every vector and experiment
  reproduces unchanged, and `ref/python/tests/test_invariants.py` checks the
  index and the eviction heap against a recomputation.
