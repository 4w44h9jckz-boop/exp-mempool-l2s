# 00. The model: accounts, heads, transactions, the pool interface, fees

Version 11, 2026-10-20. Version 1 left the EIP-8250 nonce fields out of
FEE-4 and had no `finalize` operation, version 2 had no dependency frames,
version 3 had no sealed transactions, version 4 gave an authorization no
nonce of its own, version 5 gave a frame transaction no admission claim,
version 6 did not say how much of a transaction's gas is state gas, and
version 7 had no transaction that takes value from accounts that signed for
it, version 8 priced every calldata byte as non-zero and had no client
verdict, version 9 had no stake and no storage association, and version 10
put every dependency frame at mode 3; see the version notes at the end.

Every other document in this directory talks about the objects defined here.
The model keeps exactly the fields a transaction pool reads and drops the rest:
there are no signatures to recover, no RLP, no EVM. Where a client would run
code to find something out, the model carries the answer as data, and clause
MD-6 says which answers those are. `11-surface.md` specifies the layer that
turns a real transaction into the model's: its bytes, its hash, and an
execution client's answer for the validation prefix.

## Accounts and state

**MD-1. Addresses.** An address is a non-empty string compared by equality.
Implementations MUST NOT interpret its contents, except that the profiles of
`02-frame-pool.md` name a few distinguished addresses. Vectors use short names
such as `alice`.

**MD-2. Accounts.** An account has:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `nonce` | integer $\geq 0$ | 0 | the account nonce |
| `balance` | integer $\geq 0$ | 0 | balance in wei |
| `code` | string | `""` | runtime code, compared by equality only; `""` is the empty code hash |
| `storage` | map integer to integer | empty | storage slots; an absent slot reads 0 |
| `nonce_seqs` | map integer to integer | empty | EIP-8250 keyed nonce sequences for keys other than 0; an absent key reads 0 |
| `withdrawal` | integer $\geq 0$ | 0 | the pending delayed withdrawal of a canonical paymaster instance (EIP-8141, Paymasters) |
| `stake` | integer $\geq 0$ | 0 | the stake ERC-8421's Staking Registry reports for the account, in wei (`14-erc-8421.md`, AM-3) |
| `unstake_delay` | integer $\geq 0$ | 0 | the unstake delay it reports, in seconds |
| `withdrawing` | boolean | false | whether the account has begun to withdraw its stake |

A `code` value that starts with `0xef0100` is an EIP-7702 delegation indicator
and the rest of the string is the delegate. Any other non-empty value is
contract code.

**MD-3. State.** A state maps addresses to accounts. An address with no entry
reads as the default account. The key-0 nonce sequence of EIP-8250 is the
account `nonce`: `nonce_seq(a, 0)` MUST read `nonce(a)`.

**MD-4. Heads.** A head is the header a pool validates against: `number`,
`timestamp` (seconds), `gas_limit`, `gas_used` and `base_fee`. The *pending
base fee* is the base fee of the block that will be built on the head, given
by FEE-1.

## Transactions

**MD-5. Account-nonce transactions.** Transaction types 0 (legacy), 1 (access
list), 2 (dynamic fee), 3 (blob) and 4 (set code) carry:

| Field | Meaning |
| --- | --- |
| `type` | 0, 1, 2, 3 or 4 |
| `sender` | the recovered sender |
| `nonce` | the account nonce it consumes |
| `gas` | the gas limit |
| `max_fee` | `max_fee_per_gas`; for types 0 and 1, the gas price |
| `tip` | `max_priority_fee_per_gas`; for types 0 and 1, the gas price |
| `value` | wei transferred to `to` |
| `to` | the recipient, or absent for contract creation |
| `data_size` | calldata length in bytes; the model treats every byte as non-zero |
| `size` | the encoded size in bytes; default $110 + \mathit{data\_size}$ |
| `authorities` | for type 4: the addresses that signed the authorization tuples, in order, each alone or paired with the nonce its tuple carries; alone, the tuple carries the nonce its authority has when the tuple is processed (BB-5; decision record 0031) |
| `delegate` | for type 4: the address the authorizations delegate to |
| `valid_signature` | false models a signature from which no sender can be recovered |
| `gas_used` | gas the transaction uses if included; default `gas` |
| `state_gas_used` | the part of `gas_used` that is state gas under EIP-8037, at most `gas_used`; default 0 |
| `writes` | storage writes the transaction's execution performs if included, as (address, slot, value) |
| `pulls` | value its execution takes from accounts on their signatures and moves to `to`, as (account, amount), in order; default none |
| `pays` | value its execution moves from `to` to accounts, as (account, amount), in order; default none |
| `atomic` | whether a pull its account cannot cover reverts the transaction (true, the default) or is skipped (false) |
| `revert_gas_used` | gas the transaction uses if it reverts (BB-5 of `03-block-building.md`); default `gas_used` |
| `label` | free text that is part of the transaction's identity |

