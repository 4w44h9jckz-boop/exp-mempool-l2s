# 0024. Wallets re-price the transaction that holds up the others, and users stop at a price of their own

Date: 2026-10-09. Status: accepted.

## Context

The plan's item 8 asks for fee bumping and elastic demand, and how fast the
backlog of experiment 00 clears with them. It also asks for a shared sender
under FP-12's `one`, whose stranded spend holds up every user and can be
re-priced only by its own user (experiment 01, "What it does not show").

What a pool does with a replacement is already specified: NP-11 and NP-12
for the account-nonce pool, with go-ethereum's `price_bump` of 10 percent,
and FP-12 for frame transactions, with the same rule. Both have vectors. What
is missing is wallets that send replacements and users who stop sending.
Neither is a pool's behaviour, and no source read here specifies either.

## Decision

1. **No clause changes.** The experiment exercises NP-11 to NP-13 and
   FP-12 as they stand. Bumping and elastic demand are the simulator's, in
   `BumpLoad` and `SharedSenderLoad` (`sim/emem_sim/workload.py`).
2. **A wallet re-prices its oldest unincluded transaction, or every one.**
   It does so once the node it sends to has imported `patience` blocks
   without the transaction, and then counts again. Re-pricing the oldest is
   what a speed-up button does to the transaction that holds up the rest;
   under NP-13 the later ones wait behind it and are re-priced in turn.
   Re-pricing every one is the other end. A first run measured only the
   oldest, on the reasoning that a sender's transactions land in nonce order
   anyway, and found that the reasoning was wrong: a builder can take a
   sender's consecutive nonces in one block, so a queue whose transactions
   are re-priced one at a time clears one at a time, and each may need
   several bumps of 10 percent. Both are measured. Neither is read from a
   wallet.
3. **Two sizes of bump.** One is the least NP-11 admits: tip and fee cap
   each up 10 percent, rounded up. The other is to the market: the fee cap
   is raised further, to the rule a wallet prices a new transaction by,
   twice the next base fee plus the tip. Both are assumed, not read from a
   wallet; the 10 percent is go-ethereum's `PriceBump` default (NP-1).
4. **Each sender's wallet sends to one node**, drawn when it first sends,
   and sends its replacements there. That is a wallet with one RPC
   endpoint. Experiment 00 sent each transfer to a random node. With seed 1
   and no bumping the two runs come out close but not identical.
5. **Elastic demand is a price per user.** Each arrival draws the most its
   user pays a gas, base fee and tip together, from a uniform range. The
   user does not send while the next base fee plus its tip is above that,
   caps its fee cap there, and does not bump past it. A user who does not
   send is demand that leaves, not demand that waits; it is counted, and
   never sends later. Two ranges are measured, neither from a source.
6. **Only a spend's user re-prices it.** A shared sender's spend commits
   its fees in the user's signature entry (decision record 0005, item 3), so
   the relayer cannot raise them. With `patience`, the user signs a new version
   once the relayer's node has imported `patience` blocks without the
   spend, and the relayer sends it in place of the old one. The nonce key,
   and so the identity under FP-12, stays the same.
7. **Five seeds.** Experiment 00 ran one. How much of the backlog is left
   after the burst depends on where the base fee is when the burst ends
   against the fee caps stranded in it, which a different draw of the
   network moves. So every row pools seeds 1 to 5 and reports the range
   over runs.

## Consequences

- `BumpLoad`, with `every`, `Transfer` and `bump_fees`, and `patience`,
  `bump` and `reprice` on `SharedSenderLoad`, with `Spend.versions`.
- Experiment 15.
- Not modelled: cancellation, a wallet that reads the pool rather than
  the head, fee estimators, users who come back later, and a relayer that
  re-prices out of its own pocket by sponsoring.
