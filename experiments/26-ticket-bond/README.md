# 26. A bond on the ticket paymaster

**Question.** Experiment 25 priced version 4 of claim-gated admission as
written, issuer memory and a node list against a self-issuer's junk proofs.
What does a third defence cost, a bond on the ticket paymaster as ERC-8421
stakes an operator and keeps its reputation: what does a self-issuer's junk
proof cost the nodes and the self-issuer under it, what can a holder of
honest tickets do with it to a busy and to a small honest issuer, and what
does the bond cost a small honest issuer?

**Clauses exercised.** CG-1 to CG-6 and CG-10
(`docs/spec/10-claim-gated-admission.md`, version 4), as in experiment 25.
The bond's rules and parameters are those of ERC-8421's standard ruleset,
read in `docs/spec/14-erc-8421.md` (AM-3's stake, AM-13's reputation) and
given by `docs/spec/descriptors/erc-8421.json`, which the experiment loads
and compiles (`docs/spec/13-descriptors.md`, DS-6). The bond is not a
clause: no clause composes ERC-8421's ruleset with claim-gated admission,
and it is modelled in the simulator around the clauses, in CG-2's place and
before the ticket's signature is checked (`sim/emem_sim/issuers.py`,
decision record 0062).

## Setup

- **Network, chain and load**: experiment 25's, run for two hours: 30
  nodes with 8 peers each, a block every 12 s from a rotating proposer,
  under EIP-8288 with claims, and epochs of 384 s (CG-1), for 19 epochs,
  7,296 s, so that the ruleset's hourly refresh falls at 3,600 s and
  7,200 s. Wallets send 8 spends a slot with tickets of four busy honest
  issuers, `h0` to `h3`, and 4 spends an epoch with tickets of a small
  honest issuer, `s0`, each with one leanSTARK dependency, as mode 0
  wrappers, until 300 s before the end. Honest spends pay for themselves, as
  in experiment 25.
- **The bond** (decision record 0062). Every node accepts the tickets of a
  staked paymaster only, and refuses others with `ErrIssuerUnbonded`. For
  each ticket paymaster it keeps `seen`, once for each transaction under
  its tickets whose proof it checked or which it admitted, and `included`,
  once for each of those a block includes, both multiplied by 23/24 every
  3,600 s. A paymaster is `THROTTLED` once `seen // 10` exceeds
  `included + 10`, and then backs at most 4 pending transactions at the
  node, and `BANNED` once it exceeds `included + 50`, and then its tickets
  are refused with `ErrEntityBanned`. Staked means $10^{18}$ wei with an
  unstake delay of 86,400 s, the descriptor's values. All five honest
  issuers are staked.
- **Attackers** (`JunkProofs`), from second 60 until second 6,912:
  - section 1, experiment 25's self-issuer: every slot it hands every node
    4 wrappers, each from a fresh sender with a valid ticket it signed and a
    proof that fails, and moves to its next paymaster at a node that refuses
    the current one, from its first again each epoch. With `none` the nodes
    run version 4 as written; with `bond, unbonded` its paymaster has no
    stake; with `bond` each of its one or four paymasters is staked;
  - section 2, a holder of the target's tickets, bought honestly: 5 s into
    each epoch it hands every node, for each ticket, a wrapper of its own
    whose proof fails, 8 or 64 tickets an epoch, against `h0` or `s0`.
- **Measured numbers**, as in experiment 25 (`refs/refs.md`): deploying a
  ticket paymaster costs 2,443,085 gas; an honest ticket costs its buyer
  $10^{15}$ wei; verifying one leanVM proof takes 11.442 ms on this
  machine (`bench/results/2026-10-13-leanvm.md`).
- **Derived**: section 3, from the descriptor's parameters: the junk an
  attacker needs to throttle or ban an issuer whose spends are all
  included, and the bond against the denomination.
- **Modelled**: everything the simulator counts: ticket checks, prefixes
  and proofs, each paymaster's state at each node and for how long, and the
  honest refusals and delays. The stake's lifecycle on chain is not.
- Seed 1, and one run for each row.

## Run

