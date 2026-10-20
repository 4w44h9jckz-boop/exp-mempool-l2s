# 0027. A withheld key costs its sender the ticket, and the sender sends again

Date: 2026-10-09. Status: accepted.

## Context

The plan's item 20 takes the case experiment 07 left out: key publishers
that do not publish. An earlier problem record notes that an encrypted
mempool which waits for a key keeps the chain live by turning encryption
off, for a threshold design, ethresear.ch topic 26040, whose circuit breaker
invalidates every pending ciphertext after too many key-refused slots. The
record names LUCID as the design that queues rather than invalidates, and
sets it beside a second record, under which a withheld key produces a silent
skip while every inclusion check reports success.

EIP-8184 was read again at `258836f9`, and is byte-identical at master
`af80fc1c` (2026-10-09). What it does with a key that never arrives:

- The ticket is charged in block $n$ whatever happens to the key: "Each ST
  ticket is charged", and "ticket.signer.nonce += 1" (Block processing).
- Only a decrypted transaction runs and is refunded: "Upon successful
  decryption ... The unused gas ... is then returned to the sender, together
  with the `parent_tob_fee` reserved for the penalty", and the key fee
  recipient "is further credited" then. A commitment that is not decrypted
  is left out of `decrypted_transactions`. So a sender whose key is
  withheld pays the base fee on its whole gas limit, its priority fee, its
  whole ToB fee and its key fee, and nothing it signed runs.
- The sender has a way round its publisher: "In the case of a single ST,
  the sender may itself also release the `LucidKeyMessage`, even if it
  specified a key publisher other than itself" (Key release).
- And a way out: "withheld transactions can be replaced by regular
  transactions in block $n+1$" (Rationale, Exogenous MEV).
- Nothing stops: block $n+1$ runs the commitments that were decrypted, and
  "When the encrypted mempool is underutilized, the unused gas allocation
  does not encroach on the block gas limit".

## Decision

1. **No clause changes.** LU-12 charges every committed ticket and LU-13
   runs and refunds only a commitment that is `revealed`; the vector
   `conformance/vectors/lucid/lu-13-decrypted.json` already has one that is
   not. Who withholds, and what a sender does next, are the simulator's.
2. **A publisher that withholds withholds every key it is named for**, an
   offline publisher or one that refuses a sender outright. There are ten
   publishers, and a share of them withhold; a sender names one at random
   on each attempt, among those that have not withheld from it before. The
   selective withholding the EIP prices, a trade released only when it
   pays, is not modelled: a payment is never worth withholding for that.
3. **A sender learns of a withheld key at the next head.** The ticket names
   its publisher, and the commitment is missing from the next block's
   decrypted transactions. In the model the sender acts when the block that
   committed its ticket reaches the node it sent to, a few seconds before the
   key deadline; its next attempt can be in block $n+1$.
4. **Two responses are measured**: `sealed`, which sends the payment again as
   a new sealed transaction at the next nonce, re-encrypted, so with a hash
   of its own; and `public`, which sends it as a regular transaction at the
   next nonce, with the same gas, the EIP's way out and the first record's
   trade of encryption for liveness made by one user rather than by the
   protocol.
5. **Self-release is read, not run.** A single sealed payment whose sender
   is online when its commitment lands is never stopped by its publisher, so
   in the model it is a run in which no key is withheld. What it costs is
   being online in that slot, which the model cannot price.
6. **Experiment 07's network, payments and policies.** Withholding takes a
   commitment out of the 32 a block makes without running anything, so it
   moves the ceiling a sealed payment meets; the policies differ only above
   it. A flood that withholds is experiment 07's escalating flood with every
   key withheld.

## Consequences

- In the simulator, `SealedLoad` names a publisher, withholds by publisher
  and sends again, sealed or public; `SealedFlood` can withhold.
- Experiment 18.
