# 0046. A griefer holds one seat a round and spends as the round is sent

Date: 2026-10-13. Status: accepted.

## Context

The plan's item 21 asks how often a shuffle round fails against its size,
and how long it waits, in the public pool and sealed, when an input spends
first. Decision record 0045 gave the model a transaction
that pulls from its inputs and reverts when one cannot pay. What was left
to choose is the experiment: which round, which settings, who spends first
and when, what the publisher does after a failure, and how long a round
takes off chain.

## Decision

1. **The round is an earlier design study's contract round, measured.**
   Its gas is $28078 + 67041 N$ and its calldata $132 + 224 N$ bytes, the
   lines through seven sizes the study measured on 2026-10-07. Its pulls
   run in input order, and it reverts at its $m$-th after
   $28078 + \lfloor 342675 m / 8 \rfloor$ gas, the line through its fixed
   cost and the 370,753 gas measured for a round of 8 whose last input had
   emptied its account. The unit is 0.1 ether, the study's native
   denomination, in ether rather than a token (decision record 0045,
   item 1).
2. **Four settings.** The public pool before go-ethereum's builders, which
   include a round that reverts (BB-5); the public pool before builders
   that drop it (BB-7); EIP-8184's sealed transactions, which execute at
   the top of the block after the one that commits them (LU-13); and the
   study's native lock at inclusion, modelled as two type 2 transactions
   from the publisher: a lock that pulls each unit into an escrow and skips
   an input that cannot pay (`atomic` false), and once the remaining
   coordination is done a settlement that pays the outputs from the
   escrow. The two share the charged gas the study measured on 2026-10-07
   for the amended native design, $235433 + 43471 N$, half each; the split
   is an assumption, and nothing measured but the gas a round uses depends
   on it. The native design settles at the start of a later block without a
   transaction; here the publisher sends one, which can only lengthen the
   lock's wait.
3. **The griefer holds one seat a round and spends as the round is sent.**
   One input of every round, at a position and a node drawn per round, is
   an adversary's. It signs the output list last, and as the publisher
   sends the round, or under the lock the lock, it sends a transfer of its
   unit to a fresh address, from its own node, at a tip one gwei above the
   round's, so that a builder that holds both orders the transfer first.
   That is one transaction a round. Spending earlier would
   be caught: the publisher simulates before sending (item 4). Spending later
   is too late under the lock, and under sealing a spend sent after the
   commitment runs after the decrypted round (`lu-13-decrypted.json`). Once
   its unit is gone the publisher leaves it out, so it takes no part in a
   later attempt of the same round. An adversary that buys a fresh seat for
   every attempt pays a transaction an attempt and a unit's capital a seat,
   and is not modelled.
4. **The publisher simulates, and after a failure leaves out what cannot
   pay.** Before sending, an input whose balance is below the unit, or that
   has a transaction pending, at the publisher's node, is left out and the
   attempt is coordinated again without it, as the study tells its
   submitter to simulate. After a revert it leaves out every input whose
   balance is below the unit and coordinates again. A round still pending
   while one of its inputs cannot pay is given up as dropped and replaced at
   its nonce by the next attempt, at fees raised by the pool's price bump;
   without that, a round that BB-7's builders leave out would wait for
   ever. If a builder includes it before the replacement arrives it
   reverts, and it is counted as reverted. A round left with fewer than 8
   inputs, the study's placeholder `MIN_ROUND_SIZE`, is abandoned, and the
   next starts.
5. **An attempt takes 6 to 18 seconds off chain, uniformly.** No source read
   here measures how long a round's registration and signing take; the
   range is an assumption, and the waits reported are measured from a
   round's start, so they include it. Under the lock, half comes before the
   lock and half after it.
6. **The network is experiment 18's at 20 nodes, with a 60M gas limit.**
   20 nodes of 8 peers, a 12 s slot, proposers in rotation, and transfers of
   1,000,000 gas at three quarters of the gas target, so that rounds share
   blocks with other traffic without a backlog. At 60M, LUCID's
   top-of-block segment is 7,500,000 (LU-1), which holds a sealed round of
   at most 111 inputs, so a sealed round of 128 is refused with
   `ErrSTExceedsToB`, as LU-4 says.
7. **A failed attempt is one that reverted, was dropped, locked fewer than
   8, or was caught before sending.** The failure share is failed attempts
   over attempts with a griefer, pooled over sizes and three seeds, less any
   round its pool refused.

## Consequences

- The rounds run with one griefer's seat a round, against the round the
  study measured, in every setting item 21 names and in the two defences
  the study names, builders that drop and a lock.
- What the griefer does is fixed, so the experiment shows what one seat a
  round buys, not the best an adversary can do. Withholding an approval,
  which fails the native round with a penalty to the withholder, and a
  griefer that rejoins every attempt, are not modelled.
- Honest inputs that spend by mistake are not modelled either; without a
  griefer no input spends.
