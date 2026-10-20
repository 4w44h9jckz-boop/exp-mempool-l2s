# 23. A committee's keys

**Question.** Experiment 18's payments name a key publisher that is a
threshold committee: a key is released when at least $t$ of its $n$
members' shares are in time. How often is a key in time, and what do the
payments pay for it, against the members that withhold and those that are
late, at a threshold of two thirds and a majority, for committees of 16, 64
and 423? Does it matter that one slot's absent members fail every key of
that slot at once? What do senders that go public, or release their own
key, recover? How many shares does a slot carry, what does a rotation of
the committee lose with sealed transactions in flight, and what do builders
that leave the committee out cost its senders?

**Clauses exercised.** LU-12 and LU-13 (`docs/spec/06-lucid.md`): every
committed ticket is charged, and only a commitment whose key is released
runs. LU-9's fee bump for a resealed transaction. The block builder's
`skip`, a builder's own choice (decision record 0018), now reaches the
sealed selection. Decision record 0032 has the readings; no clause changes.

EIP-8184 (Draft, read at master `af80fc1c`) leaves the key publisher
off-protocol and its key message unsigned, so a committee is a key
publisher like any other. It fixes when a key is due: after $T_3$, and by
the PTC's key observation deadline. consensus-specs at `c489a99` puts
those at 3 s and 9 s into the slot under Gloas (`refs/refs.md`). An earlier
MPC study reads the committee side, keeping a key and releasing it every
slot.

## Setup

- **Experiment 18's network, payments and trades**: 10 nodes, 8 peers each,
  a block every 12 s, gas limit 60,000,000, so a block commits at most 32
  sealed transactions; payments of 100,000 gas bidding no ToB fee, each
  from a sender of its own with one payment in flight, at 16 or 28 a slot;
  trades at 2 a slot, naming a publisher that releases every key.
- **The committee**: every payment names it. $w$ members withhold every
  share; each other member misses each slot with chance $q$, of 0.1, 0.2
  and 0.3. A key is in time in a slot when at least $t$ shares are, and
  one draw a slot decides every commitment of the committee in that block.
  Nothing within the slot is timed (decision record 0032, point 2).
