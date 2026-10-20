# 13. Descriptors: a ruleset as a file a node loads

Version 1, 2026-10-20.

**Status: proposal.** EIP-8141 fixes one public mempool's rules, and
ERC-8421 lets nodes agree on others: "Each alternative mempool is identified
by its own topic, conventionally the IPFS hash of a document that describes
its rules" (ERC-8421, Alternative Mempools, ERCs pull request 2028 at
`493ba8a`). This document makes that document machine-readable. A
**descriptor** is a file that names the rules a pool applies, each a module
with its parameters. It has one canonical encoding and an identifier derived
from it, it may inherit from a parent descriptor, and a node that refuses a
transaction under it names the descriptor and the rule. The profiles of
`02-frame-pool.md`, `05-aggregation.md` and `10-claim-gated-admission.md`
become descriptors, and `14-erc-8421.md` writes ERC-8421's standard ruleset
as one. Decision record 0060 has the readings.

## Errors

| Code | Raised by |
| --- | --- |
| `ErrDescriptorMalformed` | DS-1, DS-2 |
| `ErrDescriptorParentUnknown` | DS-5 |
| `ErrDescriptorUnknownRule`, `ErrDescriptorParams` | DS-4 |
| `ErrDescriptorRemove` | DS-5 |
| `ErrDescriptorIncomplete`, `ErrDescriptorConflict` | DS-6 |

These are a node's answers when it loads a descriptor, not refusals of a
transaction.

## The file

**DS-1. A descriptor.** A descriptor is a JSON object (RFC 8259) with
exactly these members:

| Member | Holds |
| --- | --- |
| `format` | the integer 1 |
| `name` | a string, for people |
| `source` | a string: what the rules were read from, with its version or commit |
| `parent` | the identifier (DS-3) of the descriptor it inherits from, or `null` |
| `rules` | an object mapping each module's name (DS-4) to an object of its parameters |
| `remove` | an array of module names to drop from the parent's (DS-5), possibly empty |

A value is an object, an array, a string, `true`, `false`, `null`, or an
integer from 0 to $2^{53} - 1$; an amount that may be larger is a string of
decimal digits. A string holds ASCII characters from `0x20` to `0x7e` only.
An object's member names are unique. A node MUST refuse anything else with
`ErrDescriptorMalformed`, before reading the rules.

**DS-2. The canonical encoding.** A descriptor's canonical encoding is its
JSON text with no whitespace outside strings, every object's members sorted
by name in byte order, integers in decimal without a sign, leading zeros or
exponent, and in strings only `"` and `\` escaped, as `\"` and `\\`. It is
the encoding RFC 8785 gives such a value: its members sorted by UTF-16 code
units, which for ASCII names is byte order (section 3.2.3), and its numbers
serialized as ECMAScript does, which for an integer below $2^{53}$ is its
decimal digits (section 3.2.2.3). **Source:** RFC 8785, read 2026-10-20. A file a node loads may be written
in any way that parses to the same value; its identifier is that of the
value.

**DS-3. The identifier.** A descriptor's identifier is the CIDv1 of its
canonical encoding as a raw block (codec `0x55`) hashed with SHA-256
(multihash `0x12`, length `0x20`), in base32 lower case without padding,
with the multibase prefix `b`:

$$
\mathit{id} = \texttt{"b"} \Vert \mathit{base32}(\texttt{0x01} \Vert \texttt{0x55} \Vert \texttt{0x12} \Vert \texttt{0x20} \Vert \mathit{sha256}(\mathit{canonical}))
$$

