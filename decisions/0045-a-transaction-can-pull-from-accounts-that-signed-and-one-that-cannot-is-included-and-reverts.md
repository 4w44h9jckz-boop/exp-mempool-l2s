# 0045. A transaction can pull from accounts that signed for it, and one that cannot is included and reverts

Date: 2026-10-13. Status: accepted.

## Context

The plan's item 21 asks how often a shuffle round fails against its size,
and how long it waits, in the public pool and sealed, when an input spends
first. The owner answered item 33 on 2026-10-13 with "PR then
push harder", read here as the go-ahead the item waited for.

The shuffle round of an earlier design study settles in one ordinary
transaction. Every input pays one unit through ERC-3009's
`receiveWithAuthorization`, every output receives one, and an input that
empties its account after signing makes the whole transaction revert: a
round of 8 whose last input did so was measured on 2026-10-07 reverting
after 370,753 gas, which its submitter paid. The study's native design
locks each input at inclusion instead, so that an input whose own
transaction lands first loses only its seat.

The model could express neither. BB-5 of `03-block-building.md` version 3
either applied a transaction or refused it, and nothing a transaction did
depended on another account's balance. A decrypted sealed transaction
(LU-13 of `06-lucid.md` version 1) ran nothing but its gas.

## Decision

1. **A transaction can pull and pay.** MD-5 of `00-model.md` version 8
   gains `pulls`, value its execution takes from accounts on their
   signatures and moves to `to`, and `pays`, value it moves from `to`. A
   pull is ERC-3009's `receiveWithAuthorization`, read from ethereum/ERCs at
   `c73cd77c` (Draft). The unit is ether, MD-2's balance, rather than a
   token: a token balance is a storage slot of the token's contract, which
   the model could carry only as a write that no read checks. Nothing the
   question asks depends on which asset moves.
2. **A transaction that cannot complete is included and reverts.** BB-5 of
   `03-block-building.md` version 4 executes the value, the pulls, the pays
   and the writes, and if a pull is not covered, or `to` cannot cover a
   pay, none of it applies. The sender's nonce and any authorizations stay
   applied, and the sender pays for the gas the transaction used. That is
   go-ethereum at `93d78a01`: `core/state_transition.go` says "vm errors do
   not effect consensus" and pays the coinbase on `gasUsed` whatever the
   error, and `MakeReceipt` marks the receipt failed. A pool does not read
   any of it, since go-ethereum's pool runs no code: a round whose input
   has spent is admitted and relayed as before.
3. **The gas a revert uses is declared.** The model runs no code, so it
   cannot know where in the round the failing input sits. A transaction
   carries `revert_gas_used`, by default its `gas_used`, as it carries
   `gas_used` and `state_gas_used`.
4. **A pull can be skipped instead.** With `atomic` false, a pull that its
   account cannot cover is skipped and the rest apply, as EIP-7702 skips a
   tuple and as the design study's native design skips a registration.
   That is what a lock at inclusion does, and it lets an experiment put the
   locked round beside the contract round.
5. **A revert uses no state gas.** EIP-8037 at `258836f9` restores a
   reverted frame's state gas to its baseline, top-level frame included
   (Gas accounting for halts and reverts), so BB-6 counts all of a
   reverted transaction's gas as execution.
6. **Builders that drop what reverts are a variant.** BB-7 adds
   `drop_reverting`, under which a builder treats a transaction that would
   revert as failing, `ErrExecutionReverted`, and leaves it out.
   go-ethereum's miner does not, so the default is unset. The design study
   names such a builder as a submitter's defence and did not measure it;
   which builders behave so is not read from any source here, so the
   variant is the counterfactual rather than a profile.
7. **A sealed round reverts too, and pays.** LU-2 of `06-lucid.md` version 2
   carries the plaintext's `to`, `pulls`, `pays`, `atomic` and
   `revert_used`, and LU-13 executes them as BB-5 does. EIP-8184 executes a
   decrypted transaction "as a regular transaction" and refunds the gas it
   did not use, and says the public path cannot offer "offchain revert
   protection". A decrypted transaction is committed, so BB-7 does not
   drop it.

## Consequences

- An experiment can now put a round in the public pool, sealed, or before
  builders that drop what reverts, and an input that spends first makes it
  revert at the submitter's cost, or be dropped, as the clauses say.
- Nothing any earlier experiment sent pulls or pays, so none of their
  transactions reverts. The four fields are left out of a
  transaction's hash at their defaults, so no hash moves, and every
  committed `results.md` reproduces.
- BB-5 now charges the fee after the execution rather than before it. For
  a transaction without pulls the end state is the same, since its cost
  was already checked against the sender's balance.
- Where in a round its failing input sits, a client's revert refund, and
  ERC-3009's nonce and validity window are not modelled. A pull that names
  an account twice draws on the balance its earlier pull left.
