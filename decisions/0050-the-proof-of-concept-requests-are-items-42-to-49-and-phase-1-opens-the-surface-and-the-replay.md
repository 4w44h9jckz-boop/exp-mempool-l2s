# 0050. The proof-of-concept requests are items 42 to 49, and phase 1 opens the surface and the replay

Date: 2026-10-20. Status: accepted.

## Context

A coordination project of the owner's keeps a register of proofs of
concept for the claims of two of its posts. Its eight mempool entries are to
be specified here and built in the owner's skandha fork, which is the
arrangement decision record 0035 made for the frame pool. The project's
request to this repository carries them as eight requests, each with the
claim it tests, what would show the claim wrong, what this repository would
specify, what skandha would build, and when it is done.

The owner then started three sessions, a coordinator, a mempool session and a
wallet session, in one environment with all five repositories, and asked
the coordination project for a handoff. The mempool session writes here and
to skandha. The handoff reads the owner's start of the sessions as the go
for phase 1, which for this pair is the first two requests, and keeps
phases 2 and 3 closed until the owner approves the checkpoint before each.

## Decision

1. **The requests become items 42 to 49, in the request's order.** One item
   for each request, so item $41 + k$ is the $k$-th request and the $k$-th
   register entry. Each keeps the request's "would show it wrong" as
   written. It was fixed before any work, and a result that contradicts it
   is reported as a result rather than answered by rewording it, as one of
   the handoff's rules requires.
2. **Only items 42 and 43 are open.** Item 42 is the surface a frame pool
   sits behind, item 43 the replay of mined transactions through it. Items
   45 and 46 are phase 2 and items 44, 47, 48 and 49 phase 3; they are
   listed so that the surface can be shaped with them in view, and none is
   started until the owner opens its phase.
3. **The owner's phases reorder "Growing the base".** Decision record 0035
   listed the second implementation's next steps as an ERC-8421 profile, an
   implementation written from the clauses without reading the reference,
   and then frame transactions over the bundler's RPC and P2P. The
   register puts the last first, because the claim it tests, that an open
   network does the checking, needs a pool that takes real transactions.
   The ERC-8421 profile is item 44, in phase 3. The implementation written
   from the clauses alone is in no phase. It is what would test the clauses
   rather than the vectors, and it stays in "Growing the base", not
   started.
4. **What reaches skandha follows the handoff's rule for public
   repositories.** skandha is public, and this repository was private when
   this was decided. skandha's commits, README and comments cite claims by
   the public wording of the coordination project's posts, never copy text
   from its internal files, never name its problem records, and never cite
   its unpublished work.
5. **Both repositories take the session's branch,
   `claude/zealous-ptolemy-g7w9h5`.** In skandha it starts from
   `claude/laughing-turing-jj6c9m` at `3ca50e9`, the commit that holds
   `@skandha/framepool`, so that the surface is built on the pool the
   vectors already judge. The handoff lets the session's branch rule where
   it differs from a repository's branch model, and asks that the conflict
   be recorded; this is the record.

## Consequences

- The plan gains items 42 to 49 and says which are open, and its "Growing
  the base" entry for the second implementation records the reordering.
- The work on item 42 follows this repository's order: clauses first, then
  vectors, then code here, then skandha. Its design choices get decision
  records of their own.
- Each working session ends its log entry with one status line for each
  register entry it touched, in the form the handoff asks for, because the
  coordinator reads nothing else.
