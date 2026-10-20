# 0070. The key round is specified from the EIP's text, with real keys and decryption as a field

Date: 2026-10-20. Status: accepted.

## Context

`docs/spec/06-lucid.md` version 2 specifies EIP-8184's sealed pool and the
two blocks a sealed transaction touches, and lists as *Not modelled* "the
payload bid, key messages, key-timeliness votes and the PTC; whether a key
is released is the field `revealed`". That is the part of LUCID that makes
a fact public: a builder commits to a sealed transaction in its bid, a key
publisher releases the key only after that commitment is fixed, and the
payload timeliness committee (PTC) votes, key by key, on whether it saw the
key in time. Post 22 reads LUCID as publishing the fact and not the
content. The claim this record serves is that the commitment, the deadline
and the vote can be checked without reading the content, and that a
withheld key shows up as a missing vote.

EIP-8184 was read at `258836f9`, sections "Extended payload bid with
ST-commitments", "Key message", "Key message validity and decryption",
"Key release", "Key timeliness" and "Rationale" ("Key publisher liability
for non-reveal"); it is byte-identical at master `ed9b7126` (2026-10-20).
The EIP leaves several points open: the deadlines have names and no values,
the order of the validity checks is a numbered list with decryption fourth
of five and the key check first, and a builder may face a key that the
tally allows it to treat either way.

## Decision

1. **Six clauses, LU-14 to LU-19, for standalone sealed transactions.**
   The commitment (LU-14), a key message's validity (LU-15), when a key
   publisher may release (LU-16), a PTC member's vote (LU-17), the next
   slot's tally (LU-18) and what the public record says of a key the tally
   finds missing (LU-19). Bundles, their `executable` bitfield and a
   multi-key `commitment_key` are left out, as they are in version 2.
2. **The key is real; decryption is a field.** A sealed transaction gains
   `k_dem`, 32 bytes, and `key_commitment`, by default
   `keccak256(k_dem)`, so LU-15's key check is the EIP's, on real bytes,
   with the Keccak-256 the reference already has (`ref/python/emem/keccak.py`).
   Whether the ciphertext decrypts under that key to a plaintext that
   matches `reveal_commitment` is a field, `decrypts`, because
   ChaCha20-Poly1305 and SSZ's `hash_tree_root` would add two primitives to
   a standard-library reference for a check whose result is all a pool or
   a voter acts on. A model cannot then show that decryption reads the
   content; it can show when it is asked, and the reference records which
   commitments it asked about.
3. **Public checks first, decryption last** (LU-15). The EIP numbers the
   key check first and decryption fifth, and its key check needs the
   commitment the message names, so a reader cannot run the list in the
   order written. The reading orders the checks so that every one that
   reads only the message and the block comes before the one that reads
   the ciphertext, and names a reason for each, which the EIP does not.
   The set of valid messages is the same in any order.
4. **Release is conditional, and withholding is not a clause** (LU-16).
   "When the key publisher is confident that the beacon block will become
   canonical (for example after observing attestations for it)" is read as
   an input, `attested`. "Verifies that the order of the ST-commitment is
   consistent with its underlying `max_preceding_commitments`" is read as
   commitment index $j$ at most `max_preceding`, the count of commitments
   before it. A publisher MAY release when the conditions hold and MUST NOT
   before; a publisher that withholds is a behaviour of the simulator and of
   a vector's steps, not a rule. The sender of a standalone sealed
   transaction may release its own key, as the EIP says.
5. **The vote's bitfield has one bit per commitment, and the deadlines are
   inputs** (LU-17, LU-18). The EIP types `keys_observed` as
   `Bitlist[MAX_ST_COMMITS]`, a bound, and reads bit $j$ as commitment
   index $j$; the length is the block's count of commitments. The key
   observation deadline, `lucid_key_vote_deadline` and the attestation time
   have no values in the EIP, so each is given by the caller, in
   milliseconds, and no profile fixes them.
6. **Equivocation is what is seen by the attestation time** (LU-18). "Keep
   listening for new messages and equivocation until they vote" is read as:
   a member with two distinct votes received by the attestation time is
   equivocated, and none of its votes is counted in the bitfields; a vote
   received after the attestation time counts for nothing; a vote from a
   validator outside the committee is ignored.
7. **Where the tally allows both, the reference's builder treats the key as
   observed** (LU-19). The EIP's two conditions overlap; one of them always
   holds, since both failing would need
   $t_1 > t_0 + l_0 + e$ and $t_1 + l_1 + e \le t_0$ at once. A builder may
   take either where both hold. The reference takes `observed`, which runs
   a transaction whose key the committee saw rather than charging its
   sender for nothing. LU-13's `revealed` is that choice together with
   `decrypts`.
8. **A missing key is attributed from the public record, not penalised**
   (LU-19). The EIP has no liability for a key publisher: "There is no
   protocol-level mechanism for having key publishers of multi-key bundles
   assume liability". What a reader can say of a commitment the tally
   treats as missing is one of four things: a key message that passes the
   public checks arrived in time and the ciphertext did not decrypt
   (`undecryptable`, the sender's ciphertext); one arrived only after the
   deadline (`late`); none arrived (`withheld`, the publisher named in the
   ticket, or its sender); or a valid one arrived in time and the
   committee voted against it all the same (`unvoted`, which a reader
   whose record differs from the committee's can find). The zero bits
   alone do not tell `withheld` from `undecryptable`; the released key
   message does.

## Consequences

- `06-lucid.md` goes to version 3. LU-2 gains `k_dem`, `key_commitment`
  and `decrypts`, absent from the hash when left at their defaults, so
  every existing vector and experiment keeps its hashes and numbers.
  Every vector of the document is re-read against version 3 and changes
  only its version.
- The vectors gain an operation, `key_round` (`conformance/README.md`),
  and the reference a module, `ref/python/emem/lucidkeys.py`.
- What M7's claim would be shown wrong by, read against these clauses:
  the commitment (LU-14), the deadline and the key check (LU-15 steps 1 to
  5, LU-17's time) and the tally (LU-18) read the ticket, the block, the
  key message, arrival times and votes, and nothing of the ciphertext. The
  vote bit itself is defined over a *valid* key message, and validity
  includes decryption (LU-15 step 6), so a voter does decrypt, but only a
  ciphertext whose key has already been released, when anyone holding the
  key message can. The content is read after the fact is fixed, not
  before.
- Decision record 0027's reading of a withheld key, that its sender pays
  the ticket and nothing runs, is unchanged; LU-18 is how the next block
  knows the key was withheld.
- If the EIP gives the deadlines values, specifies bundles' key messages or
  adds liability, the clause that read it changes and `06-lucid.md` bumps
  its version.