A pull is an ERC-3009 `receiveWithAuthorization` read with ether as the
unit: the account signed an authorization naming `to` as the payee, and
the sender submits it. A shuffle round, as an earlier design study
specified one, settles this way, every input's unit pulled and every output
paid in one transaction. A pool reads none of these four fields, since none
changes what a pool checks; they matter only when a block applies the
transaction.
**Source:** ERC-3009 (Draft) from ethereum/ERCs at `c73cd77c`, read
2026-10-13, `receiveWithAuthorization` ("an additional check to ensure that
the payee's address matches the caller of this function"). *Interpretation*,
decision record 0045: the unit is ether, and a skipped pull (`atomic`
false) is EIP-7702's skipped tuple, which a lock at inclusion uses, as the
registrations of that study's native shuffle round do.

Its cost is

$$
\mathit{cost} = \mathit{gas} \cdot \mathit{max\_fee} + \mathit{value},
$$

which is go-ethereum's `Transaction.Cost` without the blob term.
**Source:** go-ethereum `core/types/transaction.go`, `Cost`.

**MD-6. Frame transactions.** A frame transaction (type 6) carries `sender`,
`nonce_keys` (a strictly increasing tuple of integers, default `(0,)`),
`nonce_seq`, `frames`, `signatures`, `max_fee`, `tip`, `size` (default
$200 + D$, with $D$ as in FEE-4), `label`, `writes` (as in MD-5: the storage
writes of the frames after the prefix), `gas_used` (default: its
`max_gas`), `state_gas_used` (the part of `gas_used` that is state gas,
default: the sum of its frames' `state_gas`, which FEE-4 counts in
`max_gas`), and `claim` (default absent), an admission claim of
`10-claim-gated-admission.md` carrying `sender`, `nonce_keys` (default
`(0,)`), `nonce_seq`, `epoch`, `valid` (default true) and `salt` (default
empty), which only that document's profile reads. A **frame** carries the EIP-8141 fields
`mode` (0 `DEFAULT`, 1 `VERIFY`, 2 `SENDER`, and AG-1's `dep_frame_mode`, 3 or
4, for an EIP-8288 dependency frame, `05-aggregation.md`), `flags`, `target` (absent means `sender`),
`exec_gas` and `state_gas` (the two `limits`), `value` and `data_size`; for a
dependency frame, `deps`, the triples its `data` encodes, each as `(scheme,
data_hash, vk_hash)` with `scheme` an integer and the two hashes strings
compared by equality (AG-2); and, because the model does not execute code,
**what a node simulating the frame would observe**:

| Field | Meaning |
| --- | --- |
| `approves` | the scope the frame's code calls `APPROVE` with, or absent if it never does |
| `reverts` | the frame reverts |
| `opcodes` | the set of opcode names from the banned list of `02-frame-pool.md` the frame executes, and `UNASSIGNED` if it executes an unassigned opcode and `OOG_REVERT` if it reverts by running out of gas (`14-erc-8421.md`, AM-8) |
| `reads` | storage slots read, as (address, slot, expected); the frame's code approves only if each slot with an `expected` value holds it; a fourth element, when present, is the address a tracer finds the slot associated with (`14-erc-8421.md`, AM-9) |
| `writes` | state writes, as (address, slot, value), with the same optional fourth element |
| `calls` | addresses reached through `CALL*` or `EXTCODE*` |
| `installs_code` | for a deploy frame: the code it installs at `sender`, or absent |
| `deadline` | for an expiry verifier frame: the deadline its calldata encodes |

A frame whose resolved target has empty code runs the default code, whose
behaviour is fully defined by the EIP, so its declared observation fields are
ignored (FP-9).

A frame transaction also carries `zero_bytes` (default 0), how many of the
$D$ bytes FEE-4 counts are zero, and `verdict` (default absent), the answer an
execution client gave for its validation prefix at the pool's head: `ok`, or
one error code of FP-3, FP-8 or FP-9, or `ErrFrameClientRefused` for an answer
`11-surface.md` cannot map (SF-4). A transaction with a `verdict` has its
prefix judged by it rather than by its frames' observation fields (FP-8). A
transaction that leaves both at their defaults is the same transaction as
under version 8. **Source:** EIP-8141, Gas Accounting (`tokens_in`) and
Acceptance Algorithm, step 4. *Interpretation*, decision record 0051: a pool
that does not execute the EVM takes the prefix's outcome from a client that
does, as an input like any other observation. A **signature** carries `scheme` (`secp256k1`, `p256` or
`arbitrary`), `signer` (absent means `sender`), `canonical_msg` (true when
`msg` is empty, so the signature is over the canonical hash), `valid`, and for
`arbitrary` its byte `length`.
**Source:** EIP-8141, Frame Transaction, Signature Validation, Default code.

**MD-7. Identity.** A transaction is identified by its hash. In the model the
hash is a deterministic function of every field listed in MD-5, MD-6 or,
for a sealed transaction, LU-2 of `06-lucid.md`, `label` included, so two transactions with equal fields are the same
transaction and a different `label` makes a different one. A frame
transaction's `verdict` is left out: it is a client's answer about the
transaction at one head, not part of it, and a new answer at the next head
does not make a new transaction. At the surface the hash is the one the
chain uses (`11-surface.md`, SF-3).

## The pool interface

**MD-8. Operations.** A pool is a deterministic state machine with four
operations and no other inputs:

- `add(txs, now)` takes a list of transactions and returns one result per
  transaction: `ok`, or one error code from the tables of `01-nonce-pool.md`,
  `02-frame-pool.md` and the documents that add to them.
- `reset(head, state, now, verdicts)` tells the pool that `head` is the new
  canonical head and `state` its post-state. The pool does not execute
  blocks: it learns what was included only through the nonces, balances, code
  and storage of `state`. `verdicts`, empty by default, maps the hash of a
  pending transaction that carries a `verdict` (MD-6) to the client's answer
  at `head`; a transaction it does not name keeps the verdict it has.
- `tick(now)` lets time pass, for the rules that depend on it.
- `finalize(blocks, now)` tells the pool that `blocks` became final. Each
  block is given as its `number` and, for each sender, the summed `gas_used`
  of that sender's frame transactions in it. A pool that keeps nothing from
  finality ignores it; only `04-matcha.md` reads it.

`now` is a number of seconds. A pool MUST NOT read a clock.

**MD-9. Observables.** A pool exposes `pending()` and `queued()`, each a map
from sender to that sender's transactions in nonce order; `status(hash)`, one
of `pending`, `queued` or `unknown`; and the ordered list of transactions it
offers a builder (BB-1). Vectors check only these, the re-simulations of
FP-15, and the observables a later document adds for its own rules
(`04-matcha.md`, MA-12).

**MD-10. Ties.** Where a clause orders transactions and the source leaves a tie
unresolved, the transaction the pool received later MUST sort first among
equals for eviction and last among equals for inclusion, which is the order
EIP-1559's "Transaction Ordering" note asks for. Where a clause orders senders
and the source leaves a tie unresolved, senders MUST sort by address.
*Interpretation*: go-ethereum leaves such ties to `container/heap` and to Go's
randomised map order. Decision record 0002.

**MD-11. Subpools.** A pool in this model is three subpools behind one
reservation tracker, which holds each sender for one subpool at a time: the
account-nonce pool of `01-nonce-pool.md` for types 0 to 5, which refuses
every type but 0, 1, 2 and 4; the frame pool of `02-frame-pool.md` for type
6; and the sealed pool of `06-lucid.md` for EIP-8184's sealed transactions,
which refuses them all unless its profile takes them. `add` hands each
subpool its share of the list in the original order, the account-nonce
pool's share first and the sealed pool's last; a sealed transaction is
pending while the sealed pool holds it. **Source:** go-ethereum
`core/txpool/txpool.go`, `Add`, which splits a batch by subpool in the same
way, and `core/txpool/reserver.go`.

## Fees and gas

**FEE-1. The next base fee.** For a head with gas limit $L$, gas used $U$ and
base fee $b$, with target $T = \lfloor L / 2 \rfloor$:

$$
b' =
\begin{cases}
b & U = T \\
b + \max\left(1, \left\lfloor \left\lfloor \frac{b (U - T)}{T} \right\rfloor / 8 \right\rfloor\right) & U > T \\
\max\left(0, b - \left\lfloor \left\lfloor \frac{b (T - U)}{T} \right\rfloor / 8 \right\rfloor\right) & U < T
\end{cases}
$$

**Source:** go-ethereum `consensus/misc/eip1559/eip1559.go`, `CalcBaseFee`
(elasticity multiplier 2, change denominator 8); EIP-1559.

**FEE-2. Effective tip.** At base fee $b$, a transaction's effective tip is
$\min(\mathit{tip}, \mathit{max\_fee} - b)$, which is negative when
$\mathit{max\_fee} < b$. **Source:** go-ethereum `core/types/transaction.go`,
`EffectiveGasTip`.

**FEE-3. Intrinsic gas of an account-nonce transaction.** With every calldata
byte non-zero,

$$
g_{\text{intr}} = 21000 + 32000 \cdot [\mathit{to} \text{ absent}] + 16 \cdot \mathit{data\_size} + 25000 \cdot \lvert \mathit{authorities} \rvert ,
$$

and the EIP-7623 floor is $g_{\text{floor}} = 21000 + c_{\text{floor}} \cdot 4 \cdot \mathit{data\_size}$
with $c_{\text{floor}} = 10$ in the `geth` profile. Access lists and the
initcode word cost are not modelled. **Source:** go-ethereum `core/state_transition.go`,
`IntrinsicGas` and `FloorDataGas`, at the Prague rules; EIP-7623; EIP-7702.

**FEE-4. Gas of a frame transaction.** With $Z$ of the calldata bytes zero,
none by default, and signature verification costs of 2800 (`secp256k1`), 6700 (`p256`) and 100
(`arbitrary`):

$$
g_{\text{intr}} = 12000 + 475 \cdot \lvert \mathit{frames} \rvert + 16 \cdot D - 12 \cdot Z + \sum_{\sigma} c(\sigma) + 6000 \cdot V
$$

where $D$ is the total frame calldata in bytes plus, for each signature entry,
20 bytes if its `signer` is given, 32 bytes if its `msg` is not canonical, and
the signature's length (65 for `secp256k1`, 128 for `p256`, the entry's
`length` for `arbitrary`), plus the $N$ bytes of the nonce fields below; $Z$
is the transaction's `zero_bytes`, how many of those $D$ bytes are zero; and
$V$ counts the frames that carry value to a target other than `sender`. A
zero byte is one token and any other byte four, at 4 gas a token, which is
$16 D - 12 Z$; the floor counts four tokens for every byte, zero or not, so
$Z$ does not enter it.

