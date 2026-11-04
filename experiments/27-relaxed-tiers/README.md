# 27. The relaxed alternative mempool's bound and its tiers

**Question.** `docs/spec/15-relaxed-mempool.md` admits, behind the canonical
rules, what they refuse to a contract that sends or pays for its own
transactions. Does one write, other than one that breaks a declaration,
still invalidate at most one pending transaction that only the relaxations
admitted, and by how much do the relaxations as first asked miss that? Is a
broken declaration seen in the access list of the block that carries it, and
what is the declared code's rate after? And what does each tier need at a
stated rate of proof-carrying transactions, a relay that checks no proof
against a verifier, a network of both against one in which every node
verifies, and what does a relay make a sender of junk pay?

**Clauses exercised.** RM-2 to RM-9 (`docs/spec/15-relaxed-mempool.md`,
version 1), with FP-2 to FP-15 (`docs/spec/02-frame-pool.md`), AG-5 and
AG-6 (`docs/spec/05-aggregation.md`), and CG-2 to CG-7 and CG-11
(`docs/spec/10-claim-gated-admission.md`). The experiment loads the
descriptors themselves: `docs/spec/descriptors/eip-8141.json`, and
`docs/spec/descriptors/relaxed.json` with a child descriptor that replaces
RM-3 to name the declarations (`docs/spec/13-descriptors.md`, DS-5). The
relaxations as first asked are a child of that one with `sender_bound` and
`outflow_bound` false (decision record 0082). Nothing in it is a clause.

## Setup

- **The accounts.** A shared pool's root contract, `roots`, whose code
  declares 32 slots write-once: 16 past roots, set, and 16 future ones,
  unset. A note pool, `notes`, that sends its own withdrawals, one nonce key
  and one nullifier slot each, whose code declares 128 nullifier slots and
  an outflow bound of one withdrawal's `max_cost`, 9,683,800; it also has a
  slot it does not declare. A ticket paymaster, `tpm`, staked, which
  declares no slot and an outflow bound of one ticket-paid transaction's
  `max_cost`, 12,731,300. A paymaster that declares nothing, `upm`. An
  account with no code, `e0`, a delegated one, `d0`, and an undeclared
  contract, `c0`, each with ten transactions on keys 1 to 10. Users with
  code `account-v1`.
- **Section 1's stream**, 402 transactions in a seeded order: 120 spends
  that each read a past root; 48 that read a nullifier, unset, 16 of them a
  second reader of one; 64 withdrawals of the note pool, each reading its
  own nullifier and a past root; 10 withdrawals that read the note pool's
  undeclared slot; 60 transactions paid by the ticket paymaster and 10 more
  whose `max_cost` is half its bound; 20 paid by `upm`; the 30 of `e0`,
  `d0` and `c0`; and 40 plain ones. The note pool's balance is 64
  withdrawals' `max_cost`, the ticket paymaster's what all 70 of its
  transactions reserve.
- **The writes.** After the stream, every write the pool knows a key for,
  one at a time on a copy of the pool, at the next head with its block's
  EIP-7928 access list: each past root rewritten; each nullifier written,
  and one written twice in one block; the note pool's and `c0`'s undeclared
  slots; `e0` delegating; each declared payer paying out its bound and twice
  its bound, from a balance set to just what its pending transactions
  reserve; and `upm` paying out everything. A write breaks a declaration as
  RM-6 reads it: a declared slot whose value before is not 0, or a payment
  beyond the declared bound.
- **Section 2.** A pool whose root contract's declaration was broken 0 to 3
  times, one block each, then 20 new readers of roots no violation touched,
  at 0, 1 and 2 hours, the pool emptied before each 20.
- **Section 3.** One node under the canonical descriptor, one relay and one
  verifier under `relaxed.json` with declarations, each fed the same seeded
  stream for 1,536 s, four epochs: honest spends, each from a new account,
  paid by the ticket paymaster under a bound claim, each with one dependency
  sent as a mode 0 wrapper, as a Poisson process at 1, 5, 10 and 25 a
  second; a junk sender's 20 tickets, each sent 5 times with a different
  failing proof; and 20 transactions with neither a claim nor a prefix of
  protocol-defined frames. A block every 12 s includes everything the node
  holds. The ticket paymaster is given a record of 100,000 seen and
  included (CG-11), so that its reputation is a busy issuer's and not one a
  node has just met.
- **Measured costs.** A proof weighs 319.9 KiB and takes 12.8 ms to verify,
  the means over leanVM's recursions on this repository's machine; the
  smallest and largest proofs measured are 190.0 and 332.7 KiB
  (`bench/results/2026-10-13-leanvm.md`, read through `bench/leanvm/fit.py`).
  A spend without its proof is 872 bytes, MD-6's encoding with its
  188-byte bound ticket (CG-10).
- **Bandwidth.** A node receives a transaction 8.45 times when every node
  sends it to every peer once, in a seeded connected network of 40 nodes
  with at least 8 peers each. A relay forwards transactions without their
  proofs (RM-8). A verifier either fetches each proof once, or receives it
  with each copy of its transaction.

## Run

```
python3 experiments/27-relaxed-tiers/run.py > experiments/27-relaxed-tiers/results.md
```

It takes about 80 s; `make experiments` checks the committed results.

## Results

`results.md`, seed 27. The numbers below are copied from it.

**One write, without breaking a declaration** (section 1):

| descriptor | admitted by the canonical modules | admitted by a relaxation | most relaxed removed by one write | most removed in all |
| --- | --- | --- | --- | --- |
| canonical | 46 | 0 | 0 | 1 |
| `relaxed.json`, declarations | 45 | 275 | 1 | 1 |
| as first asked | 45 | 330 | 19 | 20 |

