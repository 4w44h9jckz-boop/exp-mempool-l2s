# 0031. An authorization carries its nonce, and a hot wallet signs one at its next nonce

Date: 2026-10-09. Status: accepted.

## Context

The plan's item 7 asks what throughput NP-6 leaves a delegated hot wallet,
which it gives one transaction in flight, and what pending authorizations do
to their authorities (NP-7). The pool clauses are go-ethereum's and have
vectors (`conformance/vectors/nonce-pool/np-06-07-delegation.json`); the
block did not. `03-block-building.md` version 1 applied every authorization
of a set code transaction: each authority's code became the delegation
indicator and its nonce rose by one, whatever its state. An authorization had
no nonce of its own in the model (MD-5 version 4).

EIP-7702 at `258836f9` (Final) does not apply every one. Its Behavior
section processes the list "after the sender's nonce is incremented", and for
each tuple verifies, among other steps, that "the code of `authority` is
empty or already delegated" (step 5) and that "the nonce of `authority` is
equal to `nonce`" (step 6); "If any step above fails, immediately stop
processing the tuple and continue to the next tuple in the list." The second
half of item 7 is exactly that race: an authorization signed for an account
that keeps sending is spent by the account's own next transaction, or spends
that transaction's nonce, depending on which a block takes first. NP-7 limits
the authority to one transaction in the pool, which bounds the race and does
not remove it. Version 1 could show only the second outcome.

## Decision

1. **An authorization may carry its nonce** (MD-5, `00-model.md` version 5).
   `authorities` lists each authority alone or paired with its tuple's nonce.
   Alone, the tuple carries the nonce its authority has when the tuple is
   processed. That is a convention of the model, not a reading of the EIP: it
   keeps every vector written before this record meaning what it meant, and
   it is what an authorization signed for the right nonce does.
2. **The block checks steps 5 and 6** (BB-5, `03-block-building.md` version
   2), after the sender's nonce has risen and before `value` and `writes`,
   and skips an authorization that fails either, without failing the
   transaction. The sponsor still pays its intrinsic gas, 25,000 a tuple
   (FEE-3). The chain id, the signature, the refund of step 7 and a
   delegation to the zero address are not modelled; `bb-05-apply.json` gains
   four cases, each checked against a mutation of the reference that it must
   catch.
3. **The pool is unchanged.** go-ethereum's `validateAuth` counts an
   authority's pooled transactions and does not read a tuple's nonce, and
   neither does NP-7.
4. **A hot wallet's rules** (`HotWallet` in the simulator). Its transfers go
   to one node a sender. While its node's head shows the account without
   code it sends by one rule and, once it shows a delegation, by another:
   `at once`; `serial`, one transaction in flight, the next after its node
   imports the block that includes the last; or `batch`, as `serial` with
   every transfer waiting in one transaction, as a delegated account's code
   can make several calls. A batch is priced at 21,000 gas a transfer, as if
   each were sent alone, so it saves slots and not gas: the gas a delegate's
   loop costs is not read from a source here. A transaction its node refuses
   waits for the next import; a transfer whose nonce a block used for
   something else is sent again after the wallet's still-pending transfers.
5. **A hot wallet signs at its next nonce.** Asked by a sponsor, the wallet
   signs each account's authorization for the nonce after everything it has
   sent, and either keeps sending (`next`), stops sending for that account
   until the delegation shows or the sponsor reports the authorization skipped
   (`pause`), or stops and signs only once nothing it sent for the account is
   waiting for a block (`drain`). These are three wallets, not a reading of
   any source: nothing specifies how a wallet signs an authorization for a
   sponsor.
6. **A sponsor batches and retries** (`Upgrade`). It sends the next batch
   of accounts not yet delegated in one type 4 transaction, at a tip of its
   own, to one node, and the next after its node imports the block that
   includes it. An account whose authorization the block skipped keeps its
   place; a batch its node refused, or for which a wallet has not signed yet,
   is asked for and sent again after the next import.

## Consequences

- `00-model.md` version 5 and `03-block-building.md` version 2; every vector
  of both was re-read and moved to the new version.
- The reference applies authorizations as BB-5 version 2 says. No experiment
  before 22 sends a set code transaction, so no committed result moves.
- Experiment 22 measures a hot wallet under NP-6 and a sponsor's upgrade of
  sixteen busy accounts under NP-7 and BB-5.
