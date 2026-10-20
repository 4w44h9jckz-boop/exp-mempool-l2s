# 06. Sealed transactions (LUCID, EIP-8184)

Version 2, 2026-10-13. Version 1 ran nothing of a decrypted transaction
but its gas; see the version notes at the end.

The mempool side of EIP-8184, *LUCID encrypted mempool*, written down as a
third subpool beside the account-nonce pool and the frame pool, with what a
builder commits and what the next block executes. The EIP is Draft; it was
read from ethereum/EIPs at commit `258836f9` (2026-10-07), sections
"Constants and parameters", "Overview", "Sealed transactions", "Extended
payload bid with ST-commitments", "Execution payload expansion", "Block
processing", "Rationale" ("Key publisher liability for non-reveal") and
"Security Considerations". Quotations below are from those sections unless
another is named. A clause marked *Interpretation* is this repository's
reading where the EIP leaves a choice open, and names decision record 0014.

A sealed transaction (ST) is a signed **ticket**, which pays and consumes its
sender's nonce, and a ciphertext that decrypts to the transaction to run. A
builder commits to STs in block $n$, in an order the protocol fixes by the
**ToB fee** each pays; the tickets are charged in block $n$; a key publisher
releases the keys once the commitment is safe; and the decrypted
transactions run at the top of block $n+1$, which refunds the unused gas and
most of the ToB fee to a sender whose key arrived. What it is for, and the
two-slot pipeline step by step, is not restated here.

The EIP leaves the pool's admission policy open: "The mempool must naturally
protect against spam and reject STs that have no chance of getting included"
(Rationale, "Key publisher liability for non-reveal"), and "there are no
fixed settings that can be established at this point for STs that should or
should not be propagated" (Security Considerations). This document states
the checks the EIP's validity rules imply, and keeps the policy itself as a
parameter (LU-8).

## What changes

A pool under a profile with `sealed` true has a sealed pool behind the
reservation tracker of MD-11 (`00-model.md` version 4). A builder commits
from it before taking any other transaction (LU-12), and executes its
parent's revealed commitments before any other transaction (LU-13), which
amends BB-3 and BB-4 of `03-block-building.md`. Under every other profile a
sealed transaction is refused with `ErrTxTypeNotSupported`.

## Profile

**LU-1. Parameters.**

| Parameter | `eip-8184` | Note |
| --- | --- | --- |
| `sealed` | true | false under the profile `off`, the default |
| `tob_gas_fraction_denominator` | 8 | `TOB_GAS_FRACTION_DENOMINATOR`; `tob_gas_limit` is the block's gas limit divided by it, rounded down |
| `tob_fee_fraction` | 128 | `TOB_FEE_FRACTION` |
| `max_st_commits` | 32 | `MAX_ST_COMMITS`, `MAX_ST_COMMITS_PER_IL` (2) times EIP-7805's `IL_COMMITTEE_SIZE` (16) |
| `max_bytes_per_st` | 262144 | `MAX_BYTES_PER_ST`, `2**24 // 64` |
| `max_tx_gas` | 16777216 | EIP-7825's cap, which "bounds the byte size of an ST" |
| `calldata_gas_per_byte` | 64 | *Interpretation*, decision record 0014: the factor `MAX_BYTES_PER_ST` is derived with |
| `st_slots` | 4096 | *Interpretation*, decision record 0014: the EIP sets no size; FP-1's `max_pending` |
| `price_bump` | 10 | *Interpretation*, decision record 0014: go-ethereum's, as NP-1's |
| `policy` | `any` | *Interpretation*, decision record 0014; `next-block` and `every-head` are variants (LU-8) |
| `evict_first` | `last` | *Interpretation*, decision record 0014; `unplaced` is a variant (LU-10), decision record 0015 |

**Source:** EIP-8184, Constants and parameters; EIP-7805, Constants.

## Errors

| Code | Clause | Meaning |
| --- | --- | --- |
| `ErrSTMalformed` | LU-4 | a `signature_id` other than 1, or a ciphertext that does not match its hash |
| `ErrSTExceedsToB` | LU-5 | a gas limit above the ToB segment's |
| `ErrSTNotIncludable` | LU-8 | the policy finds no place for it in the next block |

LU-4, LU-5, LU-9 and LU-10 also use go-ethereum's `ErrAlreadyKnown`,
`ErrTxTypeNotSupported`, `ErrInvalidSender`, `ErrOversizedData`,
`ErrGasLimitTooHigh`, `ErrFloorDataGas`, `ErrAlreadyReserved`,
`ErrNonceTooLow`, `ErrNonceTooHigh`, `ErrInsufficientFunds`,
`ErrFeeCapTooLow`, `ErrReplaceUnderpriced` and `ErrUnderpriced`.

