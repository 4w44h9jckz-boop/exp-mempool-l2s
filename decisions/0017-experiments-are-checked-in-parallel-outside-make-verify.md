# 0017. Experiments are checked in parallel, outside `make verify`

Date: 2026-10-08. Status: accepted.

## Context

`make verify` ran every check in the repository, the experiments included,
and the working agreement asked for it before every commit. Each experiment
reruns its seeded simulation and compares what it prints with its committed
`results.md`. That check is what keeps a number in prose honest, and charter
point 6 (decision record 0001) asks for it on every pull request.

It is also where the time goes. The experiments ran one after another, and
experiment 08 alone takes about four minutes
(`experiments/08-verify-floor/README.md`). The plan holds ten more
experiments, which would make the check before a commit longer than the work
on most commits. A commit that changes only a document gains nothing from it,
and a check that is too slow to run is a check that gets skipped.

## Decision

1. **`make verify` is the fast checks**: ASCII, links, the vector set, the
   reference's and the simulator's tests, and the conformance vectors. It is
   run before every commit.
2. **`make experiments` is the experiment check**, and `make` runs both. It
   is run before a commit that changes `ref/`, `sim/` or an experiment,
   since those are what can move a committed number. A commit that changes
   only an experiment may check that one,
   `scripts/check-experiments.sh experiments/NN-name`.
3. **Experiments run in parallel.** `scripts/check-experiments.sh` runs as
   many at once as there are processors (`JOBS` overrides it), and prints
   their verdicts in order. Each experiment is a process of its own whose
   randomness comes from its own seeds, so running them together cannot
   move a number.
4. **CI still checks every experiment on every pull request**, each in a job
   of its own, beside one job for `make verify`. Charter point 6 is kept;
   only where the time is spent changes.

## Consequences

- `CLAUDE.md`, `README.md`, `experiments/README.md` and the `Makefile` say
  which target to run when.
- `.github/workflows/verify.yml` lists the experiments that have a `run.py`
  and runs one job for each, so a new experiment is checked without editing
  the workflow.
- A local change to the reference or the simulator still has to wait for the
  slowest experiment. That is the price of checking every number, and it is
  paid once per such commit rather than on every commit.
