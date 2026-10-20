# 0060. A ruleset is a descriptor file, with a content identifier, modules and a parent

Date: 2026-10-20. Status: accepted.

## Context

Every ruleset this repository models is a profile in code: FP-1's columns,
AG-1's, CG-1's. ERC-8421 says alternative mempools are "identified by its
own topic, conventionally the IPFS hash of a document that describes its
rules" (ERCs pull request 2028 at `493ba8ac`), and leaves the document's
form open. If the document were machine-readable, a node could load a
mempool's rules instead of being built with them, and two implementations
could be checked against the same file. The open questions were the
encoding, the identifier, what a rule is, how one ruleset builds on
another, and what a refusal says.

## Decision

1. **JSON, with RFC 8785's canonical form on a restricted value set.** No
   floats, integers below $2^{53}$ and larger amounts as decimal strings,
   ASCII strings, unique member names. On that set RFC 8785 is: sorted
   members, no whitespace, and only `"` and `\` escaped. Any JSON parser
   can read the file, and the canonical bytes need no library.
2. **The identifier is a CIDv1 of the canonical bytes as a raw block,
   sha2-256, base32.** It is the IPFS hash ERC-8421 names, and the raw codec
   makes it a function of the bytes alone, with no IPFS chunking or
   UnixFS wrapping to agree on.
3. **A module is a rule, named as its source names it.** A module is
   `FP-6` for this repository's clauses and `PREFIX-010` for ERC-8421's. Each
   module has a fixed parameter list, every parameter explicit in the file,
   so that the identifier fixes every value. A node refuses a module it
   does not implement, rather than ignoring it.
4. **Inheritance by identifier, with removal and replacement whole.** A
   child names its parent's identifier, removes modules by name, and adds
   or replaces modules with all their parameters. Identifiers commit to
   parents, so chains cannot loop.
5. **Completeness is checked.** Core modules are always present; each
   replaceable frame-pool module is present or replaced, never both. A
   ruleset is refused that holds ERC-8421's modules with any `AG` or `CG`
   module: each set is complete on its own, but no clause says how the
   ERC's per-entity budgets, trace rules and reputation apply to dependency
   frames, wrappers or claims, so a descriptor that names both would load
   to a pool that silently runs one.
6. **A refusal names the module and the loaded descriptor.** The module is
   found from the code by each document's Errors table, which already gives
   every code one clause; ERC-8421's rules claim their codes over the frame
   pool's within that ruleset.
7. **Three descriptors to begin.** EIP-8141's canonical mempool, claim-gated
   admission as its child, and ERC-8421's standard ruleset as its child with
   six modules replaced.

## Consequences

- The profiles in code stay; a descriptor of the frame pool's modules
  compiles to one of them, so every existing vector still judges the pool.
- A descriptor's identifier changes with any value in it, its `source`
  string included, so a new version of a document means a new descriptor.
- *Not modelled*: how nodes publish and find descriptors, and the topic
  they gossip on.
