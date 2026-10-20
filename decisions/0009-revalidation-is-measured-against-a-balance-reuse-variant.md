# 0009. Revalidation is measured with a capital-free adversary, against a balance-reuse variant

Date: 2026-10-08. Status: accepted.

## Context

The plan's item 3 asks for the re-simulations a block causes as a function of
how many pending transactions share a dependency: the DoS bound the rules buy.
EIP-8141 states the goal as "to avoid allowing an arbitrary number of
transactions to be invalidated by a single environmental change or state
modification", and says of payer reservations that they bound "aggregate
exposure so that a single balance change cannot invalidate an unbounded set of
pending transactions" (Mempool, at `258836f9`). Its Revalidation section has a
node re-simulate the prefix of every transaction "whose payer's balance or code
changed", and FP-15 transcribes that. Reservations limit what a balance change
can *invalidate*; whether anything limits what it makes a node *re-run* is the
question, and answering it needs choices the sentence in the plan leaves open.

## Decision

1. **A variant of FP-15 that reuses a prefix's result on a balance change.**
   `02-frame-pool.md` version 2 adds `reuse_balance`, false in both profiles,
   so that an experiment can show how much of the work is balance-only. Under
   it a transaction whose changed dependencies are all balances, none moving
   from or to zero, is not re-run, and FP-15's step 4 makes the only check a
   balance feeds: `APPROVE`'s comparison with `max_cost`, which the
   reservation check implies. The zero exception keeps the sender-existence
   check the EIP names among the reasons a balance is a dependency. The
   reading rests on FP-9's ban of `BALANCE` and `SELFBALANCE` and on its
   refusal of calls to accounts without code, so that no prefix can observe a
   balance any other way; in the model it is exact, and
   `ref/python/tests/test_invariants.py` checks that a pool with it keeps
   exactly what a pool without it keeps. The EIP points the same way, asking
   that a node index pending transactions by their dependencies "so that
   head-of-chain changes are revalidated without re-execution", but only for
   prefixes made of protocol-defined frames. MATCHA's MA-9 reuses on balances
   without the zero exception, and stays as it is.
2. **The adversary's transactions cost it nothing to keep.** Their fee cap and
   tip are 1 wei. FP-3, like the EIP's mempool section, sets no floor on the
   fee cap, a builder never includes them, and since `max_cost` is `max_gas`
   times `max_fee` each reserves `max_gas` wei against its payer. The capital
   they would need at a fee cap of the base fee is reported beside it, for a
   client that required one, as MATCHA does for additional transactions.
3. **The touch is a 21,000-gas transfer of 1 wei to the payer**, the cheapest
   transaction that changes a balance, which any account can send to any
   address. It needs nothing from the payer, so the same touch moves an honest
   paymaster's balance.
4. **Work is counted twice**: re-simulations, which FP-15 makes observable,
   and code gas, the declared limits of the prefix frames whose target holds
   code the protocol does not define. Default code, the expiry verifier and
   the canonical paymaster are evaluated directly ("Direct Evaluation of
   Protocol-Defined Frames") and count as no code gas; a client that
   re-simulates them literally does more. The model cannot price a direct
   evaluation, so a re-simulation of one is a count with no gas.
5. **The adversary sends `max_pending` transactions**, 4096, to every node, and
   there is no other traffic, so FP-14 never evicts. With honest traffic a
   full pool evicts the adversary's 1-wei transactions first, because they
   have the lowest effective tip and no deadline sorts them sooner; what that
   costs honest transactions instead is experiment 4's question.
6. **Honest demand rises above the base fee's target only in a burst.** Wallets
   here price at twice the current base fee and never give up, so sustained
   demand above the target raises the base fee without bound: in a first run
   it drained a paymaster holding $10^{22}$ wei. Section 3 therefore runs at
   about half the target, with a ten-minute burst at twice it, the shape of
   experiment 00. Its users are senders with code, so that each re-simulation
   runs some.

## Consequences

- The numbers bound a node's work from above for shapes that run code, and
  overstate it for prefixes of protocol-defined frames under a client that
  follows the EIP's SHOULD.
- `reuse_balance` is a proposal measured, not a reading of the EIP, and the
  experiment's README says so wherever it reports it.
- Whether a node should require a fee cap near the base fee, or bound how many
  transactions one payer backs, is left as an open question in FP-15.
