# 0002. The account-nonce pool is go-ethereum's, transcribed

Date: 2026-10-07. Status: accepted.

## Context

No EIP specifies the pool for transaction types 0 to 4. Each client has its
own. An experiment needs one pool whose behaviour is known exactly, and the one
most of the network runs is go-ethereum's `legacypool`.

## Decision

1. `docs/spec/01-nonce-pool.md` transcribes go-ethereum's `legacypool` at
   commit `93d78a01` (2026-10-06) with `DefaultConfig`, including behaviour
   that looks accidental: a batch is admitted before it is promoted, so one
   batch can over-commit a balance (NP-5); eviction between promotion runs is
   capped at a quarter of `global_slots` (NP-9); pending truncation counts
   transactions while the capacity check counts slots (NP-9, NP-16). These are
   what the network does, and an experiment about the network needs them.
2. Where go-ethereum leaves an outcome to its runtime, the specification
   chooses and says so. Ties between equally priced transactions go against
   the later-received for eviction and in favour of the earlier-received for
   inclusion; ties between senders go by address (MD-10). Go uses
   `container/heap` and randomised map iteration for these.
3. Time is an input. go-ethereum's eviction ticker becomes passes at fixed
   multiples of `eviction_interval`, which every operation runs first if they
   have fallen due (NP-18). Promotion, which go-ethereum runs asynchronously
   after an `Add`, runs synchronously at the end of each batch, as go-ethereum's
   own tests run it.
4. What is left out is listed under *Not modelled* in NP-19: deep reorgs and
   reinjection, the Osaka boundary, local transactions and the journal. The
   blob pool is a separate subpool to be added when an experiment needs it.

## Consequences

The pool can be compared with a running go-ethereum node, and the vectors are
written so that one could drive a node with them. Where another client
differs, that is a second profile, as for the frame pool, not an edit to this
one.
