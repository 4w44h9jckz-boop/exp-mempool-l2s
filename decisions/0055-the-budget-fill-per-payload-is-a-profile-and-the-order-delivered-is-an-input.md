# 0055. The budget fill per payload is a profile, and the order delivered is an input

Date: 2026-10-20. Status: accepted.

## Context

Item 46 opened with phase 2 on 2026-10-20. The claim it tests is that
FOCIL's assumption that one honest includer of sixteen suffices holds, for
transactions that cost something to check, only with a budget for each list.
Would show it wrong: a budget for each list still lets one member's entries
deny honest ones, or a pooled budget does not. Done when `exp-frames`
experiment 25's denial is reproduced under the pooled budget and is absent
under the per-list one.

`07-focil.md` version 1 had one budget fill, IL-4, EIP-8369's: a budget of
`MAX_VERIFY_GAS_PER_IL` for each list, "evaluated per IL occurrence before
deduplication". Experiment 25 found that ethrex runs the same fill once over
the whole payload, because the execution layer is handed one array. It was
checked at the source before anything was written:

- ethrex at `64b8fc09`, the Hegota testnet's client:
  `crates/networking/rpc/engine/inclusion_list.rs` passes
  `inclusionListTransactions` of `engine_newPayloadV6`, one array, to the
  satisfaction check, and `crates/blockchain/focil_eligibility.rs` runs
  `fill_il_budget` once over it with $2^{20}$ for both constants;
- consensus-specs at `d9663f85`, `specs/heze/inclusion-list.md`:
  `get_inclusion_list_transactions` ends `return list(set(transactions))`,
  "Order does not need to be preserved";
- execution-apis at `e4ba6c4f`, `src/engine/bogota.md`:
  `inclusionListTransactions: Array of DATA`, nothing on order.

A second difference came with it. EIP-8369's candidacy skips only the expiry
verifier frame, so the privacy withdrawals experiment 25 uses, whose prefix
opens with EIP-8272's recent-root verifier frame, are not candidates as it
is written; EIP-8272 says "clients MUST skip both optional leading protocol
verifier frames", and ethrex's `validation_prefix` does. Version 1's IL-3
left this to the frame profile without saying so.

## Decision

1. **The fill is an IL-1 parameter, `fill`**, `per-list` in every existing
   profile, and **a profile `ethrex`** is `eip-8369` with `per-payload`. It
   records an implementation, as `geth` does, not a chain: whether the
   testnet enforces inclusion lists was not measured.
2. **Under `per-payload` the order delivered is an input** of IL-4 and
   IL-6, because no text fixes it and experiment 25 showed the verdict
   depends on it. Where none is given the model takes the ILs in committee
   order with each transaction once, so that the simulator has an order; no
   result here rests on that default.
3. **IL-3 skips a leading recent-root verifier frame under a frame profile
   with recent roots**, as EIP-8272 and ethrex do, and says so. Under a frame
   profile without them, condition 2 reads as EIP-8369 writes it.
4. **A node at the surface takes validity at the end of the payload as a
   client's verdict** (IL-5), as FP-8 takes a simulation's, and computes
   IL-4 itself. A mempool node holds no post-state; the verdict is what an
   execution client's Profile 2 replay answers.
5. **The vectors are surface vectors on experiment 25's own bytes**: the
   mined withdrawals, sponsorships and transfers, and the attacker's
   never-valid transactions, signed by a key that has never held ether.
   The per-payload cases use orders the experiment recorded, one of them
   consensus-specs' function under hash seed 3, and every expected set is
   derived by hand from IL-4 and agrees with what experiment 25 reports from
   ethrex's own fill.

## Consequences

- Done when, on the reference: under `ethrex` the never-valid transaction
  declaring $2^{20}$ gas, delivered first, is the only one admitted, and the
  committee delivered under seed 3 denies both withdrawals, so a payload
  that leaves them out satisfies the lists; under `eip-8369` the same lists
  admit every honest transaction, and the same payload leaves out W1
  without excuse.
- An includer's own list (IL-2) is the same under both fills, since it can
  budget only what it lists. Under `per-payload`, sixteen lists protect what
  one list's budget holds: two withdrawals at their declared limits.
- Under `per-list` every version 1 vector holds unchanged; all eight files
  say version 2. Four deliberate breaks of the reference were each caught
  and undone.
- Not modelled: ethrex's second budget, the code bodies a replay may load,
  and the pull requests to EIP-7805 and EIP-8369 that experiment 25 reports
  open, which fill in `(keccak256(envelope), envelope)` order and were not
  read here.
- EIP-8369's condition 2 and EIP-8272's "skip both" sentence were checked
  at ethereum/EIPs `258836f9`, the commit the document pins.