As first asked, one payment out of `upm`, which declares nothing, removes
19 relaxed transactions and the canonical one beside them; `e0` delegating
removes 9 and 1; a write to `c0`'s slot 9 and 1; a write to the note pool's
undeclared slot 8. Under `relaxed.json` each of these removes at most the
one transaction the canonical rules admitted, because none of the others was
admitted: the stream's refusals include 37 `ErrFrameSenderBusy`, 19
`ErrFramePaymasterBusy`, 10 `ErrRelaxedReserve` and 16 `ErrWriteOnceBusy`.

**Breaking a declaration.** Rewriting a past root removes up to 15 pending
transactions, every one that read it, under both relaxed descriptors. Each
of the 19 writes that break a declaration raised its code's count in the
block that carried it, the nullifier written twice in one block among them,
which the state alone shows as a first write (section 1, "seen").

**The rate after** (section 2): a code with no violation admits all 20
readers; one violation throttles it to 4 of 20, until the refresh an hour
later brings its count to 0; three ban it, 0 of 20, then 4 of 20 at the
first and second hour as the count decays to 2 and 1.

**The tiers** (section 3), at 25 spends a second:

| node | admitted | prefixes run | proofs verified | CPU ms/s | pending | state keys | claims this epoch | proofs held MiB | KiB/s in |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| canonical | 0 of 38,696 | 20 | 0 | 0.0 | 1 | 3 | 0 | 0.0 | 0.0 |
| relay | 38,696 | 0 | 0 | 0.0 | 345 | 346 | 9,681 | 0.0 | 181.3 |
| verifier | 38,696 | 38,736 | 38,716 | 322.6 | 345 | 1,037 | 0 | 107.8 | 8,240.4 |

A junk ticket carried by a relay is one transaction, 1.00 a ticket at every
rate; a verifier verifies one proof a ticket, 20 for the 100 junk
transactions, and carries none. A relay carries none of the 20 transactions
with neither a claim nor a protocol-defined prefix; a verifier carries all
20.

**One 50 Mbps link**, by proof size, 190.0, 319.9 and 332.7 KiB, carries
into a relay 848 proof-carrying transactions a second at each size, into a
verifier that fetches each proof once 31.0, 18.7 and 18.0, and into one
that receives each proof with every copy 3.8, 2.3 and 2.2. With every node
verifying at 25 a second, the network of 40 spends 12.8 CPU seconds a
second verifying; with one verifier in five, 2.6.

## What it shows

- **The bound holds in this stream, and only with decision record 0082's
  additions.** No write that breaks no declaration removed more than one
  relaxed transaction under `relaxed.json`, nor more than one in all. As
  first asked, one write removed 19: a payer that declares nothing can lose
  its whole balance in one transaction the pool does not hold, and an
  account with no code, or an undeclared contract, can change what all its
  pending transactions read. Those are decision record 0082's three cases,
  each measured.
- **A broken declaration costs every transaction that read the slot, once.**
  15 for a past root here. It is seen in its own block's access list, the
  second write to an unset slot within a block included, and the code's
  rate drops in the same reset: 4 relaxed transactions may rely on it, then
  none after three violations, recovering only as RM-6's hourly decay
  lowers the count.
- **The relay needs a small part of what a verifier needs.** At 25 spends
  a second it ran no prefix and verified no proof, where the verifier ran
  38,736 prefixes and verified 38,716 proofs, 322.6 ms of CPU a second. It
  received 181.3 KiB/s against 8,240.4, and held a third of the verifier's
  state keys, plus one claim per spend of the current epoch, and no proofs,
  where the verifier held 107.8 MiB. Its uplink limit, 848 a second, is set
  by the transactions alone, where a verifier's, 18.7 a second at the mean
  proof when each proof is fetched once, is set by the proofs.
- **A relay makes a sender of junk pay.** It forwards one transaction a
  claim, and verifiers spend one proof a ticket, so each junk transaction a
  relay carries costs its sender a ticket; a transaction it cannot charge,
  with neither a claim nor a protocol-defined prefix, it does not carry.
- **The canonical rules carry no private spend.** A node under
  `eip-8141.json` admitted none of the 38,696 spends at 25 a second: their
  dependency frames are refused, and without them, one per payer would be.

## What it does not show

- **A live node.** No client returns a prefix's reads, so a node run
  against a chain refuses `relaxed.json` (decision record 0081). Every
  number here is the reference pool's over the model.
- **A delegation that moves to another code.** The model records each
  frame's outcome, not the code that produced it (MD-6), so it can show a
  change between no code and code, `e0` delegating, but not one between two
  delegations; `d0`'s ten transactions are admitted or refused as `e0`'s
  are.
- **How proofs travel.** Section 3 counts a verifier's proofs fetched once
  or with every copy, and nothing else; how a verifier fetches the proofs a
  relay did not carry, and from whom, is not modelled (RM-8). The copies are
  those of flooding, not of any client's gossip.
- **The state a prefix reads through the client.** State keys count what
  the pending transactions' recorded dependencies name. A verifier also
  needs the execution state its prefixes read; a relay needs only nonce
  sequences, balances, codes, ticket paymasters' keys and its claims.
- **A ticket's BLS12-381 check.** It is the relay's only cryptographic
  work, one a transaction, and its cost is not measured here.
- **Adversarial placement.** The stream is seeded, not searched: section 1
  enumerates every write the pool knows a key for after one stream, which
  shows the bound in that pool and not over all pools.
