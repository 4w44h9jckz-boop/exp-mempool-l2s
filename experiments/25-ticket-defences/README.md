# 25. A self-issuer's junk proofs, and two defences

**Question.** Version 4 of claim-gated admission accepts as a ticket
paymaster any account whose code is the template, a key and a denomination,
so anyone can issue tickets to themselves. What does a self-issuer's junk
proof cost the nodes and the self-issuer under version 4 as written, and
under two defences a node might run: issuer memory, which refuses an
issuer's tickets for the rest of an epoch once $k$ proofs have failed under
them, and a node list, which accepts only the issuers a node lists? What
does each defence cost the honest senders it is meant to protect?

**Clauses exercised.** CG-1 to CG-6 and CG-10
(`docs/spec/10-claim-gated-admission.md`, version 4): the claim, the checks
before the proof (CG-3), CG-4's record of a failed proof, and the ticket
paymaster recognised by its code (decision record 0057). AG-5 to AG-9 as in
experiment 24. Neither defence is a clause. Both are modelled in the
simulator around the clauses, in CG-2's place and before the ticket's
signature is checked (`sim/emem_sim/issuers.py`, decision record 0059).

## Setup

- **Network, chain and load**: experiment 24's `laptop, budget` nodes, 30 of
  them with 8 peers each, a block every 12 s from a rotating proposer, under
  EIP-8288 with claims, and epochs of 384 s (CG-1). Wallets send 8 spends a
  slot, each with one leanSTARK dependency, as mode 0 wrappers, for 1,236 s
  of a 1,536 s run. Each spend carries a valid ticket of one of four honest
  issuers, `h0` to `h3`, by its sender. A wallet sends again after a block
  that left its spend out, with a fresh ticket if the epoch has moved on.
- **Payment**: honest spends pay for themselves. A ticket paymaster is not
  the canonical paymaster, so FP-11 lets it sponsor one pending transaction
  at a time, which would cap each issuer's spends far below this load; the
  experiment sets that cap aside to price the defences alone.
- **Attackers** (`JunkProofs`), from second 60 until second 1,152, so that
  what they close reopens before the run ends:
  - section 1, a self-issuer: every slot it hands every node 4 wrappers,
    each from a fresh sender with a valid ticket it signed itself and a
    proof that fails. With more than one paymaster it moves to the next at
    a node that refuses the current one, and starts from its first again
    in each epoch;
  - section 2, a holder of `h0`'s tickets, bought honestly: 5 s into each
    epoch it hands every node, for each ticket, a wrapper of its own whose
    proof fails. Under issuer memory with $k$, it buys $k$ tickets an epoch;
  - section 3, section 1's self-issuer with one paymaster, against nodes
    that each list $n$ of the four honest issuers, drawn at random for each
    node.
- **Defences**: `none` is version 4 as written; `memory k=1` and
  `memory k=8` close an issuer at a node, for the rest of the epoch, at the
  first or eighth proof that failed there under its tickets; `list` accepts
  the four honest issuers and nothing else.
- **Measured numbers**, read from the Hegota testnet and a wallet's run on
  it, and from this repository's benchmark (`refs/refs.md`):
  - a ticket paymaster's `VERIFY` frame spent 122,006 gas, and a ticket's
    check at a node is the same pairing outside the EVM;
  - deploying a ticket paymaster costs 2,443,085 gas (`eth_estimateGas` of
    the deployment the wallet made, at block 482,799);
  - an honest ticket costs its buyer the denomination, $10^{15}$ wei;
  - verifying one leanVM proof takes 11.442 ms on this machine
    (`bench/results/2026-10-13-leanvm.md`).
- **Derived**: a paymaster's float must cover FEE-4's max cost of the spend
  it sponsors before FP-8 lets the spend through. For the wallet's spend
  `0x0bba93ca` that is 383,893,005,374,502 wei, computed from its bytes.
  The paymaster has no withdrawal, and its float leaves only as gas it
  approves.
