# 0082. Many pending per sender and the payer's count lifted are bounded by a declared contract and a reserve

Date: 2026-11-04. Status: accepted.

## Context

Two of the three relaxations asked for are stated with a bound:
- **many pending per sender** on disjoint non-zero nonce keys, FP-12's
  `disjoint-keys`;
- **the non-canonical payer's count lifted** under FP-11's exposure sum,
  $\mathit{balance}(P) - R(P) - w(P) \ge m$.

The claim they serve is that one state change invalidates a bounded number
of pending transactions. Its stated falsifier is one write invalidating more
than one pending transaction that only the relaxations admitted.

Read against FP-10, FP-11 and FP-15, each relaxation as stated lets one
write do that.

**Many pending per sender.** Suppose $n$ transactions are pending from one
sender on disjoint keys. Their prefixes depend on the sender's code, on the
balance that pays for them, and on every sender storage slot they read
(FP-10). So any one of these writes reaches all $n$, and FP-15 step 3 re-runs
all $n$:
- an EIP-7702 delegation of the sender, which changes its code;
- a payment out of its balance;
- a store to a slot they read.

Every one whose prefix no longer holds is dropped. Under `one` it is one
transaction.

**The payer's count lifted.** FP-11's sum bounds what a payer's pending
transactions reserve, not how many one write invalidates.
- A transaction the pool does not hold can lower the payer's balance by any
  amount: one sent to a builder privately, or one the payer's code makes.
- FP-15 step 4 then drops, in the order received, every transaction the
  balance no longer covers.
- With the count at 1 that is one transaction.

That is why EIP-8141 caps a non-canonical paymaster ("each non-canonical
paymaster can only be used with no more than
`MAX_PENDING_TXS_USING_NON_CANONICAL_PAYMASTER` pending transactions"). It
gives the canonical paymaster a delayed withdrawal, $w(P)$, instead.

## Decision

1. **A relaxed sender is a declared contract (RM-4 item 2, `sender_bound`).**
   - A declaration is for a code. An account whose code is empty or an
     EIP-7702 delegation has none.
   - So a sender with several pending transactions is a contract, whose
     code no transaction can change.
   - Its relaxed transactions read only sender slots its code declares
     write-once, under RM-3's rule.
2. **A relaxed transaction reserves its payer's outflow bound (RM-5,
   `outflow_bound`).**
   - The payer's declaration names $X$, the most one transaction takes from
     its balance.
   - Each relaxed transaction it pays for must have $m \ge X$.
   - This applies to RM-4's transactions too, whose payer is often the
     sender, except when the payer is the canonical paymaster, which keeps
     EIP-8141's own bound.
   - RM-6 checks $X$ against each block's access list, as it checks
     write-once slots.
3. **Why the reserve bounds one write to one relaxed transaction.**
   - Before the write, $\mathit{balance}(P) - w(P) \ge \sum_i m_i$ over the
     payer's pending transactions.
   - A write lowers the balance by $\delta \le X$.
   - FP-15 step 4 keeps transactions in the order received while they fit,
     and removes the first that does not. Call it $j$.
   - If $j$ is relaxed, $m_j \ge X \ge \delta$. Then every later
     transaction fits, since
     $\sum_{i \ne j} m_i \le \mathit{balance}(P) - w(P) - m_j \le \mathit{balance}(P) - \delta - w(P)$.
   - If $j$ is the payer's canonical transaction, the next one removed is
     relaxed, and the same holds after it.
   - So at most one relaxed transaction goes, beside at most one the
     canonical rules admitted.
4. **For a bound ticket paymaster, $X$ is its denomination.** Its template
   refuses a `max_cost` above the denomination (CG-10's $T_b$), so every
   ticket-paid transaction can reserve exactly it at no cost to the holder,
   since `max_cost` is a cap and not a price.
5. **The relaxations alone stay measurable.** `sender_bound` and
   `outflow_bound` are parameters of `RM-4` and `RM-5`, both true in
   `relaxed.json`. Set false, they give the relaxations as stated. Experiment
   27 (`experiments/27-relaxed-tiers/README.md`) measures both.

## Consequences

- **A relaxed sender must be a declared contract.** An externally owned
  account keeps one pending transaction, and a smart account that wants
  several needs a declaration and reads only write-once slots in its
  prefixes.
- **A relaxed payer must declare $X$,** and every transaction it pays for
  beyond the first reserves $X$. A payer whose single transactions can be
  large ties up that much per pending transaction.
- **This differs from the ask.** The ask stated FP-11's exposure sum alone
  as relaxation 3's bound, and `disjoint-keys` alone as relaxation 2. This
  record adds the declared contract and the reserve, and says why with the
  ask's own falsifier. Whether to keep them is the owner's choice. Without
  them the claim's bound does not hold, and experiment 27 shows by how much:
  in its stream, one payment out of a payer that declares nothing removes
  19 relaxed transactions, and one delegation of an account with no code
  removes 9 (`experiments/27-relaxed-tiers/results.md`, section 1).
