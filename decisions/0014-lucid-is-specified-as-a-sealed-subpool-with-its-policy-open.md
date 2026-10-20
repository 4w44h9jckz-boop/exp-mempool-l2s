# 0014. LUCID is specified as a sealed subpool, with its admission policy left open as a parameter

Date: 2026-10-08. Status: accepted.

## Context

The plan's item 10 asks what an admission policy for EIP-8184's sealed
transactions admits of spam and of transactions a block can include, and how
long a cheap sealed payment waits. The EIP is Draft, read from ethereum/EIPs
at `258836f9`. It specifies the sealed transaction, the ticket's charge, the
order of commitments, the limits of the ToB segment and the next block's
refund. It does not specify a mempool beyond two sentences: "The mempool must
naturally protect against spam and reject STs that have no chance of getting
included" (Rationale), and "there are no fixed settings that can be
established at this point for STs that should or should not be propagated"
(Security Considerations). `docs/spec/06-lucid.md` turns the rules a pool can
read into clauses, and this record is where it says which readings it took.

## Decision

1. **A third subpool behind the reservation tracker.** A sealed transaction
   is a new EIP-2718 type whose ticket "consumes the sender's execution
   nonce" (ST ticket). A pool that held it beside the sender's account-nonce
   transactions would have to decide which of the two a nonce belongs to;
   go-ethereum solves that for its blob pool by holding a sender in one
   subpool at a time (`core/txpool/reserver.go`), which MD-11 already
   models. The sealed pool is that subpool, and its profile `off` refuses
   every sealed transaction (`00-model.md` version 4, MD-11).
2. **No queue.** A sealed transaction is admitted only at its sender's
   current nonce and only one per sender (LU-5, LU-9), as a frame
   transaction is (FP-7). A ticket at a future nonce cannot be charged in the
   next block, which is what "no chance of getting included" is read as.
3. **What the EIP's validity rules imply is normative; the policy is a
   parameter.** LU-4 and LU-5 refuse a ticket the next block could not
   charge (nonce, balance, `max_fee >= base_fee + key_publication_fee`) and
   one whose gas limit exceeds the ToB segment, which no block can take.
   Beyond that, three readings of "no chance" are kept as `policy` (LU-8):
   `any` refuses nothing more; `next-block` refuses one the next block's
   selection would pass over when it arrives; `every-head` re-applies that
   at every head, so that a pool never holds more than one block's
   commitments. The profile takes `any`, because the EIP says no setting can
   be fixed yet, and the experiment measures all three.
4. **The calldata check is $64s$ gas for $s$ bytes, with no base.** The EIP
   requires the gas limit to "cover the calldata cost of the byte size of the
   `SealedTransaction`" and derives `MAX_BYTES_PER_ST = 2**24 // 64` as the
   "Byte bound implied by EIP-7976 and EIP-7825". That bound is exact only
   if the cost is 64 per byte and nothing else (LU-4).
5. **A builder selects greedily in commitment order** (LU-7). The EIP fixes
   the order of commitments, by ToB fee, then gas, then root, but not which
   ones a builder takes. Its attesters vote against a block that leaves out
   an inclusion-list entry that "could be placed in `st_commitments` at the
   position determined by the ST-commitment ordering rule without violating
   its `max_preceding_commitments`". Taking candidates in that order and
   keeping each one that fits is the rule that check enforces, applied to
   everything the builder holds as though it had been listed. A builder
   maximising its own revenue could do otherwise, because the ToB fee is
   burned or refunded and only the priority fee is its own; that is a
   strategy, not a rule, and is left out.
6. **Replacement bumps three prices** (LU-9). The EIP says nothing of it.
   go-ethereum's legacy pool asks a dynamic-fee transaction to raise its fee
   cap and tip by `PriceBump` percent; a ticket's position depends on its ToB
   fee as well, so that is bumped too, and a replacement that kept a ToB fee
   of zero still passes.
7. **A full pool evicts the last in commitment order** (LU-10). It is the
   only order the EIP gives, and it is the order the builder takes, so the
   transaction evicted is the one a block would take last. `st_slots` is
   4096, as FP-1's `max_pending`, for want of any figure in the EIP.
   Decision record 0015 adds a variant, `unplaced`, that drops first what
   the next block would pass over.
8. **A new head re-applies LU-5** (LU-11), as FP-15 re-applies the frame
   pool's checks, and under `every-head` the policy as well.
9. **Tickets take no gas of their own block; decrypted transactions take the
   next block's** (LU-12, LU-13). The EIP charges tickets in block $n$ and
   executes the decrypted transactions at the top of block $n+1$; it says
   the unused allocation "does not encroach on the block gas limit", which
   reads as the used part counting against it. The ticket, which is never
   executed, is given no gas.
10. **A commitment's hash is the transaction's hash.** The model has one hash
    per transaction (MD-7), and commitments of standalone STs order by their
    `ticket_hash`. Vectors do not depend on the hash order, which a reader
    cannot compute by hand.

## Consequences

- An experiment can set `policy` and report what each reading admits and
  refuses, without any being called the EIP's.
- Because the commitment order breaks a tie in ToB fee by gas and then by
  hash, transactions that all pay no ToB fee and use the same gas are taken
  in hash order, which neither the sender nor the pool chooses. A sender can
  change its hash by re-encrypting; the model does not.
- The reference gains a sealed transaction type, a sealed pool and two steps
  in the builder (`ref/python/emem/sealed.py`,
  `ref/python/emem/sealedpool.py`, `ref/python/emem/block.py`).
- If the EIP fixes any of these points, the clause that read it changes and
  `06-lucid.md` bumps its version.