- **Modelled**: everything the simulator counts. That covers the ticket
  checks, prefix simulations and proofs verified, each issuer's closing at
  each node and for how long, the honest delays, refusals and extra
  tickets, and the share of spends each node carried. "Over a day" scales an
  epoch's rate to 225 epochs.
- Seed 1, and one run for each row.

## Run

```
python3 experiments/25-ticket-defences/run.py > experiments/25-ticket-defences/results.md
```

## Results

### 1. A self-issuer's junk proofs

| defence | paymasters | used | wrappers | ticket checks | prefixes | proofs | proofs a node an epoch | refused before the ticket | deployment gas | deployment gas a proof | a proof over a day | float wei | proof s | honest refused | landed | sent | delay p50 | p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 1 | 1 | 10920 | 10920 | 10920 | 10920 | 128.00 | 0 | 2443085 | 223.73 | 2.83 | 383893005374502 | 124.95 | 0 | 821 | 821 | 7.63 | 12.44 |
| memory k=1 | 1 | 1 | 180 | 90 | 90 | 90 | 1.00 | 90 | 2443085 | 27145.39 | 361.94 | 383893005374502 | 1.03 | 0 | 821 | 821 | 7.63 | 12.44 |
| memory k=1 | 8 | 8 | 1440 | 720 | 720 | 720 | 8.00 | 720 | 19544680 | 27145.39 | 361.94 | 3071144042996016 | 8.24 | 0 | 821 | 821 | 7.63 | 12.44 |
| memory k=8 | 1 | 1 | 810 | 720 | 720 | 720 | 8.00 | 90 | 2443085 | 3393.17 | 45.24 | 383893005374502 | 8.24 | 0 | 821 | 821 | 7.63 | 12.44 |
| memory k=8 | 8 | 8 | 6480 | 5760 | 5760 | 5760 | 64.00 | 720 | 19544680 | 3393.17 | 45.24 | 3071144042996016 | 65.91 | 0 | 821 | 821 | 7.63 | 12.44 |
| list | 1 | 1 | 10920 | 0 | 0 | 0 | 0.00 | 10920 | 2443085 | n/a | n/a | 383893005374502 | 0.00 | 0 | 821 | 821 | 7.63 | 12.44 |

### 2. A holder of honest tickets

| defence | tickets an epoch | tickets | wei | proofs | nodes closed | seconds closed | honest refused | honest tickets over none | h0 landed | h0 sent | h0 delay p50 | p90 | others p50 | others p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 1 | 2 | 2000000000000000 | 60 | 0.00 | n/a | 0 | 0 | 233 | 233 | 7.45 | 12.30 | 7.66 | 12.50 |
| memory k=1 | 1 | 2 | 2000000000000000 | 60 | 30.00 | 379.00 | 4991 | 133 | 223 | 223 | 109.73 | 368.27 | 7.55 | 12.64 |
| memory k=8 | 8 | 16 | 16000000000000000 | 480 | 30.00 | 379.00 | 4991 | 133 | 223 | 223 | 109.73 | 368.27 | 7.55 | 12.64 |
| list | 1 | 2 | 2000000000000000 | 60 | 0.00 | n/a | 0 | 0 | 233 | 233 | 7.45 | 12.30 | 7.66 | 12.50 |

### 3. Node lists that differ

| issuers listed | carried mean | least | most | honest unlisted | junk checks, prefixes, proofs | junk refused | landed | sent | delay p50 | p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | 0.99 | 0.99 | 1.00 | 0 | 0 | 10920 | 821 | 821 | 7.63 | 12.44 |
| 3 | 0.74 | 0.71 | 0.77 | 44405 | 0 | 10920 | 821 | 821 | 12.18 | 27.43 |
| 2 | 0.50 | 0.46 | 0.53 | 59331 | 0 | 10920 | 821 | 821 | 22.89 | 55.41 |
| 1 | 0.22 | 0.07 | 0.28 | 46305 | 0 | 10920 | 810 | 810 | 59.59 | 163.00 |

