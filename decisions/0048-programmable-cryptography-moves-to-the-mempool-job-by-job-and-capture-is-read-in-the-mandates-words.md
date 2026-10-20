# 0048. Programmable cryptography moves to the mempool job by job, and capture is read in the mandate's words

Date: 2026-10-14. Status: accepted.

## Context

The owner asked for the post on programmable cryptography at the mempool
level to stand on its own, and gave it a thesis: programmable cryptography
ran in compute units such as rollups in Ethereum's early years; with native
account abstraction, and to avoid capture, it should move to the mempool
level; and programmable cryptography means ZK, MPC, FHE and more, such as
iO. The post had been a write-up of an experiment that leaned on two
earlier posts for its framing. A thesis post has to say what "capture"
means, which jobs can move, and what the repository's own numbers do and do
not show, and each of those is a choice.

## Decision

1. **The thesis is the owner's, argued from read sources.** The post defines
   programmable cryptography from 0xPARC's essay, which coined the term, and
   dates the first decade's operators from their own texts: the 2018 rollup
   post's "two roles" and EIP-2938's description of the relayer. Nothing is
   taken from another study's summary where the source could be read.
2. **Capture is read in the mandate's own words.** The mandate lists four
   CROPS properties and uses "capture" throughout, with a remedy: keep
   intermediary roles "open, plural, bounded, and verifiable", and keep a
   "zero option". The post uses those words as its test and does not present
   capture resistance as a fifth listed property.
3. **Jobs move one at a time, by a placement test.** A job can run at the
   mempool level only if nodes disagreeing about it costs liveness, never
   safety. So checking and aggregating ZK proofs move; holding an MPC or FHE
   key moves only with a committee large enough to keep an honest majority;
   iO, which would remove the committee, is dated by its advocate as "still
   infeasible today". The post argues for moving jobs, not primitives.
4. **Earlier studies' numbers are quoted as theirs, and recomputed where
   the data is here.** An earlier study's chain reads of the deployed FHE
   stack are quoted with their block. L2BEAT's shares are recomputed from
   an earlier snapshot of L2BEAT, and an earlier MPC study's committee
   tails from the binomial, so both are *derived* here.
5. **The shuffle round stays as the worked example**, shortened, because it
   is the one role whose cryptography is finished and so isolates what the
   mempool's gap in time does.

## Consequences

- The post makes a claim the experiments do not test: that moving a job to
  the mempool reduces capture. What the experiments show is narrower, and
  the post says so: four things that do not move with the job (hardware for
  aggregation, committees for keys, the network's first hop, the gap
  between agreement and execution), each with a figure.
- FHE evaluation, iO and witness encryption are not modelled anywhere here.
  The post says so, and its FHE and iO rows rest on the earlier FHE study
  and on Buterin's posts.
- The Hegota headliner decision is stated from an earlier reading of the
  call, whose transcript is outside this session's reach (`refs/refs.md`).
