# 0011. The expiry check is measured at the head and at the next slot, against three adversaries

Date: 2026-10-08. Status: accepted.

## Context

The plan's item 5 asks how many expiring transactions a pool admits though no
block can include them, under the head's timestamp and under the next slot's.
EIP-8141's expiry verifier "reverts unless `block.timestamp <=
expiry_timestamp`" (Expiry Verifier Frame), and its mempool section drops a
transaction whose deadline "is less than the node's view of the current
block timestamp at any point" (Mempool, Expiry Verifier Frame, at
`258836f9`), without saying which block is current. FP-8 and FP-15 have read
it as the head since version 1. Experiment 04 found the transactions this
admits to be an adversary's best tool under a tip-first eviction order and
concluded that closing both of its floods needs the tip order and the next
slot's check; that conclusion is what this experiment tests.

## Decision

1. **`expiry_margin`, seconds added to the head's timestamp in FP-8 and
   FP-15 step 2.** `02-frame-pool.md` version 4. A number rather than a
   switch, because three readings are in use: 0, the head, which both
   profiles keep; the slot time, the block being built, which a client knows
   from its chain configuration; and 1, which is what MA-6's check 3 amounts
   to ("above the head's `timestamp`", decision record 0007). The experiments
   set 0 and 12.
2. **The profiles keep the head.** The EIP's words admit both readings. The
   head is how go-ethereum's pool names the current block (`CurrentBlock`,
   "the current head of the chain", `core/txpool/txpool.go` at `93d78a01`),
   and changing the profiles would change what every experiment so far has
   measured. The next slot's reading is reported as a variant, as `tip` is.
3. **Three adversaries, the ways a transaction can be valid at the head and
   not in the next block.** *Free*, experiment 04's, below every builder's
   price. *Expiring*, at the earliest deadline the pool admits, the head's
   timestamp plus `expiry_margin`: with a margin of 0 the next block cannot
   meet it, with the slot time it can, so the next slot's check turns it
   into a transaction that pays. *Drained*, paid by one default-code sponsor
   that sends its own balance away in the next block, in an account-nonce
   pool transfer at a higher tip. The EIP leaves such a sponsor uncapped: it
   "is not a paymaster and is governed by the per-payer exposure rule alone"
   (Replacement and Eviction); FP-13 does not stop the transfer, because the
   sponsor sends no frame transaction; and `hegota-testnet`'s
   `cap_codeless_payers` does stop it. The drained kind is in this
   experiment because without it the next slot's check would be reported as
   closing the pool to transactions no block includes, which it does not.
4. **The network section shrinks the pool to 256 and the flood to ten
   minutes.** An expiring or drained flood must be made afresh at every head
   and sent to every node, and every admission runs a prefix in the
   reference, which at 4096 is several minutes of wall clock a run. The
   mechanism does not depend on the pool's size once the pool is full, and
   section 1 shows it at 4096. Ten minutes rather than experiment 04's
   twenty because a flood that pays raises the base fee by about an eighth a
   block, and the cost of twenty minutes says more about the base fee
   formula than about the pool. The adversary is as fast as the node
   (decision record 0010).
5. **A transaction no block can include is counted at admission**: an
   admission, at any node, of a transaction whose deadline is below the
   timestamp of the next block built after it. Blocks are built every slot
   at their own timestamp with no slot missed (`sim/emem_sim/chain.py`), so
   that block's timestamp is the next multiple of the slot time.
6. **Honest deadlines use experiment 04's burst**, at the profiles' 4096,
   under both orders and both readings, so that the included sets can be
   compared transaction by transaction.

## Consequences

- The next slot's check is measured as what it is, a fix for one of three
  floods: it makes the expiring flood pay for every block it fills, and
  leaves the drained flood, which costs one transfer a block, untouched.
  What closes that one is a count cap on codeless payers, which the EIP's
  text rules out and the testnet applies.
- `simulate` takes the margin as an argument, so that a block being built
  checks deadlines against its own timestamp whatever the pool's margin is
  (`ref/python/emem/framepool/prefix.py`).
- The simulator's `FloodLoad` gains the drained kind and gives the expiring
  kind the pool's margin; experiment 04's floods are unchanged and its
  results reproduce.
