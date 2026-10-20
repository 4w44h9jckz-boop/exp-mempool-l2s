# 0064. The bond on the ticket paymaster is a clause of claim-gated admission

Date: 2026-10-20. Status: accepted.

## Context

Version 4 of `10-claim-gated-admission.md` accepts as a ticket paymaster any
account whose code is the template, a key and a denomination (CG-10), so
anyone can issue tickets to themselves and pay for junk proofs once, with a
deployment (decision record 0057). Three defences were modelled in the
simulator around the clauses and priced: issuer memory and a node list in
experiment 25 (decision record 0059), and a bond on the ticket paymaster,
ERC-8421's stake and reputation, in experiment 26 (decision record 0062).
The owner chose the bond. It becomes a clause of claim-gated admission:
the specification first, then hand-written vectors, then the reference.

Three things the simulator's model left implicit need a reading before it
can be a clause: which account is a claim's paymaster, when `seen` and
`included` move, and what happens to a banned paymaster's pending
transactions.

## Decision

1. **Version 5, CG-11.** `10-claim-gated-admission.md` goes to version 5.
   CG-1 gains `bond`, true under `claim-gated` and false under every other
   profile. CG-11 refuses, after FP-6 and before CG-2's checks, a
   transaction whose ticket paymaster is not staked (`ErrIssuerUnbonded`),
   is `BANNED` (`ErrEntityBanned`), or is `THROTTLED` and already backs
   `throttled_entity_mempool_count` pending transactions
   (`ErrEntityThrottled`). The stake is AM-3's, the counters, their refresh
   and the states AM-13's, and the parameters AM-1's with `erc-8421.json`'s
   values: the same rules and numbers experiment 26 ran.
2. **The ticket paymaster is the transaction's payer, when that is not its
   sender.** The template's `VERIFY` frame fails unless its scope is
   `PAYMENT`, and approves payment (kohaku-rs at `eea02a3`,
   `crates/frame-ticket/contracts/TicketPaymaster.yul`). A transaction that
   carries a real ticket is therefore paid by its ticket paymaster, and its
   sender, which must approve execution in a frame of its own, cannot be
   one. The model gives claims directly (MD-6), and every claim-gated
   vector before this version puts its claim on a transaction that pays for
   itself; such a claim stands for a ticket whose paymaster is not
   modelled, and CG-11 reads nothing for it. Reading the payer needs no
   simulation: it is the resolved target of FP-4's last prefix frame, as
   AM-3 names an entity, so the checks can come before the prefix runs.
   The simulator named each ticket's issuer by the load that made it
   instead, and its honest spends paid for themselves to stay clear of
   FP-11's cap; its junk was paid by the issuer's paymaster, as here.
3. **`seen` once a transaction: at a failed proof, or at admission.** A
   junk proof is never admitted, so it counts when its proof fails at AG-5's
   step 5, having passed the bond, the ticket and the prefix (CG-3). Any
   other transaction counts when the pool admits it, as AM-13 counts. A
   replacement counts as a new transaction, and no transaction counts twice.
   `included` counts FP-15's step 1, as AM-13 reads inclusion. Decision
   record 0062's simulator counted every proof it checked, verified or not;
   with that count a transaction whose own proof banned its paymaster was
   then refused at admission by the ban it caused. The clause admits it.
   The two counts differ only for that one transaction a ban, and for a
   transaction whose proof verifies and that the pool then refuses after
   it, which the simulator counted and the clause does not.
4. **A banned paymaster's pending transactions stay.** AM-13 removes them
   at `reset` (REPUTATION-010). Experiment 26 measured the bond without the
   removal, and with it a holder of an honest issuer's tickets who has the
   issuer banned would also drop its pending spends, a cost the experiment
   did not price.
5. **The throttle is moot under `claim-gated`.** FP-11 holds a ticket
   paymaster, which is not canonical, to one pending transaction, fewer
   than `throttled_entity_mempool_count`, so step 3 of CG-11 refuses
   nothing until a profile lets a paymaster pay for more. The clause keeps
   the step, as ERC-8421 has it, and its vectors raise FP-11's cap to show
   it.
6. **The descriptor.** `CG-11` is a module of `13-descriptors.md` (version
   2) with the seven parameters it reads. As a `CG` module DS-6 requires it
   with the others, so `claim-gated.json` carries it and its identifier
   changes to `bafkreifhtepzdwqnimltyd573ba7wsmln556axhbbxhqez6be547llopxe`,
   computed by skandha's TypeScript encoder and by the reference, which
   agree. DS-6 step 4 still refuses ERC-8421's modules beside claim-gated
   admission: CG-11 reads seven of their parameters, not their rules.

## What it costs

From experiment 26 (`experiments/26-ticket-bond/README.md`):

- A self-issuer with capital still buys junk, at a stake per paymaster:
  with four staked paymasters it kept 1,180 junk proofs a node in the first
  hour and 911 in the second.
- A small honest issuer locks the stake, $10^{18}$ wei, 1,000 tickets' face
  value, which was 1.11 days of its sales at 4 tickets an epoch.
- A holder of a small issuer's tickets who spends 64 an epoch on junk
  throttles it at every node at 1,541 s, and, sustained, bans it after 2.03
  hours. A busy issuer was never throttled.

## Consequences

- The vectors of CG-2 to CG-10 hold unchanged and say version 5; CG-11's
  are new, written by hand. The descriptor vectors that name
  `claim-gated.json`'s identifier or its profile change with the file and
  say version 2.
- The reference keeps AM-13's counters in the frame pool, where ERC-8421's
  pool and claim-gated admission both read them.
- Experiments 25 and 26 build their profiles from `eip-8288` with `claims`
  and without `bond`, so neither moves; experiment 26's simulated bond
  stays the evidence for the clause.
- A node run against a chain checks claims without `bond`: the surface
  (`11-surface.md`) reads no staking registry.
