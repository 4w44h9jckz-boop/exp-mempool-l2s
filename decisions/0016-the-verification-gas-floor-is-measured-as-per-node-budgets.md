# 0016. The verification gas floor is measured as per-node budgets, with hints the wire protocol does not have

Date: 2026-10-08. Status: accepted.

## Context

ethereum/EIPs pull request 12301, "Update EIP-8141: define `MAX_VERIFY_GAS`
as a shared mempool floor", is open. Read on 2026-10-08 at its head,
`f3538f20` (2026-09-29), it keeps the value at 100,000 and changes what it
is: "A public-mempool node MUST NOT reject a frame transaction, or decline to
propagate it, solely because of its validation work while the
validation-prefix budget of structural rule 6 ... is at or below
`MAX_VERIFY_GAS`", and "A node MAY additionally admit transactions whose
validation-prefix budget exceeds the floor when its own capacity allows, as
local headroom." It says what happens above the floor: such a transaction
"still propagates, but only across the subset of nodes whose headroom accepts
it, so the heavier its validation work the fewer nodes carry it and the
slower it diffuses, without ever being dropped network-wide". It leaves a
budget carried in announcements to "a future version of the eth wire
protocol".

The specification reads EIP-8141 at `258836f9`, where `MAX_VERIFY_GAS` is a
cap (FP-6). The plan's item 11 asks how far a transaction above the floor
reaches and how long it waits, and experiment 08 answers it. The experiment
needs readings of the pull request, and choices of its own.

## Decision

1. **No new clause.** Under the pull request a node refuses a transaction
   whose rule 6 budget is above its own bound, and that bound is at least the
   floor. That is FP-6 with `max_verify_gas` set to the node's bound. The
   floor constrains how the nodes of a network are configured, and is not a
   check that one pool makes. So the experiment varies `max_verify_gas` per
   node as a variant of `eip-8141`, and `02-frame-pool.md` does not change.
   FP-6 already sums the declared `exec_gas` of the prefix, MD-6's
   `limits.execution`, and the signature cost of FEE-4. That is the pull
   request's "declared `limits.execution` of the prefix plus the signature
   intrinsic". Its vectors fix the boundary at two values of the bound. The
   pull request keeps `MAX_VERIFY_STATE_GAS` a hard maximum, as FP-6 does.
2. **Headroom values are read from the measurement, and shares are chosen.**
   Headroom of 250,000 is the value ethresear.ch topic 25889 recommends,
   which admits a spend of up to two nullifiers. The gradient's tiers are the
   values of its recommendation table. The shares of nodes at each value, and
   where they sit, are this experiment's choices; no measurement of
   deployed headroom exists.
3. **A wallet sends to a node that admits its spend.** A wallet refused by a
   node learns it at once and can try another. One that tries random nodes
   until one accepts ends at a random node that admits the spend, which is
   what the experiment's wallets do, without counting the refusals.
4. **Every node proposes, unless a row says otherwise.** In the model every
   node proposes in turn, so a spend that never leaves its first node is
   still included once that node's turn comes. That is the most favourable
   reading of "never dropped network-wide". Rows in which a few nodes build
   every block measure the other end, where a spend is included only if it
   reaches a builder with headroom.
5. **Budget hints, as the network's option and not the pool's.** With
   `announce_budget`, an announcement carries each frame transaction's rule 6
   budget, and a node does not fetch one whose budget is above its own bound.
   A push is a full transaction and carries no hint, so it is unaffected.
   What a node does with a hint above its bound is in no text. The
   experiment takes two readings. The node either forgets it and fetches on
   the next announcement, or remembers it for go-ethereum's
   `maxTxUnderpricedTimeout`, 300 s, as its fetcher does with an underpriced
   transaction (decision record 0004).
6. **A liar.** A node that does not want spends to travel admits nothing, so
   it relays and includes nothing. With hints, it also announces every hash
   it hears of to every peer, with a budget above any node's bound. Liars are
   drawn from the nodes at the floor, so that the share with headroom is the
   same with and without them.
7. **Not modelled.** Peer scoring, which the pull request rules out for a
   dropped transaction above the floor ("neither ... treats the exchange as a
   protocol violation"); a retried fetch from another announcer; inclusion
   lists, which an earlier revision of the pull request named and its head
   does not; and the cost of validation in time, which is what headroom is
   meant to size.

## Consequences

- `docs/spec/README.md` lists `max_verify_gas`, set per node, among the
  variants, and names experiment 08.
- The simulator gains per-node profiles (`Scenario.frame_pools`), a subset of
  nodes that build (`ChainConfig.proposer` as a tuple), budget hints and
  liars (`NetworkConfig`), and wallets with a sender for each spend
  (`SponsoredLoad`'s `fresh`).
- Whether a hint is bound to the transaction it describes is a question for
  the eth wire protocol change that the pull request defers. The experiment's
  numbers say what an unbound hint lets a liar do under each reading.
