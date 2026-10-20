# Reference implementation

| Path | Language | What |
| --- | --- | --- |
| `python/emem/` | Python 3, standard library only | Every clause of `docs/spec/` |
| `python/tests/` | `unittest` | Data-structure tests and randomised invariant checks |

The implementation is written for a reader. Each module names the clauses it
implements, and the account-nonce pool's method names follow the go-ethereum
functions they transcribe. It is not normative: the specification is, and the
vectors in `conformance/` judge this code against it.

| Module | Clauses |
| --- | --- |
| `model.py` | MD-1 to MD-4, FEE-1, FEE-2 |
| `tx.py` | MD-5 to MD-7, FEE-3, FEE-4, the replacement rule of NP-11 |
| `noncepool/` | NP-1 to NP-20 (`txlist.py` is go-ethereum's `list`, `priced.py` its `pricedList`) |
| `framepool/` | FP-1 to FP-16 (`prefix.py` holds the static checks and the simulation) |
| `reserver.py` | NP-8, FP-13 |
| `txpool.py` | MD-11 |
| `block.py` | BB-1 to BB-5 |

The pools also keep a `log` of `("pending", tx, ...)` and `("dropped", tx,
reason)` events, which the simulation reads to gossip transactions and to
count removals. The log is instrumentation and is not specified.

```bash
PYTHONPATH=ref/python python3 -m unittest discover -s ref/python/tests
```
