# 0003. The frame pool models what simulation observes, under two profiles

Date: 2026-10-07. Status: accepted.

## Context

EIP-8141's public mempool rules are rules about a trace: which opcodes the
validation prefix executed, which storage it read, which addresses it called.
A faithful pool would run an EVM. The experiments this repository expects
(the plan) are about admission, reservation, revalidation and throughput, not
about bytecode, and an EVM would make the reference neither standard-library
only nor readable.

The rules also differ between the EIP and the one client that implements them.
Six divergences were measured on the testnet on 2026-09-10, and an earlier
study settled that the specification's constants decide every verdict.
`exp-frames` reported a further one on 2026-10-07.

## Decision

1. **A frame carries its observations.** A frame declares what a node simulating
   it would see: the scope it approves, whether it reverts, the banned opcodes
   it executes, the storage it reads (with the value its code requires), what it
   writes and calls, and what a deploy frame installs (MD-6). The pool applies
   the EIP's rules to those observations (FP-8, FP-9). Frames whose behaviour the
   protocol defines (default code, the expiry verifier, the canonical
   paymaster) are evaluated from their definitions, as the EIP permits.
2. **A read with an expected value is the model's notion of state-dependent
   validity.** The prefix approves only while the slot holds that value. That
   is what lets an experiment invalidate pending transactions with a write and
   count the revalidation work (FP-15).
3. **Two profiles, the specification's first.** `eip-8141` uses the EIP's
   constants and is the default. `hegota-testnet` records what the testnet was
   measured to enforce, each value with its source and date (FP-1), so an
   experiment can ask how much a divergence matters. A testnet value is a
   measurement and may be stale, and it never edits the `eip-8141` profile.
4. **Interpretations are explicit.** Where the EIP leaves a choice open, the
   clause says *Interpretation* and this record is where the choice is
   explained:
   - a deploy frame after a leading expiry frame counts as first (FP-5),
     because the expiry section skips that frame for shape matching;
   - within a frame, trace rules are checked before the outcome (FP-8); a
     client finds the first violation in execution order;
   - frame transactions share go-ethereum's subpool reservation with the
     account-nonce pool (FP-13), so a sender cannot have both kinds pending;
   - capacity is a number (`max_pending`) and the newcomer is a candidate
     victim (FP-14);
   - a minimum tip and the head's gas limit apply as in the account-nonce
     pool (FP-3).

## Consequences

The model cannot catch a rule that depends on what code actually does, such as
a helper contract that reads a forbidden slot only on some inputs. Experiments
state the observations they assume. A move to real bytecode, for example by
driving ethrex through `exp-frames`, would be a differential test against this
model, not a replacement for it.
