# 0081. A relaxed alternative mempool behind the canonical rules, with declarations, reputation and three tiers

Date: 2026-11-04. Status: accepted.

## Context

EIP-8141's mempool rules exist "to avoid allowing an arbitrary number of
transactions to be invalidated by a single environmental change or state
modification" (EIP-8141 at `258836f9`, Mempool). Three of them bind a
contract that sends or pays for its own transactions:
- **FP-9** refuses a prefix that reads storage outside its sender;
- **FP-11** lets a non-canonical payer pay for one pending transaction;
- **FP-12** under `one` lets a sender have one.

A shared pool that sends its own withdrawals therefore has one pending at a
time, and so does a ticket paymaster.

ERC-7562 already allows alternative mempools: their rules "MUST be checked
only when a canonical rule is violated" (ALT-020), and reputation is kept
for each (ALT-040, AREP-010). `13-descriptors.md` makes a ruleset a file of
modules with inheritance.

The ask was for an alternative that relaxes the canonical rules without
letting transactions invalidate each other, with the bar for running a node
as low as it can be:
- **write-once reads** declared per code;
- **many pending per sender** on disjoint nonce keys;
- **the non-canonical payer's count lifted** under FP-11's exposure sum;
- **reputation per declared code** from each block's EIP-7928 access list;
- **groups for builders**;
- **relay, verifier and aggregator tiers**.

**The client.** A node run against a chain learns a prefix's outcome from
its execution client (`11-surface.md`, SF-4). The Hegota testnet runs
ethrex `v23.0.0-hegota-testnet-hotfix-64b8fc09d47d7787eb1a4e3f082aa9e831dc5f8c`,
by `web3_clientVersion` on 2026-11-04. At that commit:
- **its simulation method answers** `valid`, `prefixShape`, `payer`,
  `maxCost`, `violation`, `gasUsed`, `frames`, `executionStatus` and
  `executionError`, and no reads (`crates/networking/rpc/ethrex.rs`,
  `SimulateFrameTransactionResult`);
- **its validation observer keeps only the sender's slots.** It records any
  other storage read as the violation `StorageReadNonSender`
  (`crates/vm/levm/src/vm.rs`).

## Decision

1. **A fourth descriptor, `relaxed.json`, behind the canonical rules.** It
   inherits `eip-8141.json` and adds the `AG` and `CG` modules and new `RM`
   modules (`15-relaxed-mempool.md`).
   - **RM-2 is ALT-020.** A transaction the canonical modules admit is
     admitted as they admit it. Every other module, dependency frames and
     claims included, runs only for a transaction they refuse.
   - **So the canonical rules and their values stay in the descriptor:**
     `per_sender` `one` and `max_pending_noncanonical` 1, which DS-6 step 6
     requires.
   - **A transaction the canonical rules admit is treated as under
     `eip-8141.json`.** That holds for a ticket spend the claim-gated rules
     would refuse as well.
2. **Declarations are a descriptor's.** A declaration names a code, ranges
   of write-once slots, and an outflow bound. It lives in `RM-3`'s
   parameters, so a descriptor's identifier commits to it, and nodes that
   load one descriptor agree on which contracts are declared.
   - `relaxed.json` names none.
   - A child descriptor that replaces `RM-3` names a contract's (DS-5).
   - A declaration is a claim, not a proof: it is not verified from
     bytecode, and not confined to protocol predeploys.
3. **Write-once reads, with one reader for an unset slot.**
   - **A set slot** can change only by breaking its declaration, so any
     number of transactions may read it.
   - **An unset slot** can be written once, so the pool holds one relaxed
     reader, and that write invalidates one.
   - **The unset-slot rule** refuses only relaxed transactions. A
     transaction the canonical rules admit may read a declared slot of its
     own sender, and RM-2 never refuses it.
4. **Reputation counts violations, and acts at once.** A violation is either:
   - a storage change to a declared slot whose value before it is not 0;
   - a balance change larger than the declared outflow bound.

   Each block's access list shows both.
   - **The access list, not the state, is what shows a violation.** A
     second write in one block to an unset slot leaves the state looking
     like a first write. Only EIP-7928's per-transaction changes show two.
   - **One violation throttles the code at the reset that shows it,** and
     `ban_violations` (3) bans it.
   - **Violations decay** as ERC-8421's counters do, by 23/24 each
     `declaration_refresh_seconds`. That is CG-11's 3600.
   - **A throttled code** may be relied on by `throttled_count` relaxed
     pending transactions, CG-11's 4.
   - **The count is of violations,** not of seen and included operations,
     since a declaration fails by one write and not by a rate.
5. **Groups for builders are connected components.**
   - **The keys** are the nonce keys with their sender, the payer, and the
     declared slots read.
   - **Two transactions in different groups** share no key the pool knows.
   - **A group is a lower bound on conflicts.** The pool sees the prefix's
     keys and the payer, not every key execution writes.
6. **Three tiers, as a node setting.**
   - **A relay** holds nonce sequences, payer balances, the code of senders
     and payers, ticket paymasters' keys and the claims it has forwarded. It
     runs no prefix and checks no proof. It admits two kinds of transaction:
     - a prefix of protocol-defined frames only, which it evaluates as the
       EIP evaluates them directly;
     - a transaction with a valid claim.

     It forwards one transaction under each claim, and a replacement of it
     at the price bump, without the proofs of its dependencies.
   - **A verifier** runs everything.
   - **An aggregator** is a verifier that also aggregates.

   A relay's junk costs its sender a ticket, through CG-4 and CG-5 at the
   verifiers and one transaction per claim at each relay. A transaction
   with neither a claim nor a protocol-defined prefix is carried by
   verifiers alone, since a relay has nothing to make its sender pay with.
7. **The live node refuses `relaxed.json`.** A verdict carries no reads, and
   the testnet's client refuses a read outside the sender itself.
   - **The modules run in the vector runner**, as `erc-8421.json`'s do.
   - **A node loading the descriptor refuses it at start, with that
     reason.**
   - **Needed from the client:**
     - the prefix's storage reads, each with its address, slot and value,
       in the simulation's answer;
     - a mode that records a read outside the sender instead of refusing
       it.

## Not modelled

- How a verifier fetches the proofs a relay did not carry.
- Declarations on chain, and slots in a mapping.

## Consequences

- **The bound.** Under `relaxed.json`, one write invalidates at most one
  relaxed pending transaction, except a write that breaks a declaration,
  which invalidates every transaction that read the slot once, before
  reputation acts. That bound also needs decision record 0082, for
  relaxations 2 and 3. Experiment 27 measures it.
- **A node needs a client that returns reads** before it can run this
  descriptor against a chain.
