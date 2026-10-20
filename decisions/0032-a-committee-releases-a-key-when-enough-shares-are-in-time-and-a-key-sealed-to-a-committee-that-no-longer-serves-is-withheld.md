# 0032. A committee releases a key when enough shares are in time, and a key sealed to a committee that no longer serves is withheld

Date: 2026-10-13. Status: accepted.

## Context

The plan's item 24 makes experiment 18's key publisher a threshold committee.
EIP-8184 (Draft, read at master `af80fc1c`, identical to `258836f9`) leaves
the key publisher off-protocol: senders encrypt "following the key
publisher's off-protocol instructions (and if applicable, using its public
key)", and a `LucidKeyMessage` is unsigned and valid when its key hashes to
the ticket's `commitment_key` and decrypts the transaction. Its "Additional
bundle and key options" name threshold decryption and stop at a TODO. What
the EIP does fix:

- The key publisher releases after $T_3$, "When the key publisher is
  confident that the beacon block will become canonical (for example after
  observing attestations for it)" (Key release), and the PTC votes on
  "valid keys, scheduled for the current slot" observed "by the key
  observation deadline of the PTC" (Key timeliness), $T_4$. The PTC's key
  vote "can realistically be positioned slightly earlier than the vote on
  the payload" (Rationale, PTC influence and state observation).
- "In the case of a single ST, the sender may itself also release the
  `LucidKeyMessage`, even if it specified a key publisher other than itself"
  (Key release).
- "the key publisher is visible in the ST ticket, and some builder may
  decide to censor based on key publisher identities" (Rationale,
  Censorship resistance without FOCIL).

The EIP gives no seconds. ethereum/consensus-specs at `c489a99`, the commit
this repository already reads for finality, gives them for Gloas
(`configs/mainnet.yaml` and `specs/gloas/validator.md`):
`ATTESTATION_DUE_BPS_GLOAS` is 2500 and `PAYLOAD_ATTESTATION_DUE_BPS` 7500 of
`SLOT_DURATION_MS`, 12000, so attestations are due 3 s into the slot and the
PTC's payload vote 9 s into it.

An earlier survey of dynamic committees reads the committee side: keeping
a key and releasing it each slot is the first of three things a committee at
the mempool level can mean; Ethereum's mempool committees are known an
epoch ahead, so members can be reached directly; and a rotation costs
megabytes. An earlier reading of Commonware's posts finds the two costs a
committee adds: a share from each of $n$ members for each of $B$
ciphertexts, and a ciphertext that misses its epoch is never decrypted.
Those are pointers; what follows is read from the EIP and the
specifications, and the sizes are computed here.

## Decision

1. **No clause changes.** A committee is a key publisher like any other,
   named by its address in the ticket, and a released key is the field
   `revealed` (LU-13). Bundles are not used: a single sealed transaction
   needs no key publisher signature, so a committee needs none.
2. **A key is in time when at least $t$ of the committee's $n$ members'
   shares are, and nothing within the slot is timed.** The window from
   $T_3$, 3 s, to $T_4$, 9 s at the latest, is 6 s. ProbeLab measured
   mainnet beacon blocks, "98% of messages arrive prior to the 4-second
   mark" from the start of the slot (ethresear.ch topic 19982, 2024-07-05),
   and a key message is far smaller than a block; at that mark, the key
   must be combined by 5 s, 2 s after $T_3$, which leaves each member one
   message to the combiner over a direct connection. A member whose share
   misses that is, to the key, the same as one that withholds, so the model
   counts shares and draws no times. Over gossip to members nobody can name
   in advance, the shares and then the key are two broadcasts, up to 8 s at
   the same mark, which does not fit the window; that case is not run.
3. **Members.** $w$ members never send a share, an adversary's or members
   offline for the whole run; each other member misses each slot on its own
   with probability $q$, late or offline for that slot. Every commitment of
   the committee in block $n$ shares the draw of slot $n$: the key of each is
   released when the slot's count reaches $t$. A baseline draws the members
   afresh for each commitment instead, with the same probability per key and
   no correlation between them, to separate how often keys fail from how
   many fail together.
4. **The committees.** $n$ of 16, EIP-7805's `IL_COMMITTEE_SIZE`; 64; and
   423, the smallest committee drawn from validators of which a third are
   corrupt that lacks an honest majority with probability below $2^{-40}$,
   which `run.py` computes and prints and which matches the earlier
   survey. Thresholds are two thirds, $\lceil 2n/3 \rceil$, and a
   majority, $\lfloor n/2 \rfloor + 1$; $w$ is 0 or $\lfloor n/3 \rfloor$,
   the corrupt third. 16 and 64 take both thresholds where they differ; 423
   takes a majority, since at two thirds it has 282 honest members for a
   threshold of 283.
5. **Self-release.** A sender online in the slot of its commitment
   releases its own key after $T_3$ as well, which the EIP allows for a single
   sealed transaction; a second valid key message changes nothing. Each
   commitment's sender is online with probability $o$, drawn per
   commitment, and an online sender's payment runs whatever the committee
   does.
6. **A sender learns of a withheld key at $T_4$** of the slot of its
   commitment, 9 s after the block that committed it, having seen no key,
   and sends the payment again at its next nonce to the node it sent it to: `sealed`, to the committee again, or
   `public`, as experiment 18 does. Unlike experiment 18's senders it has no
   other publisher to turn to, so a sender that keeps sealing to a committee
   that cannot release pays a ticket every block, which the run measures
   rather than prevents.
7. **Rotation every epoch.** The committee changes every 32 slots
   (`SLOTS_PER_EPOCH`). Under `reshare` the public key is kept and any
   commitment's key is released by the committee serving its slot. Under
   `rotate` each epoch's committee has a key of its own; a sender seals to
   the key of the epoch of the next slot, and a commitment sealed to epoch
   $e$'s key is released only by epoch $e$'s committee, which serves its
   epoch and the first $g$ slots of the next. A sender `keep`s a pending
   sealed transaction as it is, or `reseal`s it when its node imports the
   last block before a new epoch, the first moment it seals to the new key,
   replacing it with one sealed to that key at fees raised by LU-9's bump of
   10%. Both committees' members are drawn every
   slot, so runs that differ only in $g$ or in the sender see the same
   members.
8. **Builders that filter** leave out every sealed transaction whose ticket
   names the committee, as the EIP says one may. Without inclusion lists,
   since the specification carries no sealed transaction in one. Half of
   the payments name the committee and half a publisher nobody filters, so
   the two can be compared in one run. The block builder's `skip`, a
   builder's own choice that no clause makes (decision record 0018), now
   applies to the sealed selection as it does to the rest of the block.
9. **Shares are counted, not timed.** Each member in time sends one share
   for each commitment of its committee without batching, or one for the
   slot with batched threshold encryption. Bytes are counted at 32 bytes a
   share, one element of a 256-bit group without its proof, the element
   size the earlier survey assumes; an ASSUMPTION. The network
   has no bandwidth (decision record 0004), so the count moves no delay.

## Consequences

- In the simulator, `KeyCommittee` decides each slot which of the
  committee's commitments have their keys in time, the chain carries a
  withheld one to the next block as not `revealed`, and `SealedLoad` can
  name the committee for a share of its payments, learns at $T_4$, and
  keeps or reseals at a rotation. `build_block`'s `skip` reaches the sealed
  selection.
- Experiment 23.
- Not modelled: the committee's sampling, its key generation and resharing,
  a registry of committees, bundles and their threshold signature, members
  that release early to a builder, and selective withholding.
