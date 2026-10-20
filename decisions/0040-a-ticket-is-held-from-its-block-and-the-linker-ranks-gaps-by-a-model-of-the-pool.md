# 0040. A ticket is held from its block, and the linker ranks gaps by a model of the pool

Date: 2026-10-13. Status: accepted.

## Context

The plan's item 30 asks how often a ticket's purchase can be linked to its
spend. It asks for ticket purchases sent as public transactions at Poisson
rate $\lambda$, spends after holding times drawn from three policies, at
$\lambda H$ of 0.5, 5 and 50, the best linker, which ranks candidates by the
likelihood of their gap and breaks ties at random, and the linking rate
against a closed form at the intended holding distribution and at the one
observed. A second linker adds experiment 12's spy, and assumes that a
wallet sends its purchase and its spend through the same node.

A ticket is issued on chain, and exists once its issuance is on chain.

## Decision

1. **A wallet holds its ticket from the block that carried its purchase.**
   It watches the node it sent the purchase to, and draws $Y$ from when that
   node imports the block. So no spend can come before its purchase, and the
   item's case of noise that moves a purchase after its spend does not
   arise for a ticket issued on chain. The issuance's own wait is not
   modelled: one in the next block moves every purchase of a key by the same
   slot, which changes no gap; one that waits varying times adds noise of
   the same kind as the spend's own wait, which is measured.
2. **A purchase is a plain transaction, and a spend is the shared
   sender's.** A purchase is a type 2 transaction from the wallet's own
   account, sent once to a random node; a spend is experiment 12's, from one
   shared sender on a nonce key of its own under `hegota-testnet`'s
   `disjoint-keys`, sent to the purchase's node or to a random one. Neither
   is new to any pool, so there is no clause and no vector: the simulator's
   `Tickets` (`sim/emem_sim/workload.py`) is a load, and the linkers are
   observers that read the recorder and the spy.
3. **Keys run side by side.** The linker sees the key, so each key is an
   instance of its own. A run carries enough keys that a
   window of 20 mean holding times holds 1,500 trials for each way of
   entering, which costs transactions and not slots.
4. **The linker ranks gaps by a model of the distribution of observed gaps,
   and the closed form weights them by the gaps observed.** Counted from
   1,500 trials, the distribution of a gap in slots that spans 600 slots,
   as an hour's uniform holding does, ranks slots by sampling noise, and a
   linker ranking by the trials it is judged on favours their own slots.
   The model is the slot after the import delay plus $Y$, $\lceil (a + Y) /
   12 \rceil$, with $a$ the delays the run's wallets saw, shifted by the
   blocks the run's spends waited beyond that slot. It keeps the ties of a
   uniform policy exact. The closed form at the observed distribution is
   then the mean over trials of what a target at its observed gap wins, in
   the model's order. A trial scores one over the purchases tied with the
   target when it is among the likeliest, which is the chance that a
   random tie-break names it.
5. **The standard error counts the trials of one key that share
   candidates.** Keys side by side make the trials of one key dependent: a
   purchase is a candidate for every spend of its key within a few mean
   holding times, under uniform holding for $2 \lambda H$ of them on
   average, a hundred at $\lambda H$ of 50. A standard error that treats
   trials as independent understates the noise there. More keys and shorter windows would make
   the clusters independent, but in a trial run at $\lambda H$ of 50 and a
   minute's holding, 20 keys for each way of entering filled the blocks,
   most spends waited blocks beyond their first, and what was measured was
   no longer the item's setting. So the run keeps its keys, and the
   standard error counts
   the covariance of two trials of one key bought less than $8H$ apart,
   weighted by one less their lag over $8H$. These are Bartlett's weights,
   which keep the variance from going negative for any spacing of
   purchases. Under uniform holding a trial's candidates lie within $2H$
   of its purchase, so two trials bought more than $4H$ apart share none;
   $8H$ is twice that, and covers the longer reach of memoryless holding
   but for its tail. The table keeps the standard error of
   independent trials beside it. The first run of the experiment used
   only that one; the change was made after reading it, for this reason.
6. **The spy linker's odds come from the run.** It multiplies a candidate's
   probability by the ratio of how often the spy's guesses for a purchase
   and the spend agree when one wallet sent both through one node, taken
   from the run's trials of that kind, to how often they agree for two
   strangers, taken from every purchase and spend; or by the same ratio for
   disagreeing. It uses those odds whether or not the wallet did enter at
   one node, which is what assuming it means.

## Consequences

- The simulation reports, for each policy and $\lambda H$, at a mean holding
  time of a minute and of an hour, the rate, its standard error, and the
  closed form at the intended and at the observed distribution; then each
  linker with a wallet entering at one node and at a random one.
- The model is the linker's knowledge of the network: its import delays and
  how often a spend misses a block, which every observer of the chain can
  learn. A linker that knew less would do no better.
- Not modelled: the issuance as a transaction, amounts and gas
  prices, a purchase stream that is not Poisson, and a wallet that changes
  node between transactions in any other way.
