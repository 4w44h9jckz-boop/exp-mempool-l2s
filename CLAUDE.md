# Working agreement for this repository

Read `README.md`, then the plan on the branch `plan`. This repository
specifies expected mempool behaviour, implements it as a reference, and runs
experiments on top. The normative artefact is `docs/spec/`; the code in `ref/`
exists to show the clauses are implementable and unambiguous. When code and
clause disagree, the clause is what is wrong until a decision record says
otherwise.

- **Primary sources first.** Clauses are read from go-ethereum and the
  ethereum/EIPs repository at the commits pinned in `docs/spec/README.md`. A
  sibling repository's summary is a pointer to a source, not a source. When a
  source cannot be reached, say so in `refs/refs.md` rather than quoting from
  memory. An EIP in Draft is cited with its status and the commit read.
- **Every clause names its source**, and a clause the repository chose rather
  than read says *Interpretation* and names the decision record. Behaviour of a
  source that is deliberately left out is listed as *Not modelled*.
- **Vectors are clause-first and never regenerated.** A vector in
  `conformance/vectors/` is written by hand from a clause. When it fails, work
  out whether the implementation, the vector or the clause is wrong
  (`conformance/README.md`) before changing anything. A clause change bumps
  its document's version.
- **Specification, then vectors, then code.** A new behaviour lands in that
  order, in one commit or in consecutive ones.
- **Experiments are deterministic and their numbers are checked.** Every
  `experiments/NN-name/run.py` takes its randomness from a seed and prints its
  `results.md`, and `make experiments` fails if the committed file is stale. A
  change meant to move a number regenerates the file in the same commit, and
  the experiment's README is corrected to match. A number quoted in prose comes
  from a results file or a cited source, never from memory.
- **Profiles keep the specification and the measured chain apart.** The
  `eip-8141` profile is the EIP; `hegota-testnet` is what was measured, with
  dates. A measurement never edits the specified profile (decision record 0003).
- **Cite the mechanism's source, do not restate it.** Background belongs to
  the EIPs and the public posts that define a mechanism; write it here only
  where a clause needs it.
- **This repository is public, and every branch of it.** Nothing in it names
  or links a private repository, carries a private project's record
  identifiers, or points to unpublished work (`scripts/check_publishable.py`).
- Every session appends an entry to the log on the branch `plan`, one file a
  day, with Done, Learned, Open questions, Next.
- Every non-obvious choice gets a numbered record in `decisions/`.
- **Standard library only.** `ref/`, `sim/`, `conformance/` and `scripts/`
  import nothing outside Python 3's standard library, so `make verify` runs
  anywhere. CI uses Python 3.13.
- Run `make verify` before committing: ASCII, link and publishability
  checks, the vector-set check, the benchmark tables against their raw
  output (decision record 0033), the reference's and the simulator's unit tests, and the conformance
  vectors. Run `make experiments` too before a commit that changes `ref/`,
  `sim/` or an experiment: it reruns every offline experiment against its
  committed results, in parallel. CI runs both on every pull request, each
  experiment in a job of its own (`.github/workflows/verify.yml`, decision
  record 0017).
- Documents use ASCII only (`scripts/check-ascii.sh`). Mathematics is LaTeX in
  `$...$` or `$$...$$`, never split across lines.
- Cite a file in this repository by its path in backticks, and only if it
  exists on the branch (`scripts/check_links.py`).
- Be frugal with subagents; prefer doing the work directly.