## What it shows

- **Under version 4 as written, a self-issuer's junk proof costs every node
  a ticket check, a prefix simulation and a proof verification. It costs
  the self-issuer nothing after one deployment.** 4 wrappers a slot make
  each node verify 128 proofs an epoch, 10,920 over the run, about 125 s
  of proof verification network-wide at 11.442 ms each. Each wrapper also
  re-runs a `VERIFY` frame that spent 122,006 gas on chain. The self-issuer
  spent one deployment of 2,443,085 gas and a float of 383,893,005,374,502
  wei that it keeps. That is 224 gas of deployment a proof over the run,
  and under 3 over a day. Nothing grows with the number of junk proofs.
- **Issuer memory caps what one paymaster buys, per node and per epoch, but
  not its total.** With $k$ = 1 a node verifies one junk proof a paymaster
  an epoch, and with $k$ = 8 eight, at every node the self-issuer reaches.
  The same paymaster reopens in the next epoch. A self-issuer with $P$
  paymasters gets $kP$ proofs a node an epoch: 8 and 64 here with 8
  paymasters. Its deployments are paid once: 362 gas a proof over a day
  with $k$ = 1, and 45 with $k$ = 8.
- **Issuer memory hands a holder of honest tickets the honest issuer.** One
  ticket an epoch with $k$ = 1, or eight with $k$ = 8, closed `h0` at all 30
  nodes, 379 s of each 384 s epoch, for $2 \cdot 10^{15}$ or
  $1.6 \cdot 10^{16}$ wei over the two epochs. Nodes refused `h0`'s
  honest spends 4,991 times. Its wallets bought 133 tickets more than
  without the attack, and its spends waited 109.73 s at the median and
  368.27 s at p90, against 7.55 s and 12.64 s for the other issuers'.
  Without issuer memory, each ticket buys the attacker one failed proof at
  each node it reaches, 60 proofs for 2 tickets, and delays no honest spend.
- **A node list stops the self-issuer before its ticket is checked, and
  costs the honest senders whose issuer a node does not list.** With every
  honest issuer listed, the self-issuer's 10,920 wrappers cost no ticket
  check, prefix or proof. When each node lists 3, 2 or 1 of the 4 honest
  issuers, a node carries 74, 50 or 22 percent of the honest spends on
  average (the least 7 percent). The median delay rises from 7.63 s to
  12.18, 22.89 and 59.59 s, and p90 to 163 s with one issuer listed, since
  a spend reaches a block only through a proposer that lists its issuer.
- No defence here is free. Version 4 leaves the junk unpriced. Issuer
  memory caps the junk an issuer can cause, but anyone who buys $k$
  tickets can close an honest issuer for the rest of the epoch at every
  node they reach. A node list ends the self-issuer's junk, but adds a
  list per node, and senders whose issuer a node does not list lose that
  node.

## What it does not show

- **Node time is counted, not spent.** A junk proof's verification and
  prefix do not slow a node's admission of honest spends here, so the
  honest delays in section 1 do not move. On a real node they compete for
  the same cores.
- **Gossip of failed proofs.** A node learns of a failed proof only from a
  wrapper it was handed itself. A node that shared what failed would close
  an issuer at nodes the attacker never reached, for the griefer as for the
  self-issuer.
- **FP-11's cap on a ticket paymaster** is set aside, and with it the
  ordering it imposes on every issuer's spends.
- **Wallets do not know nodes' lists.** A refused wallet sends to a random
  node after the next block. A wallet that sent only to nodes listing its
  issuer would wait less, but still only for a proposer that lists it.
- **One seed, one size.** 30 nodes, four issuers, and one rate of junk; the
  griefer always sends early in the epoch, the worst case for the honest
  issuer.
