# Experiment 27: results

Produced by `python3 experiments/27-relaxed-tiers/run.py` (seed 27). Do not edit by hand. The declarations are a child of `relaxed.json` that replaces RM-3 (DS-5), `bafkreiacy4p3vkrilpwppra2q7nn5falsaac2uvete7atpezeso5zncfq4`.

## 1. The worst-case invalidation from one write

The same seeded stream of 402 transactions into one pool under each descriptor, then, one at a time on a copy of that pool, every write it knows a key for, at the next head with its block's access list. Admitted counts what the canonical modules admitted and what only the relaxations did (RM-2); the worst write is the one that removed the most, over the writes that break no declaration, and then over those that do (RM-6). Seen counts the violating writes whose block raised the declared code's count. Re-run is the most prefixes one write made the pool run again (FP-15 step 3), over every write, and the write.

| descriptor | canonical | relaxed | refused | relaxed removed | by | all removed | by | violating: removed | by | seen | re-run | by |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| canonical | 46 | 0 | 356 | 0 |  | 1 | the note pool's undeclared slot | 1 | tpm pays out twice its bound | n/a | 1 | the note pool's undeclared slot |
| relaxed | 45 | 280 | 77 | 1 | a nullifier written | 1 | a nullifier written | 15 | a set root rewritten | 19 of 19 | 65 | tpm pays out its declared bound |
| relaxed, reuse_balance | 45 | 280 | 77 | 1 | a nullifier written | 1 | a nullifier written | 15 | a set root rewritten | 19 of 19 | 15 | a set root rewritten |
| relaxed, as first asked | 45 | 330 | 27 | 19 | upm, which declares nothing, pays out all it has | 20 | upm, which declares nothing, pays out all it has | 15 | a set root rewritten | 19 of 19 | 70 | tpm pays out its declared bound |

Removed by the worst write of each kind, relaxed / all, and the prefixes it re-ran:

| write | canonical | relaxed | relaxed, reuse_balance | relaxed, as first asked |
| --- | --- | --- | --- | --- |
| a nullifier written | 0 / 0 / 0 | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 |
| a nullifier written twice in one block | 0 / 0 / 0 | 1 / 1 / 1 | 1 / 1 / 1 | 1 / 1 / 1 |
| a set root rewritten | 0 / 0 / 0 | 15 / 15 / 15 | 15 / 15 / 15 | 15 / 15 / 15 |
| notes pays out its declared bound | 0 / 1 / 1 | 1 / 1 / 64 | 1 / 1 / 0 | 1 / 1 / 63 |
| notes pays out twice its bound | 0 / 1 / 1 | 2 / 2 / 64 | 2 / 2 / 0 | 2 / 2 / 63 |
| the account with no code delegates | 0 / 1 / 1 | 0 / 1 / 1 | 0 / 1 / 1 | 9 / 10 / 10 |
| the note pool's undeclared slot | 0 / 1 / 1 | 0 / 0 / 0 | 0 / 0 / 0 | 8 / 8 / 8 |
| the undeclared contract's slot | 0 / 1 / 1 | 0 / 1 / 1 | 0 / 1 / 1 | 9 / 10 / 10 |
| tpm pays out its declared bound | 0 / 1 / 1 | 1 / 1 / 65 | 1 / 1 / 0 | 1 / 1 / 70 |
| tpm pays out twice its bound | 0 / 1 / 1 | 2 / 2 / 65 | 2 / 2 / 0 | 2 / 2 / 70 |
| upm, which declares nothing, pays out all it has | 0 / 1 / 1 | 0 / 1 / 1 | 0 / 1 / 1 | 19 / 20 / 20 |

Refusals in the stream, by code:

| code | canonical | relaxed | relaxed, reuse_balance | relaxed, as first asked |
| --- | --- | --- | --- | --- |
| ErrFramePayerExposure | 0 | 5 | 5 | 11 |
| ErrFramePaymasterBusy | 88 | 19 | 19 | 0 |
| ErrFrameSenderBusy | 36 | 37 | 37 | 0 |
| ErrFrameStorageReadNonSender | 232 | 0 | 0 | 0 |
| ErrWriteOnceBusy | 0 | 16 | 16 | 16 |

## 2. A violated declaration's rate after

A pool under `relaxed.json` with declarations whose root contract was violated 0 to 3 times, one block each, then 20 new readers of roots no violation rewrote, at the start and after one and two of RM-6's hourly refreshes; the pool is emptied before each 20.

| violations | state | count at 0 h | admitted | count at 1 h | admitted | count at 2 h | admitted |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | ACTIVE | 0 | 20 | 0 | 20 | 0 | 20 |
| 1 | THROTTLED | 1 | 4 | 0 | 20 | 0 | 20 |
| 2 | THROTTLED | 2 | 4 | 1 | 4 | 0 | 20 |
| 3 | BANNED | 3 | 0 | 2 | 4 | 1 | 4 |

## 3. The tiers

A node under the canonical descriptor, and one of each tier under `relaxed.json` with declarations, fed the same seeded stream over 1536 s: honest spends paid by tickets, one proof each, arriving as a Poisson process at the rate shown; a junk sender's 20 tickets, each sent 5 times, each time with another failing proof; and 20 transactions with neither a claim nor a protocol-defined prefix. Every slot a block includes what the node holds. Prefixes counts the transactions whose prefix the node ran at admission, proofs the proofs it verified, CPU the verifying time a second at 12.8 ms a proof; pending, keys and claims are peaks at a block: keys are the state the pending transactions' recorded dependencies name, claims RM-8's forwarded claims of the current epoch; proofs held is what the pending transactions' proofs weigh, in MiB, at 319.9 KiB each; KiB in a second counts each transaction's 872 bytes 8.45 times, the copies a node of a 40-node network of degree 8 receives when every node sends it to every peer, and a verifier's proof once at 319.9 KiB.