```
python3 experiments/26-ticket-bond/run.py > experiments/26-ticket-bond/results.md
```

## Results

### 1. A self-issuer's junk proofs against a bond

| defence | paymasters | used | wrappers | ticket checks | prefixes | proofs | hour 1 a node | hour 2 a node | nodes that banned | banned at s | banned share | refused before the ticket | deployment gas | stake wei | stake ETH-days | proof s | honest refused | landed | sent | delay p50 | p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| none | 1 | 1 | 68520 | 68520 | 68520 | 68520 | 1180.00 | 1104.00 | 0 | n/a | 0.00 | 0 | 2443085 | 0 | 0.00 | 784.01 | 0 | 4733 | 4733 | 6.54 | 11.48 |
| bond, unbonded | 1 | 1 | 68520 | 0 | 0 | 0 | 0.00 | 0.00 | 0 | n/a | 0.00 | 68520 | 2443085 | 0 | 0.00 | 0.00 | 0 | 4733 | 4733 | 6.54 | 11.48 |
| bond | 1 | 1 | 16380 | 15960 | 15960 | 15960 | 510.00 | 22.00 | 30 | 1584.00 | 0.73 | 420 | 2443085 | 1000000000000000000 | 1.08 | 182.61 | 0 | 4733 | 4733 | 6.54 | 11.48 |
| bond | 4 | 4 | 63690 | 62730 | 62730 | 62730 | 1180.00 | 911.00 | 30 | 1584.00 | 0.41 | 960 | 9772340 | 4000000000000000000 | 4.32 | 717.76 | 0 | 4733 | 4733 | 6.54 | 11.48 |

### 2. A holder of honest tickets against a bond

| target | tickets an epoch | tickets | wei | proofs | hour 1 a node | hour 2 a node | nodes that throttled | throttled at s | nodes that banned | banned at s | throttled share | banned share | honest refused | target landed | sent | delay p50 | p90 | others p50 | others p90 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| h0 | 8 | 136 | 136000000000000000 | 4080 | 72.00 | 64.00 | 0 | n/a | 0 | n/a | 0.00 | 0.00 | 0 | 1210 | 1210 | 6.66 | 11.40 | 6.51 | 11.49 |
| h0 | 64 | 1088 | 1088000000000000000 | 32640 | 576.00 | 512.00 | 0 | n/a | 0 | n/a | 0.00 | 0.00 | 0 | 1210 | 1210 | 6.66 | 11.40 | 6.51 | 11.49 |
| s0 | 8 | 136 | 136000000000000000 | 4080 | 72.00 | 64.00 | 0 | n/a | 0 | n/a | 0.00 | 0.00 | 0 | 71 | 71 | 7.55 | 11.30 | 6.51 | 11.49 |
| s0 | 64 | 1088 | 1088000000000000000 | 32640 | 576.00 | 512.00 | 30 | 1541.00 | 0 | n/a | 0.77 | 0.00 | 0 | 71 | 71 | 7.55 | 11.30 | 6.51 | 11.49 |

### 3. What a bond costs a small honest issuer

| spends counted an hour | junk to throttle | wei | junk to ban | wei |
| --- | --- | --- | --- | --- |
| 0 | 110 | 110000000000000000 | 510 | 510000000000000000 |
| 10 | 200 | 200000000000000000 | 600 | 600000000000000000 |
| 100 | 1010 | 1010000000000000000 | 1410 | 1410000000000000000 |
| 1000 | 9110 | 9110000000000000000 | 9510 | 9510000000000000000 |

| issuer | spends an epoch | tickets an epoch | wei an epoch | throttled after hours | banned after hours | bond days |
| --- | --- | --- | --- | --- | --- | --- |
| h0 | 64 | 8 | 8000000000000000 | n/a | n/a | 0.07 |
| h0 | 64 | 64 | 64000000000000000 | n/a | n/a | 0.07 |
| s0 | 4 | 8 | 8000000000000000 | n/a | n/a | 1.11 |
| s0 | 4 | 64 | 64000000000000000 | 0.43 | 2.03 | 1.11 |

## What it shows

