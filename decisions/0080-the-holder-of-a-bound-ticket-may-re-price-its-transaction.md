# 0080. The holder of a bound ticket may re-price its transaction

Date: 2026-10-21. Status: accepted.

## Context

CG-6 (rule R6) records a transaction's slot and claim whenever the pool
removes it for anything but a consumed nonce, and then refuses that slot and
claim for the rest of the claim's epoch. Decision record 0037 counted a
replacement as such a removal. Under version 5 a claim named only the slot,
so a replacement under the same claim could be anyone's copy, and counting
it limited each ticket to one replacement however many copies were sent.

Version 6 bound a ticket to its transaction (CG-12): under `binding` only
the holder of the one-time key the ticket names can make a transaction whose
claim is bound. Decision record 0069 found that CG-6 then limits only the
holder:
- a holder who re-prices once at the bump is admitted;
- a second re-pricing under the same ticket is `ErrClaimExpired`.

The owner decided that a holder's replacement should no longer count as a
removal. Each re-pricing still needs the bump, and stays within the ticket's
price.

## Decision

1. **Under `binding`, CG-6 records nothing when FP-12 replaces a
   transaction with one that carries the same claim.**
   `10-claim-gated-admission.md` becomes version 8.
   - Two claims with equal fields are one claim (CG-2), so the replacement
     carries the same slot, epoch, salt and binder.
   - CG-12 has already refused it unless its binder signed it, so it is the
     holder's.
2. **Every other removal is counted as before.** That covers:
   - a replacement under another ticket;
   - an eviction;
   - a drop at a new head for anything but a consumed nonce;
   - every removal under a profile without `binding`, where a replacement
     under the same claim may still be a copier's.
3. **What bounds the re-pricings.**
   - **The bump.** Each one raises both fees by `price_bump`, 10 percent,
     over the one it replaces (FP-12).
   - **The ticket's price.** A bound ticket paymaster refuses a `max_cost`
     above its denomination. That is the template's check (decision record
     0069, point 4), which a node learns from the client's verdict on the
     prefix (SF-4).

   A holder whose first transaction costs $c_0$ under a ticket of price $D$,
   with its gas limits held fixed, therefore re-prices at most
   $\lfloor \log(D / c_0) / \log(1.1) \rfloor$ times. Lowering the limits
   buys a few more, down to what the transaction needs. Each re-pricing
   costs a node one recovery for CG-12, one pairing for CG-9 and one
   simulation.
4. **CG-5 is unchanged.** It still binds a transaction with a dependency to
   one proof under each claim, so such a transaction re-prices only under a
   new ticket.
5. **No static check of the price.** A node reads the denomination from the
   paymaster's code (CG-10) and could refuse an over-priced re-pricing
   before the pairing. The decision asked for none, and the client's verdict
   already refuses it, so it is left for a later version.
6. **Vectors.**
   - `cg-12-binding.json`'s holder case now re-prices three times at the
     bump, and a fourth beyond the ticket's price is
     `ErrFramePrefixReverted` by the client's verdict, the third staying
     pending.
   - `cg-06-no-second-admission.json` gains two cases:
     - a replacement under another ticket is still recorded under
       `binding`;
     - without `binding`, a replacement under the same claim is still
       recorded.

## Consequences

- **A bound ticket now gives its holder the fee bumps any sender has,**
  until the transaction reaches the ticket's price. A copier still has
  none, since it cannot make a bound claim.
- **The version 7 consequence of decision record 0069, point 3, is
  replaced:** a second re-pricing under the same bound ticket is admitted.
- **Re-pricing with a dependency still needs a new ticket**, since R4 binds
  proofs, not claims.