## Sealed transactions

**LU-2. The object.** A sealed transaction carries the fields of its ticket a
pool reads, and, as MD-6 does for frames, the answers a node would find out
by decrypting it or by waiting for its key:

| Field | Meaning |
| --- | --- |
| `sender` | `ticket_from`, recovered from the ticket's signature |
| `nonce` | the ticket's nonce, the sender's account nonce |
| `max_fee` | `max_fee_per_gas` |
| `tip` | `max_priority_fee_per_gas` |
| `gas_limit` | the ticket's `gas_limit`, which the plaintext transaction's must equal |
| `max_tob_fee` | wei in total, not per gas |
| `max_preceding` | `max_preceding_commitments` |
| `key_publisher` | the address that releases its key |
| `fee_recipient` | `key_publication_fee_recipient` |
| `key_fee` | `key_publication_fee`, wei |
| `size` | bytes of the `SealedTransaction` as propagated |
| `signature_id` | the only valid value is `EC_DSA_TYPE`, 1 |
| `valid_signature` | false models a signature from which no sender can be recovered |
| `ciphertext_ok` | whether `keccak256(ciphertext_envelope)` equals `ciphertext_hash` |
| `revealed` | whether a valid key message for it is released in time and decrypts it (LU-13) |
| `used` | the plaintext transaction's `dual_gas_used` if revealed; default `gas_limit` |
| `to`, `pulls`, `pays`, `atomic` | the plaintext transaction's recipient, and what its execution pulls and pays, as MD-5's; default no recipient and nothing pulled or paid |
| `revert_used` | the plaintext transaction's `dual_gas_used` if its execution reverts (LU-13); default `used` |
| `label` | as MD-5's |

Its hash is MD-7's over every field; the model takes it as both the ST's
hash and its `ticket_hash`, which orders commitments (LU-6). **Source:**
EIP-8184, Sealed transactions, ST ticket, Ciphertext envelope, Key message
validity and decryption.

*Not modelled:* the plaintext transaction's other fields and effects, beyond
the gas it uses and the value it pulls and pays, and its sender, which can
differ from the ticket's sender; the ciphertext,
the key and the DEM; bundles, their `executable` bitfield and their key
publisher's signature.

**LU-3. The ticket's fee.** With $G$ the gas limit, $b$ a base fee per gas
and $k$ the key fee, an ST **can pay** at $b$ if
$\mathit{max\_fee} \cdot G \geq b G + k$. If it can, its fees at $b$ are

$$
\mathit{priority} = \min(\mathit{tip} \cdot G,\; \mathit{max\_fee} \cdot G - bG - k), \qquad \mathit{tob} = \min(\mathit{max\_tob\_fee},\; \mathit{max\_fee} \cdot G - bG - k - \mathit{priority})
$$

and its ticket fee is $bG + k + \mathit{priority} + \mathit{tob}$, which is at
most $\mathit{max\_fee} \cdot G$, its **cost**. **Source:** EIP-8184, Block
processing, the charging pseudocode.

## Admission

**LU-4. Static checks.** A pool MUST refuse a sealed transaction with the
first of these that applies:

1. `ErrAlreadyKnown` if it holds one with the same hash;
2. `ErrTxTypeNotSupported` if `sealed` is false;
3. `ErrSTMalformed` if `signature_id` is not 1;
4. `ErrInvalidSender` if the signature is not valid;
5. `ErrSTMalformed` if the ciphertext does not match its hash;
6. `ErrOversizedData` if `size` exceeds `max_bytes_per_st`;
7. `ErrGasLimitTooHigh` if `gas_limit` exceeds `max_tx_gas`;
8. `ErrFloorDataGas` if `gas_limit` is below `calldata_gas_per_byte` times
   `size`.

