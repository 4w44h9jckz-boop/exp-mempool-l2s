# 0019. Wasted work is counted in prefix runs, against two adversaries

Date: 2026-10-09. Status: accepted.

## Context

The plan's item 13 asks how much validation work the network spends per
adversary transaction, from fresh empty payers, against the number of nodes,
under both frame pool profiles. The claim it tests is ethresear.ch topic 25995,
"Public-mempool gas sponsorship needs escrow, a bond, or trust", by
AnkushinDaniil, posted 2026-09-14 and read in full on 2026-10-09. Its case 1
says of a rule that "charges nothing" per attempt: "Each distinct s reaches
and is checked by all N nodes". Wasted work is then about $N$ times the
attacker's cost, and EIP-8141 avoids this only by holding money.
An earlier study reads the result for private spends: a spend from a fresh
account can have none of the three. It asks for a measured $w$, the work to
reject one transaction, which needs a client.

The frame pool already decides the question, clause by clause. FP-8 runs the
prefix before FP-11 reads the payer's balance, and a pool relays only what it
admits. So no clause is new. What the experiment must choose is what to
count and which adversaries to set against the rule.

## Decision

1. **Work is counted in prefix runs, not in gas or time.** A run is a pool
   evaluating a transaction's validation prefix:
   - at admission, which is every answer FP-8 or a later clause gives;
   - at a new head, when FP-15 re-runs it.

   The model has no client, so it cannot give the topic's $w$ in time; it
   gives the number of times $w$ is paid. Admission runs come from the
   recorder's answers per node, less the answers FP-2 to FP-7 give before
   the prefix runs. Re-runs come from each pool's record of what its last
   reset re-ran. A builder's failed attempt to include a transaction is
   counted apart.
2. **Two adversaries, at opposite ends.**
   - *empty* is case 1 as the topic states it. Each transaction has a
     default-code sender and a default-code sponsor of its own, made for
     nothing and holding nothing. The adversary hands each one to one
     random node, or to every node, which is the most a sender can do
     without relaying.
   - *drained* is the cheapest way to get past FP-11. One sponsor a block
     holds enough for `k` transactions at their fee cap. The adversary
     waits two seconds after a block, by which time every node holds it,
     then hands each of the `k` transactions to a random node. With them it
     sends every node the sponsor's transfer of its whole balance, at twice
     their tip, to the next round's sponsor. The next block includes the
     transfer first, so the transactions fail, and the same balance backs
     the next round. This is experiment 05's drained sponsor, made to
     travel by gossip rather than handed to every node. It is the topic's
     "checked-but-drainable balance", which the topic files under "hold
     money".

   The money is reported as what the adversary pays in transfers and what
   it holds. A balance that moves from sponsor to sponsor stays the
   adversary's, so it is capital and not cost.
3. **Network size is the variable.** 25, 50, 100 and 200 nodes, 8 peers
   each, every node proposing in turn. Honest self-paying frame transactions
   are the yardstick: the work the network does per transaction that pays.

## Consequences

- `SybilLoad` in `sim/emem_sim/workload.py` sends both adversaries.
- The model cannot see work that a client does before the prefix, such as
  decoding and signature recovery, or after it, such as storing and
  announcing. Both are paid for every hand-over whatever the rule.