So it begins `bafkrei`, and it is the IPFS hash of the canonical file added
as a single raw block. **Source:** ERC-8421, Alternative Mempools ("the
IPFS hash of a document"); multiformats `cid` at `9eca1c5b` ("CIDv1":
`<multibase-prefix><multicodec-cidv1><multicodec-content-type><multihash-content-address>`),
`multicodec` at `8d9e9b3b` (`cidv1` `0x01`, `raw` `0x55`, `sha2-256`
`0x12`) and `multibase` at `d7406cde` (`b`, "base32", "RFC4648
case-insensitive - no padding"), read 2026-10-20. Choosing the raw codec,
so that the identifier is a function of the bytes alone, is this
document's (*Interpretation*, decision record 0060).

## Modules

**DS-4. Modules.** A module is one rule, named as its source names it: a
family and a number, as ERC-8421 names `PREFIX-010` and this repository
names `FP-6`. A node implements a set of modules, each with a fixed list of
parameters and the codes it may refuse with; the table below and
`14-erc-8421.md` give them. In a descriptor, a module's parameters object
MUST hold exactly the module's parameters, each of its type; there are no
defaults, so that the identifier fixes every value. A node MUST refuse a
descriptor that names a module it does not implement with
`ErrDescriptorUnknownRule`, and one whose parameters differ from the
module's with `ErrDescriptorParams`, naming the module; it checks the
modules of `rules` in the byte order of their names, each name before its
parameters.

The modules of this repository's frame pool, with the parameters of FP-1,
AG-1 and CG-1 each takes. A parameter's value under each of the profiles is
the one those clauses give.

| Module | Parameters | Kind |
| --- | --- | --- |
| `FP-2` | none | core |
| `FP-3` | `price_limit` (integer) | core |
| `FP-4` | none | core |
| `FP-5` | `expiry_verifier` (string) | rule |
| `FP-6` | `max_verify_gas` (integer), `max_verify_state_gas` (integer, or `null` for not enforced) | rule |
| `FP-7` | none | rule |
| `FP-8` | `expiry_margin` (integer), `expiry_verifier_code` (string) | core |
| `FP-9` | `canonical_paymaster_code` (string), `precompiles` (array of strings) | rule |
| `FP-10` | none | core |
| `FP-11` | `max_pending_noncanonical` (integer), `cap_codeless_payers` (boolean) | rule |
| `FP-12` | `per_sender` (`one` or `disjoint-keys`), `price_bump` (integer) | rule |
| `FP-13` | none | core |
| `FP-14` | `max_pending` (integer), `evict_first` (`expiry` or `tip`) | core |
| `FP-15` | `reuse_balance` (boolean) | core |
| `FP-16` | none | core |
| `AG-2` | `max_dependencies_per_frame` (integer) | rule |
| `AG-3` | none | rule |
| `AG-4` | `max_sigs_per_tx` (integer), `max_starks_per_tx` (integer) | rule |
| `AG-5` | `max_sig_deps_per_wrapper` (integer), `max_stark_deps_per_wrapper` (integer) | rule |
| `AG-6` | none | rule |
| `AG-7` | `aggregation_interval_ms` (integer), `cap_aggregates` (boolean), `forward_wrappers` (boolean) | rule |
| `AG-8` | none | rule |
| `CG-2` | `claim_epoch` (integer) | rule |
| `CG-3` | `signed_proofs` (boolean) | rule |
| `CG-4` | `claim_memory` (`slot`, `claim` or `none`) | rule |
| `CG-5` | none | rule |
| `CG-6` | none | rule |
| `CG-7` | `verifies` (boolean) | rule |
| `CG-8` | `namespace` (string) | rule |
| `CG-9` | none | rule |
| `CG-10` | `template_length` (integer), `template_keccak` (string) | rule |

A **core** module is part of every frame pool this repository models; a
**rule** module may be absent, or replaced (DS-6). A module refuses with the
codes its document's Errors table gives it.

## Inheritance and loading

**DS-5. Inheritance.** A descriptor whose `parent` is not `null` inherits:
its **effective modules** are its parent's effective modules, without those
its `remove` names, with each module in its `rules` added, or replacing the
parent's module of that name whole. A node finds a parent by its identifier
among the descriptors it holds, checking that the parent's identifier is the
one named, and MUST refuse with `ErrDescriptorParentUnknown` a parent it
does not hold. A name in `remove` that the parent's effective modules do
not have MUST be refused with `ErrDescriptorRemove`. Each effective module
remembers the descriptor whose `rules` set it. A chain of parents cannot
loop, since an identifier commits to its parent's.

A node loads a descriptor in this order, the first failure being its
answer: DS-1 on the file; the parent, which it has loaded already, by
DS-5; the descriptor's own `rules` by DS-4; its `remove` by DS-5, in the
order the array gives; then the effective modules by DS-6.

**DS-6. A complete ruleset.** A node checks a descriptor's effective
modules in this order, and the first failure is its answer:

1. every core module, in the table's order, is present, else
   `ErrDescriptorIncomplete` naming the first missing;
2. if any module of `14-erc-8421.md` is present, every one AM-2 lists is,
   else `ErrDescriptorIncomplete` naming the first missing in AM-2's order;
3. each of `FP-5`, `FP-6`, `FP-7`, `FP-9`, `FP-11` and `FP-12`, in that
   order, is present without the ERC's modules, or absent with them, else
   `ErrDescriptorConflict` naming it if both are there and
   `ErrDescriptorIncomplete` naming it if neither is;
4. no `AG` or `CG` module is present with the ERC's modules, else
   `ErrDescriptorConflict` naming the first present in the table's order:
   no clause says how ERC-8421's ruleset composes with dependency frames or
   claims (decision record 0060);
5. if any `AG` module is present, every `AG` module of the table is, and if
   any `CG` module is present, every `AG` and `CG` module is, else
   `ErrDescriptorIncomplete` naming the first missing in the table's order. A
pool under a complete ruleset behaves as the profile whose parameters its
modules carry: every module listed above present, with FP-1's `eip-8141`
column, is the `eip-8141` profile; with the `AG` modules, `eip-8288`; with
the `CG` modules too, `claim-gated`. A parameter of FP-1, AG-1 or CG-1 no
module carries takes that profile's value.

**DS-7. Rejections.** A pool that refuses a transaction under a descriptor
MUST name, with the code, the **rule**, the effective module that refused
it, which its document's Errors table gives, and the **descriptor**, the
identifier of the descriptor the node loaded. A refusal by a clause outside
the modules, such as FP-2's answer to a transaction already held, names the
module it is in all the same: every code the frame pool returns belongs to
one module above or in `14-erc-8421.md`.

## The descriptors

**DS-8. Three descriptors.** `docs/spec/descriptors/` holds:

| File | Ruleset | Parent |
| --- | --- | --- |
| `eip-8141.json` | EIP-8141's canonical mempool: the modules above from `FP-2` to `FP-16`, with FP-1's `eip-8141` column | none |
| `claim-gated.json` | claim-gated admission: `eip-8141.json`'s modules with the `AG` and `CG` modules above, with AG-1's and CG-1's values | `eip-8141.json` |
| `erc-8421.json` | ERC-8421's standard alternative mempool, ERCs pull request 2028 at `493ba8a` (`14-erc-8421.md`) | `eip-8141.json` |

Each file's identifier is in `docs/spec/descriptors/README.md`. A change to
a file changes its identifier, and a child's `parent` with it.

*Not modelled:* how nodes find each other's descriptors, and the topic a
descriptor names on the wire. ERC-8421 leaves the transport out of scope,
and so does this document.