- **A bond prices each paymaster a self-issuer uses, and the ruleset's
  reputation bounds what each buys.** Under version 4 as written the
  self-issuer's one deployment bought 1,180 junk proofs a node in the first
  hour and 1,104 in the second, 68,520 over the run. With its paymaster
  staked, every node banned it at 1,584 s, after 510 failed proofs there,
  and the hourly refresh reopened it for 22 more: 15,960 proofs over the
  run, and a banned share of 0.73 of the attack's node-time. The
  self-issuer locked $10^{18}$ wei for 1.08 ETH-days, from the attack's
  start to the end of the unstake delay, and spent the same deployment.
- **More paymasters buy more junk, at a stake each.** With four staked
  paymasters the self-issuer kept the full 1,180 a node in the first hour
  and 911 in the second: 22 more from each of the two the refresh reopened,
  and the rest from the two it had not used up. That is
  $4 \cdot 10^{18}$ wei locked, 4.32 ETH-days, for 62,730 proofs, against
  one deployment for 68,520 under version 4. The bond does not stop a
  self-issuer with capital; it makes each 510 proofs a node cost one
  paymaster's stake for a day, and each 22 after that cost an hour of it.
- **An unstaked paymaster costs the nodes nothing.** All 68,520 wrappers of
  `bond, unbonded` were refused before the ticket was checked, as a node
  list refuses an unlisted issuer in experiment 25, except that any issuer
  can join by staking rather than by being listed.
- **A holder of honest tickets cannot close a busy honest issuer.** At 8 or
  64 tickets an epoch, $1.088 \cdot 10^{18}$ wei over the run at 64, no node
  throttled or banned h0, and its spends landed as before: its `included`
  grows with its traffic, and the threshold with it. Under issuer memory in
  experiment 25, one ticket an epoch closed h0 at every node for 379 s of
  each epoch.
- **A small issuer is cheaper to grief.** At 64 tickets an epoch every node
  throttled s0 at 1,541 s, for 0.77 of the attack's node-time. It still
  landed all 71 of its spends, because 4 an epoch never made it back 4
  pending at once, so the throttle refused none. Sustained, the same rate
  bans it after 2.03 hours (section 3), just after this run's attack ends,
  for 0.064 ETH an epoch; 8 tickets an epoch never throttles it. An issuer
  no node has counted is banned by 510 junk proofs a node within an hour,
  0.51 ETH of its tickets, and one counted 1,000 times an hour by 9,510.
- **The bond weighs on a small issuer as a share of its sales.** The stake,
  $10^{18}$ wei, is 1,000 tickets' face value: 1.11 days of s0's sales at 4
  an epoch, and 0.07 days of h0's at 64. It is locked from the first ticket
  to a day after the last.
- No honest spend was refused and no honest delay moved in any row: 4,733
  of 4,733 busy spends and 71 of 71 small ones landed, at 6.54 s and 11.48 s.
- Against experiment 25, the bond sits between its two defences. Like a node
  list it refuses an unstaked paymaster before any check, without a list
  per node; like issuer memory it bounds what one paymaster buys, by
  reputation rather than by an epoch, and a griefer has to outweigh the
  issuer's own included spends rather than spend $k$ tickets.

## What it does not show

- **The stake's price.** The experiment counts wei locked and for how long,
  not what locking it costs, which depends on what the staker would
  otherwise earn; and not the gas of staking and unstaking.
- **Bursts.** The throttle refuses an issuer's spends only while it backs 4
  pending at a node. A small issuer whose spends arrive together would be
  refused while throttled; s0's arrive at 4 an epoch and never were.
- **Reputation shared between nodes.** Each node counts only what it saw;
  the self-issuer and the griefer reach every node, the worst case for the
  issuer they target, and a self-issuer that reaches fewer nodes is banned
  at fewer.
- **The derived rows** of section 3 count every honest spend as seen and
  included in the epoch it is sent, at its mean rate; the simulated rows
  of section 2 agree with them where they overlap, throttling s0 at 0.43
  hours.
- **One seed, two hours.** One rate of junk, one honest load, and a griefer
  who always sends early in the epoch.
- **Node time is counted, not spent**, as in experiment 25.
