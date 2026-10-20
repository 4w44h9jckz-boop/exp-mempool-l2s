# exp-mempool-l2s: experiments with the Ethereum mempool

A base for experimenting with the Ethereum transaction pool. It holds three
things:

- **a specification** of expected mempool behaviour, as numbered clauses with
  their sources;
- **a reference implementation** of that specification;
- **a simulation base** that runs the reference on a network of nodes, so that
  an experiment is a seeded script whose output is committed and re-checked.

It covers the two pools that matter for current protocol work: the
account-nonce pool every node runs for transaction types 0 to 4, transcribed
from go-ethereum, and the EIP-8141 public mempool for frame transactions, with
EIP-8250 keyed nonces, as the EIP specifies it and as the Hegota testnet was
measured to enforce it.

## Layout

| Path | What it holds |
| --- | --- |
| [docs/spec/](docs/spec/) | The normative clauses: the model and fees (`00`), the account-nonce pool (`01`), the frame pool (`02`), block building (`03`) |
| [ref/python/emem/](ref/python/emem/) | The reference implementation: standard library only, written for a reader |
| [conformance/](conformance/) | Hand-written vectors, one file per clause, and the runner that plays them against the reference |
| [sim/emem_sim/](sim/emem_sim/) | The simulation base: event loop, gossiping nodes, block production, workloads, metrics |
| [experiments/](experiments/) | One question per folder, each with a deterministic `run.py` and its committed `results.md` |
| [bench/](bench/) | Measurements of a machine, committed once, with the tables derived from them checked |
| [decisions/](decisions/) | Why the repository is shaped the way it is |
| [refs/refs.md](refs/refs.md) | Sources, with commits and retrieval dates |

## Branches

As in [exp-frames](https://github.com/4w44h9jckz-boop/exp-frames):

| Branch | Holds | Merges into |
| --- | --- | --- |
| `main` | the specification, the vectors, the reference, the simulator, the finished experiments, the benchmarks, the decision records and the sources | none |
| `base` | changes to the specification, the reference and the simulator, in the order clause, vectors, then code; merged before any experiment that needs them | `main` |
| `exp/NN-name` | one experiment: its `run.py`, `results.md` and README | `main` |
| `plan` | the plan, what is built and what comes next, and the dated working log. Never merged | none |

The repository was published on 2026-10-20 from a tree kept until then in a
history that is not public. Decision records, results and documents written
before that date cite that history's commits where they name one; the
published tree is the record from that date on.

## Quick start

Nothing to install beyond Python 3 (CI uses 3.13).

```bash
make verify          # the fast checks: documents, unit tests, vectors
make experiments     # every experiment against its committed results, in parallel
make                 # both, which is everything CI runs
make vectors         # just the conformance vectors
python3 experiments/00-baseline/run.py    # one experiment, printed to stdout
```

Using the reference directly:

```python
import sys; sys.path.insert(0, "ref/python")
from emem import Account, Frame, FrameTx, Head, State, Tx, TxPool, build_block

state = State({"alice": Account(balance=10**18), "bob": Account(balance=10**18)})
head = Head(timestamp=1000, base_fee=10**9)
pool = TxPool(head, state)                       # geth + eip-8141 profiles
pool.add([Tx("alice", nonce=0, max_fee=3 * 10**9, tip=10**9),
          FrameTx("bob", (Frame(mode=1, flags=3, exec_gas=30000), Frame(mode=2, exec_gas=50000)),
                  max_fee=3 * 10**9, tip=10**9)])  # -> ["ok", "ok"]
block, post = build_block(pool, head, state)
pool.reset(block.head, post)
```

## How the parts fit

The specification is normative and the code is not. Vectors are written from
clauses, never generated from the code, and when the two disagree
`conformance/README.md` says how to decide which is wrong. An experiment that
finds the specification silent or ambiguous records that as an open question
in the clause, not as a quiet change to the code. Decision record 0001 has the
reasoning.

## Related repositories

- [exp-frames](https://github.com/4w44h9jckz-boop/exp-frames) sends real frame
  transactions to the ethrex Hegota testnet. It is the way to check the
  `hegota-testnet` profile against the chain, and its mined transactions are
  the fixtures the replay of `docs/spec/12-replay.md` reads.
- [skandha](https://github.com/4w44h9jckz-boop/skandha), a fork of an
  ERC-4337 bundler, carries a second implementation of the frame pool in
  TypeScript, `packages/framepool`, which plays this repository's vectors,
  and a node that takes frame transactions over JSON-RPC and gossip by
  `docs/spec/11-surface.md`.
- [kohaku-rs](https://github.com/4w44h9jckz-boop/kohaku-rs) builds frame
  transactions, including privacy-pool withdrawals, in Rust.

## License

Apache 2.0. See [LICENSE](LICENSE).