**Source:** EIP-8184, ST ticket (`signature_id`), Sealed transactions (the
ciphertext hash, which block processing checks and a node can check on
receipt), Constants (`MAX_BYTES_PER_ST`), Ciphertext envelope ("The
`gas_limit` must be sufficient to cover the calldata cost of the byte size of
the `SealedTransaction`"). *Interpretation:* the calldata cost of $s$ bytes
is $64s$, the cost `MAX_BYTES_PER_ST` is derived from, with no 21,000 base,
because $2^{24}/64$ is the bound the EIP states exactly; decision record
0014.

**LU-5. Checks against the head and the state.** With $b$ the pending base
fee (FEE-1) and the head's gas limit $L$, a pool MUST then refuse a sealed
transaction with the first of these that applies:

1. `ErrSTExceedsToB` if `gas_limit` exceeds
   $\lfloor L / \mathit{tob\_gas\_fraction\_denominator} \rfloor$, the ToB
   segment of a block with the head's gas limit, which no commitment's
   gas can exceed;
2. `ErrAlreadyReserved` if another subpool holds the sender (MD-11);
3. `ErrNonceTooLow` if `nonce` is below the sender's nonce, and
   `ErrNonceTooHigh` if it is above it;
4. `ErrInsufficientFunds` if the sender's balance is below its cost (LU-3);
5. `ErrFeeCapTooLow` if it cannot pay at $b$ (LU-3).

**Source:** EIP-8184, Block processing (the ticket's nonce and balance
assertions, and `assert max_fee >= base_fee + ticket.key_publication_fee`),
Key release ("the aggregate of all `gas_obligation` entries is within the
`tob_gas_limit`"), and Rationale ("reject STs that have no chance of getting
included"). *Interpretation:* a ticket that could not be charged in the next
block, or never fits a ToB segment, has no chance; a pool holds no sealed
transaction it could not include next, so there is no queue of future
nonces, as there is none in FP-7; decision record 0014.

**LU-6. Commitment order.** At base fee $b$, sealed transactions that can pay
MUST be ordered by descending ToB fee (LU-3), then by descending gas limit,
then by ascending hash. **Source:** EIP-8184, Block processing, the
"ST-commitment ordering rule" (descending `commitment_tob_fee`, descending
`gas_obligation`, ascending `commitment_root`), for commitments that are not
bundles.

**LU-7. Selection.** The selection from a set of sealed transactions, against
a state, at base fee $b$ and minimum tip $t$, is computed as follows:

1. The candidates are those that can pay at $b$, whose `nonce` equals the
   sender's nonce, whose sender's balance covers the ticket fee at $b$, and
   whose priority fee at $b$ is at least $tG$.
2. Taking candidates in LU-6 order, each is selected if fewer than
   `max_st_commits` are selected, the selected gas limits plus its own do not
   exceed the ToB segment of LU-5, and the number already selected is at most
   its `max_preceding`. Otherwise it is passed over, and the next is
   considered.

**Source:** EIP-8184, Extended payload bid (at most `MAX_ST_COMMITS`
commitments, `gas_obligation` within `tob_gas_limit`), Block processing (the
order, and "`max_preceding_commitments` executed before the ST, acting as an
upper bound"), and Inclusion lists with STs and bundles (the attesters'
check). *Interpretation:* the EIP leaves the choice to the builder; this is
the rule attesters enforce on an inclusion list's entries, "If in any
instance the ST-commitment could be placed in `st_commitments` at the
position determined by the ST-commitment ordering rule without violating its
`max_preceding_commitments`, but is not included, attesters vote against the
block", applied to every candidate a builder holds; decision record 0014.

**LU-8. Policy.** After LU-4, LU-5 and LU-9, a pool MUST refuse with
`ErrSTNotIncludable` a sealed transaction that its `policy` finds no place
for:

- `any`: none is refused here.
- `next-block`: one that the selection (LU-7) over the pool's sealed
  transactions and itself, less any it would replace, against the pool's
  state at the pending base fee with a minimum tip of 0, does not select.
- `every-head`: as `next-block`, and at every head as well (LU-11).

*Interpretation:* "no chance of getting included" is read three ways, as
nothing beyond LU-5, as no place in the next block when it arrives, and as no
place in the next block ever, which bounds a pool by one block's
commitments; decision record 0014.

**LU-9. Replacement.** After LU-4 and LU-5, a sealed transaction $t$ from a
sender the pool holds one for, $p$, MUST replace $p$ if and only if its
`max_fee` and `tip` pass NP-11 against $p$'s and

$$
t.\mathit{max\_tob\_fee} \geq \left\lfloor \tfrac{(100 + \beta)\, p.\mathit{max\_tob\_fee}}{100} \right\rfloor
$$

with $\beta$ = `price_bump`; otherwise the pool MUST refuse it with
`ErrReplaceUnderpriced`. *Interpretation:* the EIP says nothing of
replacement; this is go-ethereum's rule for a dynamic-fee transaction, with
the ToB fee as a third price that need not rise from zero; decision record
0014.

**LU-10. Capacity.** After LU-8, a pool holding `st_slots` sealed
transactions that receives a new one replacing none MUST pick a victim among
them, admit the new one only as `evict_first` says, and then drop the victim;
otherwise it MUST refuse the new one with `ErrUnderpriced`. At the pending
base fee:

- `last`: the victim is the last of them in LU-6 order, and the new one is
  admitted if it comes before the victim.
- `unplaced`: with the selection (LU-7) over them and the new one, at a
  minimum tip of 0, the victim is the last of them in LU-6 order that the
  selection does not take, or the last of them if it takes them all; the new
  one is admitted if it comes before the victim, or if the selection takes it
  and not the victim.

*Interpretation:* the EIP sets no size and no eviction order. `last` uses the
commitment order, the only order it gives and the order a builder takes;
decision record 0014. `unplaced` drops first what the next block would pass
over, a variant experiment 07 measures; decision record 0015.

**LU-11. A new head.** On `reset`, a pool MUST drop every sealed transaction
whose `nonce` is below its sender's nonce, whose sender's balance is below
its cost, that cannot pay at the new pending base fee, or whose gas limit
exceeds the new head's ToB segment; and, under `every-head`, every one the
selection (LU-7) over what remains, at the new pending base fee with a
minimum tip of 0, does not select. A dropped transaction releases its
sender (MD-11). *Interpretation:* LU-5 applied again, as FP-15 applies the
frame pool's checks again; decision record 0014.

## Building a block

**LU-12. Commitments.** A builder with minimum tip $m$ building block $n$
at base fee $b$ MUST commit the selection (LU-7) over its pool's sealed
transactions against its parent's post-state at $b$ and $m$, before it takes
any other transaction. Each committed ticket, in commitment order, increases
its sender's nonce by one and takes the ticket fee at $b$ from its balance,
and the coinbase receives its priority fee. The tickets take none of block
$n$'s gas. **Source:** EIP-8184, Overview, Execution payload expansion
(`st_tickets` first in the payload) and Block processing (the charge).
*Interpretation:* the EIP gives tickets no gas of their own; their gas is
the ToB segment of the next block (LU-13); decision record 0014.

**LU-13. Decrypted transactions.** Block $n+1$ MUST execute, before any other
transaction, each of block $n$'s commitments that is `revealed`, in
commitment order. Each executes its pulls and pays into and out of `to` as
BB-5 of `03-block-building.md` executes an account-nonce transaction's,
reverting as BB-5 says, against the state its earlier commitments left;
with $u$ its `revert_used` if it reverted and its `used` otherwise, it
takes $u$ of block $n+1$'s gas limit, and counts $u$ in its `gas_used`
(BB-4); then its sender receives
$b_n (G - u) + \lfloor \mathit{tob} \cdot (F - 1) / F \rfloor$,
with $b_n$ block $n$'s base fee, $\mathit{tob}$ the ToB fee it paid and $F$
`tob_fee_fraction`, and its `fee_recipient` receives its key fee. A
commitment that is not revealed executes nothing and returns nothing. The
regular transactions of BB-3 have the gas left. **Source:** EIP-8184, Block
processing ("The PT is then executed as a regular transaction, except that
it bypasses the ordinary EIP-1559 fee-cap validation and no gas fee is
charged", and "The unused gas, previously charged to the `parent_ticket`
according to the base fee of the previous block, is then returned to the
sender, together with the `parent_tob_fee` reserved for the penalty"),
Rationale ("When the encrypted mempool is underutilized, the unused gas
allocation does not encroach on the block gas limit") and its section User
welfare ("Trusted intermediaries can offer, e.g., offchain revert
protection, that the public path cannot replicate"), so a decrypted
transaction that reverts is executed and pays for its gas, and BB-7 does
not drop it.

## Not modelled

- Inclusion lists and their enforcement (EIP-7805), `tob_gas_limit_per_il`,
  and which inclusion-list entries a block must take.
- Bundles, their `executable` bitfield, `gas_obligation`, `commitment_key`
  and key publisher signature.
- The payload bid, key messages, key-timeliness votes and the PTC; whether a
  key is released is the field `revealed`.
- Recovery under a rejected payload, the same-slot variant and the frame
  transaction integration (Rationale, Alternative specifications).
- What the decrypted transaction does beyond its gas, pulls and pays, the header it is
  executed against, `SLOTNUM`, and the deferred EIP-2935 and EIP-4788
  updates.
- How a node relays sealed transactions: the simulator gossips them as
  transactions of their `size` (`sim/emem_sim/network.py`).

## Version notes

- **Version 2.** LU-2 gains the plaintext transaction's `to`, `pulls`,
  `pays`, `atomic` and `revert_used`, and LU-13 executes them as BB-5 of
  `03-block-building.md` version 4 does, reverting at the gas the plaintext
  used (decision record 0045). A sealed transaction that leaves them at
  their defaults pulls and pays nothing, never reverts, and is the same
  transaction as under version 1, so every vector of this document was
  re-read against version 2 and needed no change but its version;
  `lu-13-decrypted.json` gains the cases of a sealed round.
