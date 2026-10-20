# 0052. A replay judges what a chain keeps, and names its differences before it runs

Date: 2026-10-20. Status: accepted.

## Context

The plan's item 43 asks for the comparison behind the coordination
project's register entry for the replay: for each of `exp-frames`' mined
fixtures, a profile's verdict, the chain's outcome, and the profile
differences allowed to explain a mismatch. Its line "would show it wrong"
is: skandha admits what the chain rejected, or refuses what it mined, in a
way no named profile difference explains.

Three facts bound what a replay can judge:

- The fixtures are all mined. `exp-frames` keeps what landed, with its
  receipt; what a node refused is in experiments' READMEs, not in fixtures.
- State at a fixture's block cannot be read. The Hegota testnet's client
  refuses `ethrex_simulateFrameTransaction` at an old block, and answers
  `eth_getBalance`, `eth_getTransactionCount` and `eth_getCode` there with
  the latest state and no error (decision record 0051). Old headers are
  served.
- ethpandaops' frames-devnet-0 no longer answers (its RPC returned 404 on
  2026-10-20), so the six fixtures mined there have no header to read.

## Decision

1. **A document of its own, `docs/spec/12-replay.md`, prefix `RP`.** The
   comparison is not pool behaviour, so it does not sit in `11-surface.md`;
   it is a procedure over the surface and the pool's static clauses, with
   vectors like any clause.
2. **Judge only what a chain keeps.** The verdict is SF-2 and SF-3, then FP-3
   to FP-6 against the parent header, and the payer FP-10 reads from the
   prefix's shape. FP-7 is fixed by inclusion, FP-8 and FP-9 leave no trace
   in a receipt, and FP-11 to FP-14 depend on a pool nobody kept. The
   receipt's payer is the one piece of the prefix's outcome the chain keeps,
   so an ok verdict agrees only when the payers are the same.
3. **Differences are named before the first replay, with how each is
   applied.** RP-5 lists four: `max_verify_gas` and `max_verify_state_gas`
   and `expiry_verifier`, which FP-1 already records between the two
   profiles, and `recent-roots`, EIP-8272's verifier frame, which the
   testnet runs (ethrex's divergence ledger, section 1) and the
   `hegota-testnet` profile does not model. A refusal is explained when one
   difference, or two together, turns it into `ok`; the result names the
   fewest that do. Anything else is a disagreement, reported as one, and a
   new name added after a run would answer the falsifier with a word rather
   than a test.
4. **Each fixture is judged under its chain's profile, and Hegota's under the
   EIP's too.** `hegota-testnet` is the profile the falsifier is about;
   `eip-8141` beside it records what the EIP's own profile would refuse,
   which is what the plan's differential check was for.
5. **A fixture without a header is judged without the gas-limit
   comparison**, and its result says `header: missing`, rather than being
   left out.

## Consequences

- `conformance/` gains the `replay` operation and
  `conformance/vectors/replay/rp-04-comparison.json`, nine cases from four
  mined fixtures, three parent headers read from the chain, and three inputs
  written in by hand to reach the outcomes the fixtures cannot: a payer that
  differs, a refusal nothing explains, and bytes that are not the chain's.
- The reference gains `ref/python/emem/replay.py`. skandha's replay command
  plays the same rule over every fixture, and its results file is where item
  43's "every fixture has a verdict" is checked.
- *Not modelled*, as RP says: admission at the time a fixture was sent, and
  the trace-rule divergences `exp-frames` experiment 19 measured, which no
  receipt shows.