- **Committees**: 16 (EIP-7805's `IL_COMMITTEE_SIZE`), 64 and 423, the
  smallest drawn from validators of which a third are corrupt that lacks
  an honest majority with chance below $2^{-40}$ (section 0). Thresholds of
  two thirds and a majority: 11 and 9 of 16, 43 and 33 of 64, 212 of 423.
  $w$ is 0 or a third of $n$, rounded down: 5, 21 and 141.
- **Senders**: a sender that has seen no key 9 s after the block that
  committed its payment sends it again at its next nonce, to the node it
  sent it to, sealed to the committee (section 1) or as a regular
  transaction (section 2). In section 3, half of the senders, drawn per
  commitment, are online and release their own key.
- **Baseline**: the same rows with the members drawn afresh for each
  commitment, so each key is in time with the same chance, alone.
- **Rotation** (section 5): a new committee every 32 slots, which keeps the
  key (`reshare`) or makes its own (`rotate`); under `rotate` the old
  committee serves $g$ more slots, and a sender `keep`s a pending sealed
  transaction or `reseal`s it to the new key at a 10% bump.
- **Filtering** (section 6): half of the payments name the committee and
  half a publisher nobody filters; up to 5 of the 10 builders leave the
  committee's sealed transactions out, with no inclusion lists.
- **Shares** (section 4) are counted at 32 bytes each, an ASSUMPTION. The
  network has no bandwidth (decision record 0004), so they move no delay.
- Seed 1, 1200 s a run; rows are the payments first sent from second 240 to
  second 960, the window's 60 slots.

## Run

```
python3 experiments/23-committee-keys/run.py > experiments/23-committee-keys/results.md
```

It runs its simulations in parallel (`EMEM_JOBS`). Every figure below is
from `results.md`.

## Results

**Committee sizes** (section 0): the chance a committee of $n$ has no
honest majority, from validators of which a third are corrupt, is
$2^{-2.98}$ at 16, $2^{-7.87}$ at 64, and $2^{-40.16}$ at 423.

**Members that withhold or are late** (section 1), at 16 payments a slot;
P(key) is the chance a slot's key is in time, exactly, and released the
share of the committee's commitments whose key it released; delays in
seconds, from first sending to the block that runs the payment:

| committee | withholding | late | P(key) | released | sent | executed | delay p50 | p99 | attempts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 43 of 64 | 0 | 0.00 | 1.0000 | 1.0000 | 960 | 960 | 18.23 | 23.99 | 1.00 |
| 11 of 16 | 0 | 0.10 | 0.9967 | 0.9846 | 960 | 960 | 18.32 | 27.01 | 1.02 |
| 11 of 16 | 0 | 0.30 | 0.6598 | 0.5520 | 940 | 940 | 28.50 | 523.56 | 1.81 |
| 43 of 64 | 0 | 0.30 | 0.7383 | 0.7522 | 958 | 958 | 21.30 | 57.90 | 1.33 |
| 33 of 64 | 0 | 0.30 | 0.9994 | 1.0000 | 960 | 960 | 18.23 | 23.99 | 1.00 |
| 11 of 16 | 5 | 0.10 | 0.3138 | 0.2842 | 857 | 615 | 46.52 | 831.51 | 2.72 |
| 9 of 16 | 5 | 0.10 | 0.9104 | 0.9366 | 959 | 959 | 18.81 | 34.21 | 1.07 |
| 9 of 16 | 5 | 0.20 | 0.6174 | 0.6341 | 957 | 957 | 22.16 | 122.01 | 1.55 |
| 43 of 64 | 21 | 0.10 | 0.0108 | 0.0350 | 809 | 55 | 31.78 | 216.14 | 2.77 |
| 43 of 64 | 21 | 0.20 | 0.0001 | 0.0000 | 790 | 0 | n/a | n/a | 2.68 |
| 33 of 64 | 21 | 0.10 | 0.9972 | 1.0000 | 960 | 960 | 18.23 | 23.99 | 1.00 |
| 33 of 64 | 21 | 0.20 | 0.7711 | 0.6117 | 956 | 956 | 23.99 | 163.36 | 1.63 |
| 212 of 423 | 141 | 0.20 | 0.9800 | 0.9727 | 960 | 960 | 18.41 | 33.75 | 1.03 |
| 212 of 423 | 141 | 0.30 | 0.0318 | 0.0501 | 797 | 107 | 48.99 | 930.66 | 2.64 |

`results.md` has every row, at 28 a slot too, with the wei each payment
lost to tickets whose key was withheld. Sent falls where keys are withheld
because an arrival whose sender still has a payment in flight is skipped,
as in experiments 07 and 18: senders held by the committee turn demand
away.

**Senders that go public** (section 2), 43 of 64 at 16 a slot:

| withholding | late | sent | executed | sealed | public | delay p99 | lost, wei |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0.30 | 958 | 958 | 678 | 280 | 24.01 | 68370329882463.47 |
| 21 | 0.20 | 958 | 958 | 0 | 958 | 23.97 | 232862311046764.09 |

against 0 of 790 executed, and 567,948,535,125,443 wei lost a payment, by
senders that seal again with 21 withholding at 0.2.

**Keys that fail together, alone, and senders that release their own**
(section 3), at 16 a slot:

| committee | withholding | late | P(key) | draw | released | sent | executed | delay p90 | p99 | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 9 of 16 | 5 | 0.20 | 0.6174 | slot | 0.6341 | 957 | 957 | 57.39 | 122.01 | 169.13 |
| 9 of 16 | 5 | 0.20 | 0.6174 | commitment | 0.6248 | 958 | 958 | 42.66 | 76.20 | 108.03 |
| 9 of 16 | 5 | 0.20 | 0.6174 | slot, 0.5 online | 0.6649 | 960 | 960 | 29.76 | 42.48 | 46.12 |
| 11 of 16 | 5 | 0.10 | 0.3138 | slot | 0.2842 | 857 | 615 | 530.43 | 831.51 | 884.52 |
| 11 of 16 | 5 | 0.10 | 0.3138 | commitment | 0.2925 | 900 | 666 | 518.54 | 825.25 | 885.13 |
| 11 of 16 | 5 | 0.10 | 0.3138 | slot, 0.5 online | 0.2969 | 965 | 965 | 43.19 | 79.18 | 91.56 |
| 33 of 64 | 21 | 0.20 | 0.7711 | slot | 0.6117 | 956 | 956 | 69.53 | 163.36 | 211.10 |
| 33 of 64 | 21 | 0.20 | 0.7711 | commitment | 0.7631 | 958 | 958 | 33.17 | 51.73 | 90.89 |

**Shares a slot** (section 4), no member withholding, each late with chance
0.1, at 28 a slot:

| committee | commitments, mean | shares each, mean | batched, mean | bytes each, mean | max | sealed bytes, mean |
| --- | --- | --- | --- | --- | --- | --- |
| 11 of 16 | 28.77 | 409.27 | 14.22 | 13096.53 | 16384 | 14728.53 |
| 43 of 64 | 28.53 | 1630.83 | 57.17 | 52186.67 | 61440 | 14609.07 |
| 212 of 423 | 28.53 | 10881.82 | 381.47 | 348218.13 | 395264 | 14609.07 |

**Rotation** (section 5): at 16 a slot no commitment's key was gone under
any handover. At 28 a slot, `rotate` with the sender keeping its
transaction lost 2 commitments with the old committee serving 0 or 1 more
slots, 285,493,798,015.18 wei a payment on average, and none at 2 or 4;
resealing lost none at any $g$, with a p99 of 76.06 s against 76.31 s
under `reshare`.

**Builders that filter** (section 6): delays of the payments that name the
committee and, last, of the others:

| a slot | filtering | committee's executed | delay p50 | p90 | p99 | others' p99 |
| --- | --- | --- | --- | --- | --- | --- |
| 16 | 0 of 10 | 462 | 18.45 | 22.77 | 23.96 | 24.04 |
| 16 | 5 of 10 | 465 | 24.94 | 35.97 | 58.92 | 28.00 |
| 28 | 0 of 10 | 823 | 18.08 | 23.73 | 53.02 | 62.96 |
| 28 | 1 of 10 | 827 | 19.75 | 39.48 | 133.16 | 86.68 |
| 28 | 3 of 10 | 803 | 22.85 | 81.99 | 459.01 | 60.06 |
| 28 | 5 of 10 | 775 | 31.21 | 451.75 | 790.42 | 45.18 |

## What it shows

- **With a corrupt third withholding, a threshold of two thirds is
  unanimity among the rest.** 43 of 64 with 21 withholding needs all 43
  others: P(key) is 0.0108 at a lateness of 0.1, and the committee
  released 0.0350 of its keys. At 0.2 it released none, and senders that
  kept sealing to it executed 0 of 790 payments, each paying for 2.68
  tickets on average, 567,948,535,125,443 wei. 11 of 16 with 5 withholding
  released 0.2842 at 0.1. A majority with the same members withholding
  released every key at 0.1, 33 of 64 at 1.0000 with a p99 of 23.99 s,
  the same as nothing withheld.
- **A larger committee sharpens the step; it does not move it.** The count
  in time concentrates around $(1-q)(n-w)$, so a key is in time almost
  always while that is above $t$ and almost never once it is below. 212 of
  423 with 141 withholding released 1.0000 at 0.1, 0.9727 at 0.2 and
  0.0501 at 0.3, where P(key) falls from 0.9800 to 0.0318. 9 of 16 with 5
  withholding degrades instead: 0.9366, 0.6341, 0.3014. Against lateness,
  the size that buys $2^{-40}$ against a corrupt majority helps below the
  step and hurts above it: at 0.2, 212 of 423 had a P(key) of 0.9800
  against 33 of 64's 0.7711, and at 0.3, 0.0318 against 0.2148. Where the
  step sits, $t$ against $n-w$ decides.
- **Without withholding, lateness breaks two thirds, and a small
  committee first.** 11 of 16 released 0.9846 of its keys at a lateness of
  0.1 and 0.5520 at 0.3, with a p99 of 523.56 s against 23.99 s; 43 of 64
  released 0.7522 at 0.3. The majorities, 33 of 64 and 212 of 423,
  released every key at every lateness up to 0.3.
- **Going public caps the loss at one ticket and restores the delay.**
  With 43 of 64, 21 withholding, at 0.2, all 958 payments ran in public with a
  p99 of 23.97 s, each losing one ticket, 232,862,311,046,764 wei on
  average, where senders that sealed again ran none. A sender sealing to
  a committee has no other publisher to turn to, unlike experiment 18's.
- **Keys that fail together cost tail delay at the same share released.**
  9 of 16 with 5 withholding at 0.2 released 0.6341 drawn a slot and
  0.6248 drawn a commitment, with a p99 of 122.01 s against 76.20 s. A
  failed slot sends every one of its commitments back at once, into a
  block that commits at most 32. A run's outcome also rests on its 60 slot
  draws rather than on each commitment's: drawn a slot, the share released
  ended up to 0.1732 from P(key) (33 of 64 with 21 withholding at 0.2, 28
  a slot: 0.5979 against 0.7711); drawn a commitment, within 0.0224.
- **Senders that release their own key take the committee off half of the
  path.** With half of them online, 11 of 16 with 5 withholding at 0.1 ran
  965 of 965 payments with a p99 of 79.18 s, against 615 of 857 and 831.51
  s. At 28 a slot it helps less: with 11 of 16, 5 withholding, at 0.2,
  1194 of 1513 ran, against 118 of 1283 with no sender online, because
  offline senders' payments keep coming back and every block commits its
  32.
- **Without batching, a large committee's shares outweigh what they open.**
  At 28 a slot, 212 of 423 sent 10,881.82 shares a slot on average,
  348,218.13 bytes at 32 bytes a share, for 14,609.07 bytes of sealed
  transactions. 43 of 64 sent 52,186.67 bytes and 11 of 16 13,096.53.
  Batched threshold encryption needs one share per member in time, 381.47
  a slot for 423. The model has no bandwidth, so none of this moved a
  delay.
- **A rotation loses only what waits across it.** A sender seals to the key
  of the next slot's epoch, and a payment is committed within about a
  slot, so only payments that wait across a boundary are at risk: 2
  commitments at 28 a slot when the old committee served at most one more
  slot and senders kept their transactions, and none when it served 2, or
  when senders resealed.
- **Builders that leave the committee out cost its senders only when the
  rest cannot absorb them.** At 16 a slot, with 5 of 10 builders filtering,
  the committee's payments had a p99 of 58.92 s against 23.96 s with none,
  and the others were untouched. At 28 a slot the builders that do not
  filter cannot commit the committee's backlog within their 32: the p99
  was 133.16 s with 1 of 10 filtering, 459.01 s with 3 and 790.42 s with
  5. The ticket names the committee, as the EIP says, and inclusion lists
  carry no sealed transaction under this specification.

## Answer

A threshold committee works as LUCID's key publisher when its threshold
leaves room for both what withholds and what is late: here a majority of
64 or of 423 released every key with a third of its members withholding
and the rest late with chance 0.1, and two thirds of 64 released 0.0350 of
them. Size buys safety against a corrupt majority, $2^{-40}$ at 423
against $2^{-2.98}$ at 16; against lateness it only sharpens a step whose
place the threshold sets. A sender that goes
public, or is online to release its own key, keeps a failing committee to
a ticket's loss; one that keeps sealing to it pays a ticket a block and may
never run. Rotation is cheap at these rates. Filtering by the committee's
name is visible, and costs its senders once the other builders run out of
commitments.

## What it does not show

- **Time within the slot.** A share is in time or not; the 2 s at the
  4-second mark that decision record 0032 reads from ProbeLab's measurement
  is not simulated, and the case of shares and then a key over gossip,
  which does not fit the window, is not run.
- **Correlated members.** Members miss a slot independently of each other.
  Members on one client, region or provider fail together, which this
  does not measure.
- **Selective withholding and early release.** Members that withhold some
  senders' keys, or release a key early to a builder, are not modelled; nor
  is a committee that prices its release, which the EIP leaves to the
  publisher.
- **The committee's own costs.** Its sampling, key generation, resharing and
  the bytes of a rotation, which the MPC study prices, are not here; neither
  are bundles and the threshold ECDSA signature a bundle would need.
- **Inclusion lists for sealed transactions.** None exist in this
  specification, so section 6 has none.
- **Skipped arrivals.** Demand falls where senders are held, as in
  experiments 07 and 18; a sender with several payments in flight is not
  modelled.
