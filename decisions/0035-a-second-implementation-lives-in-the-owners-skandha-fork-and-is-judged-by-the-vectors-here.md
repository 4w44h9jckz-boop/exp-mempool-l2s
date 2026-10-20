# 0035. A second implementation lives in the owner's skandha fork, and is judged by the vectors here

Date: 2026-10-13. Status: accepted.

## Context

The owner forked etherspot/skandha, an ERC-4337 bundler in TypeScript, to
`4w44h9jckz-boop/skandha` at `acba0d8`, and asked to "make skandha our base".
Asked what that should mean, the owner chose a second implementation:
EIP-8141's frame-transaction pool rules, and later an ERC-8421 profile, built
into the fork in TypeScript and checked by the hand-written vectors in
`conformance/vectors/`, with this repository's specification staying the
normative one and the Python reference and simulator staying as they are.

A bundler is the natural host. ERC-8421, "Frame Transaction Alternative
Mempools" (Draft, ethereum/ERCs pull request 2028 at `493ba8ac`, read and
reported on in the session of 2026-10-13), describes pools for frame
transactions run alongside the public one with ERC-7562's stake and
reputation, which is the machinery skandha already has for user operations.
skandha is not an execution client and holds no account-nonce transactions.

So far one implementation has played the vectors, and the same hands wrote
the vectors, the clauses and the code. A vector can still depend on that
code without anyone noticing: on Python's integers, which have no width; on
its dictionaries, which keep insertion order; on the reference's hash of a
transaction (MD-7 asks only for a deterministic function of every field); or
on the exact decimal of a configured factor. A second implementation in a
language without those defaults finds such a dependence when a vector fails
there and passes here.

It does not, by itself, test that the clauses are unambiguous. That needs an
implementation written from the clauses by someone who has not read the
reference, and the first version in the fork is a port of
`ref/python/emem/`, read alongside the clauses. The difference is stated
rather than hidden: the port tests the vectors' independence from Python and
gives the fork a pool; it does not count as a second reading of the
specification.

## Decision

1. **The specification here stays normative, and the vectors here judge the
   fork.** The fork's package is `packages/framepool` on its branch
   `claude/laughing-turing-jj6c9m`. It is written to the clauses' names
   (FP-11, MA-6 and so on in its comments, as the reference is) and takes no
   dependency outside Node's standard library at run time, so that it can be
   read and moved into the bundler's executor later.
2. **The vectors are copied, never edited.** The fork holds a byte-for-byte
   copy of `conformance/vectors/` at a named commit of this repository,
   with a list of each file's SHA-256, and its test checks the list before it
   plays a case. A vector the fork disagrees with is settled here, by
   `conformance/README.md`'s three cases, and copied again; a vector that
   turns out to depend on the reference rather than the clause is case 3,
   the clause moves, and its document's version with it.
3. **What the fork skips is computed from the case, not listed by name.** A
   case is played when the fork has everything it uses, and reported as
   skipped otherwise with what it needs: the account-nonce pool of
   `docs/spec/01-nonce-pool.md`, the sealed pool of `06-lucid.md`, block
   building (`03-block-building.md`), inclusion lists (`07-focil.md`) or an
   aggregator (`05-aggregation.md`, AG-5 to AG-9). A list of names would let
   a failing case be quietly moved onto it; a rule over the case's contents
   cannot be. The first version covers FEE-1, FEE-3 and FEE-4, the frame
   pool's clauses under every profile, MATCHA, the admission and reset
   rules of recent roots and expiring nonces, and the static and admission
   rules of dependency frames.
4. **The pool's internal shortcuts are not ported where a plain loop gives
   the same answer.** The reference keeps FP-14's candidates and MA-8's ages
   in heaps with stale entries; the fork takes the minimum over the pool.
   Both pick the same transaction, and the fork's version is the clause as
   written.
5. **An ERC-8421 profile comes here first.** It is a profile of
   `docs/spec/02-frame-pool.md` or a document of its own, with clauses read
   from the ERC at a pinned commit and vectors written from them, before
   either implementation has it, as for every behaviour (specification, then
   vectors, then code).
6. **Wiring the pool into the bundler waits.** Taking frame transactions over
   skandha's RPC and P2P needs signing, RLP and a client to simulate the
   prefix; none of that is needed to play a vector, and it comes when an
   experiment or the ERC-8421 profile needs it.

## Consequences

- `make verify` does not run the fork: it is TypeScript and needs Node or
  Bun. The fork's own test does, and a failure there is reported here, in
  the log, as a finding about a vector or a clause before anything changes.
- The commit of this repository the fork copied from is part of every
  result it reports, as a source's commit is part of every clause here.
- The plan gains the second implementation under "Growing the base", with
  what it covers and what it skips.
- The first version is the fork's `3ca50e9`, with the vectors copied at
  `6932e756`. Its runner played 212 of the 473 cases and matched every one,
  and skipped 261: the four FP-13 cases whose other side is the
  account-nonce pool, and every case of the sets for the nonce pool, LUCID,
  FOCIL and block building, and of the aggregator's and the builder's in
  the aggregation, recent-root and expiring-nonce sets (the fork's
  `packages/framepool/README.md`). Five changes made to the port on
  purpose and not kept, a price bump of 0, FP-14's order, MATCHA's balance
  reuse, the recent-root window and the rounding of MATCHA's charge, each
  made at least one played case fail, so the cases it plays can tell a
  wrong port from a right one.
