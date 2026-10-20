# 0039. An update is a program leanVM proves with its own hash, and the updater is a load

Date: 2026-10-13. Status: accepted.

## Context

The plan's item 31 tests a design for a privacy pool's tree. The pool
appends each output to a keccak hash chain, at one storage update a
transaction, and an updater, a role open to anyone, proves from time to
time that the pool's Merkle root is the tree of the first $k$ chained
outputs; spends prove membership under such a root. The price is latency: a
note can be spent only after the next update. The item asks for the time
and memory to prove that $k$ chained 32-byte outputs, hashed with keccak,
are the leaves of a depth-32 tree under leanVM's native hash, for $k$ of
10, 100 and 1,000. It also asks for a pool whose spends must cite a root
within EIP-8272's window, whose updater role is held by a share of nodes at
the benchmark's cost, and whose demand is Railgun's measured 15 to 38
outputs an hour and ten times that.

leanVM at `1f9e4c4f`, the commit `bench/leanvm/` pins, has one hash
instruction, BLAKE2s ("hash: BLAKE2s is a placeholder.
SHA2, SHA3, BLAKE3 are actively considered", its README), and no keccak. Its
`sha3` branch at `bf7b6b29` ("Merge main into sha3", 2026-10-12, a merge of
`1f9e4c4f`) replaces it: "SHA3-256 (FIPS 202), the repo's one hash
function", whose instruction is "the Keccak-f\[1600\] permutation", at a rate
of 136 bytes (`crates/primitives/src/hash.rs`). Ethereum's keccak256 is the
legacy Keccak-256, the same sponge at the same rate with another
domain-separation byte: Go's standard library builds `New256` as "rate:
rateK512, outputLen: 32, dsbyte: dsbyteSHA3" and `NewLegacyKeccak256` as
"rate: rateK512, outputLen: 32, dsbyte: dsbyteKeccak", with `dsbyteSHA3`
0b00000110 and `dsbyteKeccak` 0b00000001 (`crypto/internal/fips140/sha3/hashes.go`,
Go 1.25.1, read on this machine).

The design says nothing of how an update reaches the chain, beyond counting
the updater's root proof as one more folded dependency, nor of what happens
when two updaters prove the same outputs.

## Decision

1. **An update is a program, proved by leanVM, and timed on both of its
   hashes.** A guest program recomputes the chain from a given head over
   $k$ outputs, builds the subtree of the outputs, rounded up to $m$, a
   power of two, with zero leaves, and walks
   one path of siblings and direction bits from the subtree's slot to the
   root twice, from an empty subtree (the old root) and from the new one;
   it publishes the hash of both roots and both chain heads. It is timed at
   `1f9e4c4f`, where every hash is BLAKE2s, and at `bf7b6b29`, where every
   hash is SHA3-256. The second is the item's chain, to a constant:
   keccak256 of 64 bytes is one permutation, as SHA3-256 of 64 bytes is,
   and the two differ in one padding byte. Neither commit has the item's
   mix of keccak for the chain and another hash for the tree; on the `sha3`
   branch the tree's hash is the VM's native one, which is what the item
   asks of the tree.
2. **The update is an aligned subtree, and its position is not in the
   statement.** A batch of $k$ outputs fills a subtree of $m$ leaves at a
   slot where the old tree was empty, so the old and new roots share their
   siblings. An update at an unaligned position would hash a frontier
   instead, about as many nodes. A deployed update must bind the subtree's
   position into what it publishes; this one does not, and the cost of that
   is not counted. The outputs, the head and the siblings are random, since
   the cost does not depend on their values.
3. **The updater is a load, not a clause.** An update is an ordinary frame
   transaction with one leanSTARK dependency (EIP-8288), from the updater's
   own account; what it proves and what it writes are the pool contract's
   business, which no mempool clause reads. So there is no specification
   change and no vector: the simulator's `Updater` (`sim/emem_sim/workload.py`)
   holds the role at named nodes and reads the chain off blocks.
4. **A stale update reverts in execution, not in the pool.** The pool's
   contract compares an update's old root with its own when the update
   executes; EIP-8141's validation cannot read that storage, so the pool
   admits an update that another has overtaken, and a block carries it and
   it reverts, its sender paying. The first update of a coverage in block
   order takes effect, and its outputs can be spent from the next slot,
   which is RR-2 and RR-3's "only that root is referenceable beginning in
   slot `S + 1`" (`docs/spec/08-recent-roots.md`). The root is not written
   in the run, since nothing in it cites one.
5. **Holders race, or back off.** A holder proves when its head shows
   outputs past the coverage, if it has no update in flight. Racing is the
   open role with nothing added; backing off, a wait drawn below a bound and
   a look at its own pool for another holder's update of the same coverage,
   is the cheapest coordination that needs no new message. Neither is part
   of the design under test.
6. **The window is studied on the chain alone.** EIP-8272's usable window
   is 8,191 slots of 12 s, about 27 hours; it binds only on a policy that
   updates less often than that, and at Railgun's demand only a large $k$
   does. Simulating a network for the weeks that takes is out of
   proportion, so the study of the window draws outputs per slot and lands
   each update in the next slot.

## Consequences

- The guest was run once, on 2026-10-13, and the simulation takes the
  updater's proving time from the SHA3-256 line fitted to that run.
- The update's cost is the hash count the guest prints, not a keccak circuit
  in another proof system: a pool proving its tree in a SNARK over a prime
  field pays for keccak very differently, and nothing here measures that.
- A mixed design, keccak for the chain and BLAKE2s for the tree, would cost
  between the two runs; it is not measured.
- What pays an updater, and so how many hold the role, is open. The
  simulation measures what racing costs, not what makes anyone race.
