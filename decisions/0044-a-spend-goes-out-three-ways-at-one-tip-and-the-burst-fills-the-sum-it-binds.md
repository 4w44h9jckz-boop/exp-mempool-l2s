# 0044. A spend goes out three ways at one tip, and the burst fills the sum it binds

Date: 2026-10-13. Status: accepted.

## Context

The plan's item 34 asks for experiment 21 again with state gas and full
blocks, to compare how long private spends and other transactions wait. Decision
record 0043 gave the model EIP-8037's second dimension, and with it a
difference between envelopes: a frame transaction reserves its state gas in
the state dimension alone, and a type 2 transaction reserves all of its gas
in both.

A block full of other traffic is a tip auction: a transaction waits until
its tip ranks above what fills the block. A first trial compared spends and
other transactions drawn independently, and the difference between their
medians was mostly the difference between their tips.
A second trial, with the three ways at one tip, found the frame spend
landing first in every tie that mattered, because experiment 21's spends
all come from one shared sender and go-ethereum's `choosePeers` sends one
sender's transactions to the same first hops, so at equal tips the gossip
decided.

## Decision

1. **Each user's spend goes out three ways at one tip.** A user who asks
   for a spend sends it as experiment 21's frame transaction, as a type 2
   transaction with the frame spend's execution gas and the nullifier's
   state gas, and as a control with the execution gas alone, all to the
   node that relays the frame spend. The comparison is within each user,
   so it measures the envelope and not the tip. The two type 2 ways come
   from senders of their own, so no relayer's nonce chain is measured.
2. **Each way's tip differs from the user's by a jitter below 1,000 wei.**
   Which of the three a builder takes first is then a coin's. The shared
   sender's fixed first hops are a property of go-ethereum's gossip, which
   experiment 12 measured for what it tells a spy; here they would be
   measured as a property of the envelope, which they are not.
3. **The control is the other transaction.** Item 34 compares private
   spends with other transactions. The control does the spend's work
   without its nullifier, so a difference between them is the nullifier's.
   The other traffic's waits are reported beside them.
4. **The burst fills the sum it binds at 1.5 times what that sum holds.**
   Other traffic is type 2 transactions, from 5,000 senders, for 600 s:
   either of execution gas drawn uniformly between 21,000 and 200,000, or
   of execution gas between 21,000 and 100,000 and, with equal chances,
   one new storage slot, two, or one new account, at EIP-8037's 97,920,
   195,840 and 183,600 state gas. Under `two` the second fills the state
   dimension, which holds fewer of them than the execution dimension;
   under `one` it is execution and state in one sum. The arrival rate is
   1.5 times what the sum that binds holds at the mean, under each rule,
   so that every run's blocks are full for the burst and its backlog. Both
   mixes are assumptions: no source on the mix of Ethereum's transactions
   was read.
5. **The state traffic creates state of more than one size.** A trial
   whose state traffic all created one slot found the frame spend never
   landing after its control in blocks full of state. That was the gas
   limit's remainder, not the envelope: when everything that uses state
   uses 97,920, a block's state room is 2,100,000 less a multiple of it,
   so near the block's end it is 141,600 or 43,680, never between the
   control's gas, 69,902 for a nonce key, and the frame spend's 97,920,
   where the control fits and the frame spend does not. With accounts and
   slots mixed, the room moves in steps of 12,240, 8 state bytes, and
   both margins occur.
6. **Fee caps are a million base fees above the tip.** EIP-1559 raises the
   base fee by an eighth after a full block, so through a burst and its
   backlog it outruns a cap of twice the base fee, and then the wait is
   the wallet's, which experiment 15 measured. With caps that never bind,
   the queue is ordered by tip alone.
7. **Five seeds, pooled.** A run takes seconds, and a user's spend differs
   from its control only at the margin of a block, so the counts are small
   in any one run.

## Consequences

- The result says what the nullifier costs a spend in waiting, in each
  envelope, against a transaction of the same execution gas, and what it
  costs in gas, which is the same in both envelopes.
- The item's other half, a shared sender keeping its nullifiers off state
  without making validity depend on block order, is an argument and not a
  measurement.
- A relayer that sends every type 2 spend from one account, and
  wallets whose caps bind, are not measured.
