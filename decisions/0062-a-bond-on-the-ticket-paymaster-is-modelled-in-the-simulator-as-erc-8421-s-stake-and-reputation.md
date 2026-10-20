# 0062. A bond on the ticket paymaster is modelled in the simulator, as ERC-8421's stake and reputation

Date: 2026-10-20. Status: accepted.

## Context

Decision record 0059 modelled two defences against a self-issuer's junk
proofs under version 4 of `10-claim-gated-admission.md`, and experiment 25
priced them: issuer memory rate-limits junk but lets a holder of honest
tickets close an honest issuer, and a node list stops junk but costs
honest spends their reach when lists differ. The choice between them is
open, and a third has been asked to be priced before it is made: a bond on
the ticket paymaster, priced by the issuer's capital rather than by a list
or a timeout.

`14-erc-8421.md` reads ERC-8421's standard ruleset, which stakes operators
and keeps a reputation for each entity, and `docs/spec/descriptors/erc-8421.json`
gives its parameters. A ticket paymaster is an operator of that kind. No
clause composes the ruleset with claim-gated admission: `13-descriptors.md`
refuses a descriptor that names both (DS-6, decision record 0060), because
no clause says how per-entity budgets, trace rules and reputation apply to
dependency frames, wrappers and claims.

## Decision

1. **No clause.** `10-claim-gated-admission.md` stays at version 4 and
   `14-erc-8421.md` at version 1. The bond is a third `Defence` of the
   simulator's guard (`sim/emem_sim/issuers.py`), beside issuer memory and
   the node list, and is not in the reference's pool or in the vectors.
2. **A node requires the stake.** It accepts the tickets of a paymaster that
   is staked as AM-3 stakes an entity, and refuses every other's with
   `ErrIssuerUnbonded` in CG-2's place, before the ticket's signature is
   checked. ERC-8421 admits an unstaked sponsoring payer under
   REPUTATION-220; requiring the stake of a ticket paymaster is what makes
   it a bond, since a self-issuer otherwise replaces a banned paymaster for
   the price of a deployment. Which paymasters are staked is the run's
   (`Bond.bonded`), as the registry's answer would be (AM-3).
3. **Reputation as AM-13 keeps it, for the ticket paymaster.** A node
   counts `seen` once for each transaction under a paymaster's tickets whose
   proof it checked (CG-3's mode 0 wrappers) or which it admitted by any
   path: the ERC counts each "unique valid transaction" a node "received
   over RPC and over the mempool network", and a junk proof's transaction
   has passed its claim and its prefix. It counts `included` once for each
   of those that FP-15's step 1 removes, AM-13's reading of inclusion. Both
   are refreshed by 23/24 every `refresh_seconds` of the run, from 0.
4. **A banned paymaster is refused before any check**, with
   `ErrEntityBanned` (REPUTATION-010), and a throttled one once it backs
   `throttled_entity_mempool_count` pending transactions at the node, with
   `ErrEntityThrottled` (REPUTATION-020), both in CG-2's place. Junk is
   never pending, so throttling bounds it only while the paymaster backs
   honest spends; the ban is what bounds a self-issuer.
5. **The parameters are the descriptor's.** Experiment 26 loads
   `erc-8421.json` and compiles it (DS-6), so the bond's thresholds are the
   ruleset's own.
6. **The adversary.** `JunkProofs` moves on from a banned paymaster as from a
   closed one, and starts from its first again each epoch, so it returns to
   a paymaster a refresh has unbanned.

## Consequences

- Experiment 26 prices the bond against experiment 25's self-issuer and its
  holder of honest tickets, and derives what it costs a small honest issuer
  from the ruleset's counters. The choice among the three stays open.
- Under a bond the guard also wraps the frame pool's `_insert` and
  `_remove`, to count `seen` and `included`; `sim/tests/test_sim.py`'s
  `TestBond` checks the counts, the ban, the refresh and the throttle.
- *Not modelled*: the stake's deposit, unlock and withdrawal on chain and
  their gas; AM-14's blame, since a junk proof is refused at admission and
  never revalidated; REPUTATION-220's allowance, since an unstaked
  paymaster is refused outright; and a reputation shared between nodes,
  since each node counts only what it saw.
