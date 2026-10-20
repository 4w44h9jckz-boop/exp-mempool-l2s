# 0001. Charter: a specification, a reference implementation, and a simulation base

Date: 2026-10-07. Status: accepted by the owner's request; open to revision.

## Context

The owner asked for a repository "for experimenting with ethereum mempool",
with "different experiments" to come and "a base first", built on the domain
knowledge and expected behaviour of the sibling repositories, and then for "a
ref impl base" as well. The work that bears on it is:

- an earlier account abstraction study, whose explainers teach the public
  mempool, ERC-4337's alternative mempool, EIP-8141's public mempool policy,
  FOCIL and LUCID, and which measured where the one deployed frame
  transaction client differs from the EIP;
- `exp-frames`, which builds frame transaction tooling against the ethrex
  Hegota testnet and records what that testnet's mempool enforced on
  2026-10-07;
- an earlier specification project, whose working agreement sets the pattern
  for a specification with a reference implementation and clause-first
  conformance vectors.

## Decision

1. **Three layers.** `docs/spec/` states expected mempool behaviour as numbered,
   sourced clauses; `ref/python/` implements them; `conformance/` binds the two
   with hand-written vectors. Experiments are built on top: `sim/` runs the
   reference pools on a simulated network, and `experiments/` holds one
   question per folder. An experiment's findings about the clauses go back
   into the specification, never silently into the code.
2. **The specification is normative and the code is not.** When they disagree
   the clause is wrong until a decision record says otherwise. Vectors are
   written from clauses before the code they judge, and are never regenerated
   from the code (`conformance/README.md`).
3. **Primary sources, pinned.** Clauses are read from go-ethereum and the
   ethereum/EIPs repository at named commits (`docs/spec/README.md`). A
   sibling's summary is a pointer to a source, not a source.
4. **Standard library only, Python 3.** Everything `make verify` runs needs
   nothing installed, so a fresh session or CI reproduces it.
5. **Teach by routing.** The mechanisms are specified in their EIPs and in
   go-ethereum. This repository cites those rather than restating them, and
   writes background only where a clause or an experiment needs it.
6. **Deterministic experiments.** Every simulated number comes from a seeded
   run whose output is committed and re-checked on every pull request.

## Consequences

The base covers the two pools that matter now: the account-nonce pool, as
go-ethereum implements it, and the EIP-8141 frame transaction pool, as the
EIP specifies it. Blob transactions, private order flow, FOCIL and encrypted
mempools are not modelled yet; the plan lists them as the order in which
experiments are expected to need them.
