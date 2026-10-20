# 0018. Inclusion lists are read from EIP-7805 with EIP-8369's profiles, and builders that filter are the simulator's

Date: 2026-10-09. Status: accepted.

## Context

The plan's item 17 asks how long a transaction waits when a share of
builders leaves it out, without inclusion lists and with them, at full
blocks, and what a filtering builder gives up. An earlier study argues that
at full blocks it gives up nothing.
Answering it needs three things the repository did not have. It needs a
clause for what an inclusion list obliges a builder to do. It needs a clause
for what an includer lists. And it needs a model of a builder that wants a
transaction out.

EIP-7805, Standards Track and in Draft, was read at ethereum/EIPs `258836f9`
and was unchanged on master on 2026-10-08. It states the obligation. Its
check for "the nonce and balance of `T.origin`" does not decide whether a
frame transaction is valid. EIP-8369, Informational and in Draft, read at
the same commit, says which transactions can be enforced, in two profiles.
Both texts leave choices open, and the simulator needs choices of its own.

## Decision

1. **A specification document of its own, with three profiles.**
   `docs/spec/07-focil.md` has the profiles `off`, `eip-7805` (Profile 1
   only) and `eip-8369` (Profile 1 and Profile 2). EIP-8369 is Informational
   and says a Standards Track extension "must restate every binding rule". So
   `eip-8369` specifies a proposal, as `matcha` does (decision record 0007).
   The pools do not change: an inclusion list is built from a pool, and
   EIP-8369 says "public mempool admission and FOCIL eligibility remain
   separate".
2. **Readings where the texts leave a choice** (the *Interpretation* clauses
   of `07-focil.md`):
   - `MAX_VERIFY_GAS_PER_TX` is set equal to `MAX_VERIFY_GAS_PER_IL`, the
     largest value EIP-8369's "up to" allows.
   - IL-2: an includer lists what its own pool would put in a block on its
     head at a minimum tip of zero. EIP-7805 leaves the order "to the
     discretion of implementers" and names three, "at random, by priority
     fee, or based on how long they have been pending". The profile orders by
     fee, and `age` is a variant. The fee order is what a block builder's
     pool already gives; age is the order that favours a transaction that
     builders have left out. Random is neither, and is not modelled. An
     includer lists only what it could enforce, and skips a frame
     transaction its list's budget cannot hold. A listed transaction that
     cannot be enforced would cost the list bytes and buy nothing.
   - IL-5: the fee check is EIP-8369's `fee_valid`, which "could be validly
     included" implies. The check is made at the end of the payload rather
     than at a builder-claimed index. The two agree for a transaction whose
     dependencies are "position-stable", and every frame transaction the
     experiments send is one. The prefix reads only what FP-9 lets it read.
   - IL-8: every attester stores the same lists, the ones the slot's
     includers built, and every attester is honest. A block that does not
     satisfy them is not canonical, and the slot has no block.
3. **The committee and the clock are the simulator's.**
   - Each slot, `committee_size` nodes are drawn without replacement from a
     random stream of their own, `{seed}/committee`. Turning inclusion lists
     on therefore does not move the chain's own draws.
   - Every includer builds its list 8 s into the slot, the end of EIP-7805's
     window "`t=0 to 8s`".
   - Every list reaches the next slot's builder and every attester. Gossip,
     its deadlines and a late list are not modelled.
4. **Builders that filter.** A fixed set of builders builds every block in
   turn. That stands in for a builder market in which each wins a share of
   the slots. The set that filters is drawn at random from them, so the
   slots that do not filter are spread through the rotation. A filtering
   builder leaves out every transaction of the senders it filters
   (`build_block`'s `skip`, a choice no clause makes). When its block would
   leave a listed transaction out (IL-6), it follows one of four
   strategies:
   - `stuff`: it appends a transfer of its own (`own`) at a fee cap of the
     base fee and no tip. The transfer's gas is just enough to leave less
     unused gas than the smallest listed transaction it left out, so that
     IL-6 excuses every one.
   - `miss`: it proposes the block anyway, and attesters reject it.
   - `yield`: the slot goes to the next builder in turn that does not
     filter, which builds it honestly. This is the reading under
     proposer-builder separation, where a proposer takes the best bid that
     satisfies the lists. It is `miss` if every builder filters.
   - `cheapest`: it stuffs if the stuffed block's priority fees cover the
     base fee it burns, and yields otherwise. Losing the slot pays it
     nothing.

   Builders are funded so that a builder's balance never limits stuffing.
   Includers that filter leave the same senders out of what they list.
5. **What filtering costs is measured against an honest counterfactual.**
   For each slot a filtering builder was due, the simulator builds the block
   it would have built honestly from the same pool and lists. The cost is
   that block's priority fees, less the fees the builder was paid, plus the
   base fee it burned. A slot it yielded or missed pays it nothing. MEV,
   bids and payments to the proposer are not modelled, so the cost is in
   priority fees and burned base fee only.
6. **The chain runs at its gas target.** On a chain at rest the base fee
   falls toward zero, and stuffing a block then costs nothing. Every run of
   experiment 09 therefore carries background demand of 1,000,000-gas
   transfers at the gas target on average, so the base fee starts and stays
   near where blocks are half full. The wallets price as every experiment's
   do, at twice the next base fee plus the tip, and never bump a fee.
   Section 3 adds a burst of extra demand. EIP-1559 lets blocks stay full
   only while the base fee is still rising, so a full block exists only
   during such a burst.
7. **Runs in parallel.** `emem_sim.parallel.run_all` runs independent
   simulations in as many processes as there are processors (`EMEM_JOBS`
   overrides it), and returns their results in the order asked for. A
   run's randomness comes from its own scenario and seed, and nothing in
   `ref/python/emem/` or `sim/emem_sim/` keeps state between runs. So a
   result does not depend on which process ran it, and decision record
   0017's check still holds.

## Consequences

- `docs/spec/README.md` lists `07-focil.md` and the profiles `eip-7805` and
  `eip-8369`. `scripts/check_vectors.py` requires a vector for every IL
  clause but IL-1.
- `build_block` takes the slot's lists, a FOCIL profile and a builder's own
  `skip` and `own`. `ChainConfig` takes `focil`, `il_at`, `censored`,
  `filtering`, `filtering_includers` and `strategy`. The recorder keeps
  missed slots, and when each transaction was first listed.
- Not modelled, beyond `07-focil.md`'s list: MEV and bids; a builder that
  answers another's filtering; wallets that resend at a higher fee; and an
  adversary that times its transactions around the list deadline.
