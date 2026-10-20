# 0022. MATCHA's load floor is specified with the new charge as its unit, and measured against users who send alone

Date: 2026-10-09. Status: accepted.

## Context

The plan's item 12 asks what MATCHA's optional linear fees cost a user of a
busy shared sender against one who sends alone, at the same demand. An
earlier problem record argues that the floor prices a user by how busy their
anonymity set is. It names, as evidence that would retire it, a `base_price`
small enough relative to market priority fees that the floor never binds.

`04-matcha.md` version 1 left the policy out (*Not modelled*). The post
states it in one paragraph, read from topic 25949's raw text as cached on
2026-10-07 (`refs/refs.md`): "Each new additional transaction must offer a
minimum effective priority fee that rises linearly with this `load`. [...]
When all charges are equal, the floor is `base_price` for the first
additional transaction, twice `base_price` for the next, then three times,
and so on."

## Decision

1. **The floor is $\mathit{load\_price} \cdot (c + L) / c$**, with $c$ the
   new transaction's charge and $L$ the load. "Rises linearly with this
   `load`" fixes the shape, and the sequence for equal charges fixes the
   slope only when every charge is $c$. Taking the new transaction's own
   charge as the unit gives that sequence and needs no constant the post
   does not name. A fixed reference charge would need one, and the mean
   pending charge would make a transaction's floor depend on others' sizes
   twice. The experiment's spends all have one shape, so the reading does
   not move its numbers; the vectors pin it with unequal charges.
2. **Check 5 of MA-6 comes after width.** The post lists the policy apart
   from the admission checks, as something a client "may also track". A
   transaction refused for its fee then spends no width, and a transaction
   with no width is told so first.
3. **`load_price` is 0 in `matcha`.** The policy is optional in the post,
   so the profile is unchanged and every version 1 vector holds.
4. **The experiment's users read the floor.** A wallet that wants its spend
   in the next block offers the higher of the tip it drew and the floor of
   the node it sends to (`load_floor` in `sim/emem_sim/workload.py`). A
   second section has wallets that do not, and wait instead.
5. **The yardstick is the same spend from a sender of its own.** Users who
   send alone use the same frames and gas, and each is its own sender's
   baseline, so the floor never applies to them. They arrive at the same
   rate, in the same run, from a load of their own.
6. **The shared sender starts at the width cap.** Every node credits it
   with `width_cap` from block 0 before the run, as if it had been busy
   before. Without that, the first 64 to 95 slots measure experiment 02's
   wait for width, not the floor. Demand stops at three spends a slot,
   below the rate at which the cap runs out before the first finalized
   block earns more; refusals for width are reported, so a row where width
   bound would show it.

## Consequences

- `04-matcha.md` version 2: MA-13, `load_price` in MA-1, check 5 in MA-6
  and MA-7, and `load(sender)` in MA-12. Seven cases in
  `conformance/vectors/matcha/ma-13-load.json`, `expect_load` in the
  runner, and every MATCHA vector at version 2.
- `FramePool.load` and check 5 in `ref/python/emem/framepool/pool.py`.
- `SharedSenderLoad` takes `floor`, and `load_floor` gives the floor a pool
  asks of a transaction.
- Experiment 13 reports, for each `load_price` and demand, what shared and
  lone users offer over what they drew, how often the floor binds, how
  often other nodes refuse a spend for it, and the delay.
- Not modelled: the deterrent the floor is for, a batch of junk from the
  shared sender, whose $n$-th transaction faces $n$ times `load_price` by
  the clause's arithmetic; and a floor read at one node and refused at
  another being re-priced, since no wallet here bumps a fee.