The nonce fields are priced as transaction data (EIP-8250, "Transaction
payload"): $N$ is the length of $\mathit{rlp}(\mathit{nonce\_keys}) \Vert \mathit{rlp}(\mathit{nonce\_seq})$
with every integer in canonical minimal form. An integer $x$ encodes in
$r(x) = 1$ byte if $x < 128$ (zero is the single byte `0x80`), and otherwise
in $r(x) = 1 + \lceil \mathit{bits}(x) / 8 \rceil$ bytes. A list whose items
encode in $P$ bytes in total encodes in $1 + P$ bytes if $P \leq 55$, and in
$1 + \lceil \mathit{bits}(P) / 8 \rceil + P$ bytes otherwise. So

$$
N = r_{\text{list}}\left(\sum_{k \in \mathit{nonce\_keys}} r(k)\right) + r(\mathit{nonce\_seq}),
$$

which is 3 for the default `nonce_keys` $(0)$ at `nonce_seq` 0, and 35 for one
256-bit key at `nonce_seq` 0. *Interpretation:* EIP-8250 adds
`tokens_in(nonce_calldata)` to `calldata_tokens`, a name EIP-8141 at the
pinned commit no longer defines: its floor counts `calldata_floor_tokens`
with `floor_tokens_in`. With every byte non-zero the two counts are equal, so
the model adds $4N$ tokens to the floor under either reading. Decision record
0006.

$$
\mathit{max\_gas} = \max\left(g_{\text{intr}} + \sum_f (e_f + s_f),\; g_{\text{floor}} + \sum_f s_f\right),
\qquad
\mathit{max\_cost} = \mathit{max\_gas} \cdot \mathit{max\_fee}
$$

with $g_{\text{floor}} = 12000 + 475 \cdot \lvert \mathit{frames} \rvert + \sum_\sigma c(\sigma) + 6000 \cdot V + 16 \cdot 4 \cdot D$
and $e_f$, $s_f$ the frame's execution and state limits. Blob gas is not
modelled. **Source:** EIP-8141, Gas Accounting and Transaction settlement;
EIP-8250, Transaction payload.

*Not modelled:* the state gas EIP-8250 charges a payment-scoped `APPROVE` for
each nonce key used for the first time (`KEYED_NONCE_FIRST_USE_STATE_GAS`,
97920 under EIP-8037's current constants), which the approving frame's state
limit must cover. The model neither requires the limit nor charges it: a
transaction that pays it says so in its frame's `state_gas` and its
`state_gas_used`, which a block counts in a dimension of its own only under
`03-block-building.md`'s rule `two` (version 3).

## Version notes

- **Version 2.** FEE-4 prices the EIP-8250 nonce fields, which version 1 left
  out: every frame transaction's $D$ grows by $N$, 3 bytes for the default
  nonce fields, so its intrinsic gas rises by $16N$ and its floor by $64N$.
  MD-8 gains `finalize`, and MD-9 admits observables that later documents
  add. Every vector of this document was re-read against
  version 2, and the FEE-4 vectors were corrected by hand.
- **Version 3.** MD-6 gains mode 3 and the `deps` of an EIP-8288 dependency
  frame, which `05-aggregation.md` needs (decision record 0012). Nothing this
  document computes changes: a dependency frame's `data_size` and `exec_gas`
  enter FEE-4 as any frame's do. Every vector of this document was re-read
  against version 3 and needed no change but its version.
- **Version 4.** MD-11 gains a third subpool, the sealed pool of
  `06-lucid.md` (decision record 0014), and MD-7 and MD-8 name it. A pool
  whose sealed profile is `off` behaves as under version 3. Every vector of
  this document was re-read against version 4 and needed no change but its
  version.
- **Version 5.** MD-5's `authorities` may carry the nonce of each
  authorization tuple, which `03-block-building.md` version 2 checks
  (decision record 0031). An authority given alone behaves as under version
  4, and FEE-3 counts a tuple the same either way. Every vector of this
  document was re-read against version 5 and needed no change but its
  version.
- **Version 6.** MD-6's frame transaction may carry an admission `claim`,
  which `10-claim-gated-admission.md` checks (decision record 0037). A
  transaction without one is the same transaction as under version 5, and
  nothing FEE-4 computes reads the claim. Every vector of this document was
  re-read against version 6 and needed no change but its version.
- **Version 7.** MD-5 and MD-6 gain `state_gas_used`, the part of
  `gas_used` that is EIP-8037 state gas, which `03-block-building.md`
  version 3 counts under its rule `two` (decision record 0043). It is part
  of `gas_used`, so nothing a pool or FEE-4 computes changes, and a
  transaction that leaves it at its default is the same transaction as
  under version 6. Every vector of this document was re-read against
  version 7 and needed no change but its version.
- **Version 8.** MD-5 gains `pulls`, `pays`, `atomic` and
  `revert_gas_used`, which `03-block-building.md` version 4 applies and
  reverts (decision record 0045). No pool reads them, and a transaction that
  leaves them at their defaults is the same transaction as under version 7.
  Every vector of this document was re-read against version 8 and needed no
  change but its version.
- **Version 9.** MD-6's frame transaction gains `zero_bytes` and `verdict`,
  FEE-4's intrinsic gas subtracts $12 Z$, and MD-8's `reset` takes the
  verdicts at the new head (decision record 0051). They exist for
  `11-surface.md`, where a transaction has real bytes and a pool without an
  EVM asks a client about its prefix. With both left at their defaults a
  transaction is the same transaction as under version 8 and costs the same
  gas, and a `reset` with no verdicts is version 8's. Every vector of this
  document was re-read against version 9 and needed no change but its
  version.

- **Version 10.** MD-2's account gains `stake`, `unstake_delay` and
  `withdrawing`, what ERC-8421's Staking Registry reports for it; MD-6's
  reads and writes gain the address a slot is associated with, and a
  frame's observed opcodes may include `UNASSIGNED` and `OOG_REVERT`. Only
  `14-erc-8421.md` reads them (decision record 0061). With every new field
  at its default, a state and a transaction are version 9's, and every
  vector of this document holds and now says version 10.

- **Version 11.** A dependency frame's mode is AG-1's `dep_frame_mode`: 3
  under `eip-8288`, as before, and 4 under `eip-8288-master` (decision record
  0063). Under every profile but that one nothing changes, and every vector of
  this document holds and now says version 11.
