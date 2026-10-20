# Reproduce and check the repository. `make` runs everything CI runs.
#
#   verify       the fast checks: checks, ref, vectors and sim
#   checks       documents are ASCII, cited files exist, nothing points to a
#                private source, the vector set matches the specification,
#                every benchmark table is what its raw output derives
#                (decision record 0033)
#   ref          the reference implementation's unit and invariant tests
#   vectors      the reference against the hand-written conformance vectors;
#                there is no target that regenerates vectors, on purpose
#   sim          the simulation base's tests
#   experiments  every offline experiment against its committed results.md,
#                in parallel; CI runs each in a job of its own (decision
#                record 0017)
#
# Python 3 standard library only. The checks read `git ls-files`, so run them
# after `git add`.

PYTHON ?= python3

.PHONY: all verify checks ascii links publishable vectorset bench ref vectors sim experiments help

all: verify experiments

verify: checks ref vectors sim

checks: ascii links publishable vectorset bench

ascii:
	@./scripts/check-ascii.sh

links:
	@$(PYTHON) scripts/check_links.py

publishable:
	@$(PYTHON) scripts/check_publishable.py

vectorset:
	@$(PYTHON) scripts/check_vectors.py

bench:
	@$(PYTHON) scripts/check_bench.py

ref:
	@PYTHONPATH=ref/python $(PYTHON) -m unittest discover -s ref/python/tests

vectors:
	@$(PYTHON) conformance/run.py

sim:
	@PYTHONPATH=ref/python:sim $(PYTHON) -m unittest discover -s sim/tests

experiments:
	@./scripts/check-experiments.sh

help:
	@sed -n '1,17p' Makefile