| rate /s | tier | honest admitted | honest sent | prefixes | proofs | CPU ms/s | pending | keys | claims | proofs held | KiB/s in |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | canonical | 0 | 1519 | 20 | 0 | 0.0 | 1 | 3 | 0 | 0.0 | 0.0 |
| 1 | relay | 1519 | 1519 | 0 | 0 | 0.0 | 22 | 23 | 408 | 0.0 | 7.1 |
| 1 | verifier | 1519 | 1519 | 1559 | 1539 | 12.8 | 22 | 68 | 0 | 6.9 | 323.5 |
| 5 | canonical | 0 | 7747 | 20 | 0 | 0.0 | 1 | 3 | 0 | 0.0 | 0.0 |
| 5 | relay | 7747 | 7747 | 0 | 0 | 0.0 | 83 | 84 | 2003 | 0.0 | 36.3 |
| 5 | verifier | 7747 | 7747 | 7787 | 7767 | 64.7 | 83 | 251 | 0 | 25.9 | 1649.7 |
| 10 | canonical | 0 | 15384 | 20 | 0 | 0.0 | 1 | 3 | 0 | 0.0 | 0.0 |
| 10 | relay | 15384 | 15384 | 0 | 0 | 0.0 | 143 | 143 | 3843 | 0.0 | 72.1 |
| 10 | verifier | 15384 | 15384 | 15424 | 15404 | 128.4 | 143 | 428 | 0 | 44.7 | 3276.1 |
| 25 | canonical | 0 | 38696 | 20 | 0 | 0.0 | 1 | 3 | 0 | 0.0 | 0.0 |
| 25 | relay | 38696 | 38696 | 0 | 0 | 0.0 | 345 | 346 | 9681 | 0.0 | 181.3 |
| 25 | verifier | 38696 | 38696 | 38736 | 38716 | 322.6 | 345 | 1037 | 0 | 107.8 | 8240.4 |

Junk against each tier: what a relay carried per junk ticket, and what a verifier verified; and the transactions with neither a claim nor a protocol-defined prefix that each carried.

| rate /s | tier | junk sent | junk carried | junk proofs verified | carried per ticket | unchecked carried |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | canonical | 100 | 0 | 0 | 0.00 | 20 |
| 1 | relay | 100 | 20 | 0 | 1.00 | 0 |
| 1 | verifier | 100 | 0 | 20 | 0.00 | 20 |
| 5 | canonical | 100 | 0 | 0 | 0.00 | 20 |
| 5 | relay | 100 | 20 | 0 | 1.00 | 0 |
| 5 | verifier | 100 | 0 | 20 | 0.00 | 20 |
| 10 | canonical | 100 | 0 | 0 | 0.00 | 20 |
| 10 | relay | 100 | 20 | 0 | 1.00 | 0 |
| 10 | verifier | 100 | 0 | 20 | 0.00 | 20 |
| 25 | canonical | 100 | 0 | 0 | 0.00 | 20 |
| 25 | relay | 100 | 20 | 0 | 1.00 | 0 |
| 25 | verifier | 100 | 0 | 20 | 0.00 | 20 |

Per node, by mix, at a rate across the network, in KiB a second: a relay; a verifier that fetches each proof once; a verifier that receives each proof with its transaction, 8.45 times; one verifier's CPU, and the network's verifying in CPU seconds a second.

| mix | verifiers | rate /s | relay KiB/s | verifier, fetched once | verifier, pushed | verifier CPU ms/s | network CPU s/s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| every node verifies | 40 | 1 | n/a | 327 | 2710 | 13 | 0.5 |
| every node verifies | 40 | 5 | n/a | 1635 | 13552 | 64 | 2.6 |
| every node verifies | 40 | 10 | n/a | 3271 | 27104 | 128 | 5.1 |
| every node verifies | 40 | 25 | n/a | 8177 | 67759 | 320 | 12.8 |
| one verifier in two | 20 | 1 | 7.2 | 327 | 2710 | 13 | 0.3 |
| one verifier in two | 20 | 5 | 36.0 | 1635 | 13552 | 64 | 1.3 |
| one verifier in two | 20 | 10 | 72.0 | 3271 | 27104 | 128 | 2.6 |
| one verifier in two | 20 | 25 | 179.9 | 8177 | 67759 | 320 | 6.4 |
| one verifier in five | 8 | 1 | 7.2 | 327 | 2710 | 13 | 0.1 |
| one verifier in five | 8 | 5 | 36.0 | 1635 | 13552 | 64 | 0.5 |
| one verifier in five | 8 | 10 | 72.0 | 3271 | 27104 | 128 | 1.0 |
| one verifier in five | 8 | 25 | 179.9 | 8177 | 67759 | 320 | 2.6 |

The rate of proof-carrying transactions one 50 Mbps link carries into a node, by proof size, from the benchmark's smallest, mean and largest proof:

| proof KiB | relay | verifier, fetched once | verifier, pushed |
| --- | --- | --- | --- |
| 190.0 | 848 | 31.0 | 3.8 |
| 319.9 | 848 | 18.7 | 2.3 |
| 332.7 | 848 | 18.0 | 2.2 |

