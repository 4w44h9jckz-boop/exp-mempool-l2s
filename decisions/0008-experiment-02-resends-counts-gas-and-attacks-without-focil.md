# 0008. Experiment 02 resends, counts work in gas, and attacks without FOCIL

Date: 2026-10-07. Status: accepted.

## Context

The plan's item 2 asks for MATCHA's throughput and worst-case revalidation work
against experiment 01. Experiment 01's harness answers neither as it stands:
its relayer never has more than one spend refused for a reason that goes away,
its spend has no expiry frame, and it counts re-simulations, which under
MATCHA are no longer all alike, because a re-run is paid for in width and a
refused re-run is not run at all. The post names two attacks, mass
invalidation and width draining, and answers the second with a FOCIL
extension the model does not have (`docs/spec/04-matcha.md`, *Not modelled*).

## Decision

1. **The spend is the voucher pool's whole.** An expiry frame with a deadline
   a day ahead, the pool's `self_verify` frame at 5,000 gas and 260 bytes, a
   `SENDER` frame at 41,000 gas and 68 bytes, and a 256-bit nullifier as its
   nonce key, as an earlier design study of a voucher pool shaped it.
   MATCHA's charge counts bytes and prefix execution, so a spend of that shape
   lets the charge be set beside the one that study measured on 2026-09-08,
   and the expiry frame is what MA-6 check 3 reads. This departs from
   decision record 0005, item 3, which left the frame out because nothing in
   experiment 01 read it.
2. **Where several spends can be pending, the relayer sends each at once and
   takes back what is lost.** After every block its node imports it sends
   again any spend its node refused or no longer holds, and skips one already
   included. It does not read width, so every resend while width is short is a
   refusal. A relayer that held spends until its node's width covered them
   would make fewer, and is not measured. Under `one` the relayer is
   experiment 01's, serial.
3. **Work is counted in admission gas** (MA-2's $a$, before the safety
   factor), summed over every prefix a pool runs for the sender, at admission
   and after a head change, including runs whose transaction is then refused.
   Under MATCHA a re-run is paid for in the same unit, and a count of
   re-simulations would weigh a refused admission at nothing although its
   prefix ran.
4. **Junk is a valid spend at a tip of 1 wei.** It passes every admission
   check, and no builder includes it because the tip is below the miner's
   minimum. For mass invalidation every junk prefix reads one setting slot of
   the adversary's application, and an account the adversary controls writes
   the slot once a block, at 26,000 gas, which is the cheapest write that
   invalidates them all. The adversary first earns width with paid spends at
   honest tips, because without width MATCHA leaves it a baseline and nothing
   else. For width draining the adversary is assumed to hold valid vouchers for
   the honest pool, which any user of the pool does.
5. **Width draining is measured without FOCIL.** The post's deterrent is that
   includers would force junk on chain, where it would cost its sender. The
   model has no inclusion lists, so the numbers are what draining does to a
   pool when nothing deters it.
6. **`disjoint-keys` is left out of the draining runs.** Every included honest
   spend moves the pool's balance, so every junk spend pending at every node is
   re-run at every block; the run is section 3's attack at a fifth of the burst
   and takes too long to sit in `make experiments`.

## Consequences

- Section 1's width refusals are the relayer's resends, and a smarter relayer
  would show fewer of them and the same throughput.
- A reader comparing with experiment 01 should use its delays, not its spend:
  the two spends differ in shape, and experiment 02's is 69,621 gas.
- Whether FOCIL would make draining unprofitable is left to the experiment
  that adds inclusion lists (the plan, growing the base).
