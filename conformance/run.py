#!/usr/bin/env python3
"""Play every vector in conformance/vectors against the reference implementation.

Usage: conformance/run.py [-v] [vector files or directories ...]

Exit status 0 when every case matches. A mismatch is reported with the clause,
the case and the step; `conformance/README.md` says what to do about one. This
script reads vectors and never writes them: there is no regeneration mode.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ref" / "python"))

from emem import (EIP_8141, FOCIL_PROFILES, GETH, PROFILES, SEALED_PROFILES, Account, Aggregator,  # noqa: E402
                  Claim, Dependency, Frame, FrameTx, Head, SealedTx, Signature, Stark, State, Tx, TxPool, Wrapper,
                  build_block, build_il, floor_data_gas, intrinsic_gas, next_base_fee, omission)
from emem.dependencies import union  # noqa: E402
from emem.claimticket import (TicketClaim, TicketFrame, carried as ticket_carried,  # noqa: E402
                              message as ticket_message, valid as ticket_valid)
from emem.focil import admitted  # noqa: E402
from emem.recentroots import source_id, write_root  # noqa: E402
from emem.sealed import fees  # noqa: E402
from emem.surface import SURFACE_PROFILES, Surface, address_form, decode, verdict  # noqa: E402
from emem.errors import TxError  # noqa: E402
from emem.replay import replay  # noqa: E402

DEFAULT_HEAD = {"number": 0, "timestamp": 1000, "gas_limit": 30_000_000, "gas_used": 15_000_000, "base_fee": 10}
ACCOUNT_FIELDS = ("nonce", "balance", "code", "storage", "nonce_seqs", "withdrawal")


class Mismatch(Exception):
    pass


# --- JSON to model ------------------------------------------------------------

def make_head(d: dict, base: dict | None = None) -> Head:
    merged = dict(DEFAULT_HEAD if base is None else base)
    merged.update(d or {})
    return Head(**merged)


def head_dict(h: Head) -> dict:
    return {"number": h.number, "timestamp": h.timestamp, "gas_limit": h.gas_limit,
            "gas_used": h.gas_used, "base_fee": h.base_fee, "slot": h.slot}


def merge_state(state: State | None, d: dict) -> State:
    """Field-wise merge of an account map over a state (conformance/README.md)."""
    new = state.copy() if state is not None else State()
    for addr, fields in (d or {}).items():
        acc = new.edit(addr)
        for key, value in fields.items():
            if key not in ACCOUNT_FIELDS:
                raise ValueError(f"unknown account field {key}")
            if key in ("storage", "nonce_seqs"):
                getattr(acc, key).update({int(k): v for k, v in value.items()})
            else:
                setattr(acc, key, value)
    return new


def write_roots(state: State, cfg, roots: list) -> None:
    """RR-3: entries as the writes `[source_address, salt, slot, root]` would leave them; `root` null empties one."""
    for address, salt, slot, root in roots or []:
        write_root(state, cfg, source_id(address, salt), slot, root)


def make_signature(d: dict) -> Signature:
    return Signature(**d)


def make_frame(d: dict) -> Frame:
    d = dict(d)
    if "opcodes" in d:
        d["opcodes"] = frozenset(d["opcodes"])
    for key in ("reads", "writes"):
        if key in d:
            d[key] = tuple(tuple(x) for x in d[key])
    if "calls" in d:
        d["calls"] = tuple(d["calls"])
    if "deps" in d:
        d["deps"] = make_deps(d["deps"])
    if "roots" in d:
        d["roots"] = tuple(tuple(x) for x in d["roots"])
    return Frame(**d)


def make_deps(triples: list) -> tuple[Dependency, ...]:
    return tuple(Dependency(*t) for t in triples)


def deps_json(deps) -> list:
    return [[d.scheme, d.data_hash, d.vk_hash] for d in deps]


def make_wrapper(d: dict) -> Wrapper:
    """AG-5; `deps`, `proofs` and `stark` default to an honest wrapper's (conformance/README.md)."""
    entries, txs = [], []
    for t in d["txs"]:
        if "hash" in t:
            tx = make_tx(t["hash"])
            entries.append(tx.hash)
        else:
            tx = make_tx(t)
            entries.append(tx)
        txs.append(tx)
    deps = make_deps(d["deps"]) if "deps" in d else union(txs)
    proofs = tuple(d.get("proofs", [True] * len(deps)))
    stark = None
    if d["mode"] != 0:
        s = d.get("stark", {})
        stark = Stark(make_deps(s["covers"]) if "covers" in s else deps, s.get("valid", True))
    signed = tuple(d.get("signed", ()))
    return Wrapper(tuple(entries), d["mode"], deps, proofs if d["mode"] == 0 else (), stark, signed)


def make_tx(d: dict):
    d = dict(d)
    for key in ("pulls", "pays"):  # MD-5 and LU-2: [account, amount] pairs
        if key in d:
            d[key] = tuple(tuple(x) for x in d[key])
    if d.get("type") == "st":
        d.pop("type")
        d.setdefault("sender", "alice")
        return SealedTx(**d)
    if d.get("type") == 6:
        d.pop("type")
        d["frames"] = tuple(make_frame(f) for f in d.get("frames", []))
        if "signatures" in d:
            d["signatures"] = tuple(make_signature(s) for s in d["signatures"])
        if "nonce_keys" in d:
            d["nonce_keys"] = tuple(d["nonce_keys"])
        if "claim" in d:
            c = dict(d["claim"])
            if "nonce_keys" in c:
                c["nonce_keys"] = tuple(c["nonce_keys"])
            d["claim"] = Claim(**c)
        for key in ("writes", "root_writes"):
            if key in d:
                d[key] = tuple(tuple(x) for x in d[key])
        d.setdefault("sender", "alice")
        return FrameTx(**d)
    if "authorities" in d:
        d["authorities"] = tuple(a if isinstance(a, str) else tuple(a) for a in d["authorities"])
    for key in ("writes", "root_writes"):
        if key in d:
            d[key] = tuple(tuple(x) for x in d[key])
    d.setdefault("sender", "alice")
    return Tx(**d)


def label(tx) -> str:
    return tx.label or tx.hash[:10]


# --- operations -----------------------------------------------------------------

def run_next_base_fee(case: dict) -> None:
    h = case["head"]
    got = next_base_fee(h["gas_limit"], h["gas_used"], h["base_fee"])
    if got != case["expect"]:
        raise Mismatch(f"expected {case['expect']}, got {got}")


def run_intrinsic_gas(case: dict) -> None:
    tx = make_tx(case["tx"])
    got = {"intrinsic": intrinsic_gas(tx), "floor": floor_data_gas(tx, GETH.floor_cost_per_token)}
    if got != case["expect"]:
        raise Mismatch(f"expected {case['expect']}, got {got}")


def run_frame_gas(case: dict) -> None:
    tx = make_tx(case["tx"])
    g = tx.gas
    got = {"intrinsic": g.intrinsic, "floor": g.floor, "max_gas": g.max_gas, "max_cost": tx.max_cost}
    if got != case["expect"]:
        raise Mismatch(f"expected {case['expect']}, got {got}")


def run_ticket_fee(case: dict) -> None:
    st = make_tx(case["st"])
    f = fees(st, case["base_fee"])
    got = {"can_pay": f is not None, "cost": st.cost}
    if f is not None:
        got.update(priority=f.priority, tob=f.tob, ticket_fee=f.ticket_fee)
    if got != case["expect"]:
        raise Mismatch(f"expected {case['expect']}, got {got}")


def run_pool(case: dict) -> None:
    profile = PROFILES[case.get("profile", EIP_8141.name)]
    config = case.get("config", {})
    nonce_cfg = GETH.with_(**config.get("nonce", {}))
    frame_cfg = profile.with_(**config.get("frame", {}))
    sealed_cfg = SEALED_PROFILES[case.get("sealed", "off")].with_(**config.get("sealed", {}))
    focil_cfg = FOCIL_PROFILES[case.get("focil", "off")].with_(**config.get("focil", {}))
    head_d = dict(DEFAULT_HEAD)
    head_d.update(case.get("head", {}))
    head = Head(**head_d)
    state = merge_state(None, case.get("state", {}))
    write_roots(state, frame_cfg, case.get("roots"))
    pool = TxPool(head, state, nonce_cfg, frame_cfg, sealed_config=sealed_cfg)
    aggregator = Aggregator(pool)
    scheduled = ()  # LU-13: the last block's commitments
    now = 0
    for n, step in enumerate(case["steps"]):
        where = f"step {n}"
        if "add" in step:
            now = step.get("now", now)
            txs = [make_tx(t) for t in step["add"]]
            got = pool.add(txs, now)
            if "expect" in step and got != step["expect"]:
                raise Mismatch(f"{where}: add expected {step['expect']}, got {got}")
        elif "wrapper" in step:
            now = step.get("now", now)
            got = aggregator.receive(make_wrapper(step["wrapper"]), now)
            if "expect" in step and got != step["expect"]:
                raise Mismatch(f"{where}: wrapper expected {step['expect']}, got {got}")
        elif "aggregate" in step:
            w = aggregator.aggregate()
            if w is None:
                if step.get("expect", None) is not None:
                    raise Mismatch(f"{where}: aggregate expected {step['expect']}, got none")
                continue
            if step.get("expect", ...) is None:
                raise Mismatch(f"{where}: aggregate expected none, got one")
            names = [label(e if isinstance(e, FrameTx) else pool.frame.entries[e].tx) for e in w.txs]
            hashed = [n for n, e in zip(names, w.txs) if not isinstance(e, FrameTx)]
            if "expect" in step and names != step["expect"]:
                raise Mismatch(f"{where}: aggregate expected {step['expect']}, got {names}")
            if "expect_hashed" in step and hashed != step["expect_hashed"]:
                raise Mismatch(f"{where}: aggregate hashes expected {step['expect_hashed']}, got {hashed}")
            if "expect_deps" in step and deps_json(w.deps) != step["expect_deps"]:
                raise Mismatch(f"{where}: aggregate deps expected {step['expect_deps']}, got {deps_json(w.deps)}")
            if "expect_time" in step and aggregator.proving_time != step["expect_time"]:
                raise Mismatch(f"{where}: aggregate proving time expected {step['expect_time']}, "
                               f"got {aggregator.proving_time}")
            if "expect_memory" in step and aggregator.memory != step["expect_memory"]:
                raise Mismatch(f"{where}: aggregate memory expected {step['expect_memory']}, got {aggregator.memory}")
        elif "reset" in step:
            now = step.get("now", now)
            head_d.update(step["reset"].get("head", {}))
            head = Head(**head_d)
            state = merge_state(state, step["reset"].get("state", {}))
            write_roots(state, frame_cfg, step["reset"].get("roots"))
            by_label = {label(tx): tx.hash for txs in pool.frame.content().values() for tx in txs}
            verdicts = {by_label[k]: v for k, v in step["reset"].get("verdicts", {}).items()}  # MD-8
            pool.reset(head, state, now, verdicts)
        elif "tick" in step:
            now = step["tick"]
            pool.tick(now)
        elif "finalize" in step:
            now = step.get("now", now)
            pool.finalize([(b["number"], dict(b.get("gas", {}))) for b in step["finalize"]], now)
        elif "expect_width" in step:
            got = {s: pool.frame.width(s) for s in step["expect_width"]}
            if got != step["expect_width"]:
                raise Mismatch(f"{where}: width expected {step['expect_width']}, got {got}")
        elif "expect_load" in step:
            got = {s: pool.frame.load(s) for s in step["expect_load"]}
            if got != step["expect_load"]:
                raise Mismatch(f"{where}: load expected {step['expect_load']}, got {got}")
        elif "expect_baseline" in step:
            got = {}
            for s in step["expect_baseline"]:
                h = pool.frame.baseline(s)
                got[s] = None if h is None else label(pool.frame.entries[h].tx)
            if got != step["expect_baseline"]:
                raise Mismatch(f"{where}: baseline expected {step['expect_baseline']}, got {got}")
        elif "expect_baselines" in step:
            got = {s: [label(pool.frame.entries[h].tx) for h in pool.frame.baselines(s)]
                   for s in step["expect_baselines"]}
            if got != step["expect_baselines"]:
                raise Mismatch(f"{where}: baselines expected {step['expect_baselines']}, got {got}")
        elif "expect_pool" in step:
            pending, queued = pool.content()
            got = {"pending": {s: [label(t) for t in txs] for s, txs in pending.items()},
                   "queued": {s: [label(t) for t in txs] for s, txs in queued.items()}}
            want = {"pending": step["expect_pool"].get("pending", {}),
                    "queued": step["expect_pool"].get("queued", {})}
            if got != want:
                raise Mismatch(f"{where}: pool expected {want}, got {got}")
        elif "expect_view" in step:
            v = step["expect_view"]
            from emem.block import PriceAndNonce
            order = PriceAndNonce(pool.nonce.pending_view(v["min_tip"], v["base_fee"]),
                                  pool.frame.pending_view(v["min_tip"], v["base_fee"]),
                                  v["base_fee"], pool.arrival)
            got = []
            while order.peek() is not None:
                got.append(label(order.peek()))
                order.shift()
            if got != step["expect"]:
                raise Mismatch(f"{where}: view expected {step['expect']}, got {got}")
        elif "expect_selection" in step:
            v = step["expect_selection"]
            got = [label(t) for t in pool.sealed.selection(v.get("base_fee", head.next_base_fee()), v.get("min_tip", 0))]
            if got != step["expect"]:
                raise Mismatch(f"{where}: selection expected {step['expect']}, got {got}")
        elif "expect_resimulated" in step:
            got = [label(t) for t in pool.frame.resimulated]
            if got != step["expect_resimulated"]:
                raise Mismatch(f"{where}: resimulated expected {step['expect_resimulated']}, got {got}")
        elif "il" in step:
            got = [label(t) for t in build_il(pool, step["il"].get("base_fee", head.next_base_fee()), focil_cfg)]
            if got != step["expect"]:
                raise Mismatch(f"{where}: il expected {step['expect']}, got {got}")
        elif "build" in step:
            b = step["build"]
            ils = tuple(tuple(make_tx(t) for t in il) for il in b.get("ils", []))
            leave = set(b.get("skip", []))
            block, post = build_block(pool, head, state, min_tip=b.get("min_tip", 1),
                                      coinbase=b.get("coinbase", "coinbase"), scheduled=scheduled, ils=ils,
                                      focil=focil_cfg, skip=(lambda t: t.sender in leave) if leave else None,
                                      slot=b.get("slot"), dimensions=b.get("dimensions", "one"),
                                      drop_reverting=b.get("drop_reverting", False))
            missing = omission(block.txs, post, block.head, block.gas, ils, frame_cfg, focil_cfg)
            got = None if missing is None else label(missing)
            if "expect_omission" in step and got != step["expect_omission"]:
                raise Mismatch(f"{where}: omission expected {step['expect_omission']}, got {got}")
            if "expect_canonical" in step and (missing is None) != step["expect_canonical"]:
                raise Mismatch(f"{where}: canonical expected {step['expect_canonical']}, got {missing is None}")
            if missing is None:  # IL-8: a block that leaves a listed transaction out is not canonical
                state = post
                scheduled = block.commitments
                head = block.head
                head_d = head_dict(head)
                now += 12
                pool.reset(head, state, now)
            got = [label(t) for t in block.txs]
            if "expect" in step and got != step["expect"]:
                raise Mismatch(f"{where}: block expected {step['expect']}, got {got}")
            got = [[label(t), err] for t, err in block.failed]
            if "expect_failed" in step and got != step["expect_failed"]:
                raise Mismatch(f"{where}: failed expected {step['expect_failed']}, got {got}")
            if "expect_gas_used" in step and head.gas_used != step["expect_gas_used"]:
                raise Mismatch(f"{where}: gas used expected {step['expect_gas_used']}, got {head.gas_used}")
            got = [label(c.tx) for c in block.commitments]
            if "expect_commitments" in step and got != step["expect_commitments"]:
                raise Mismatch(f"{where}: commitments expected {step['expect_commitments']}, got {got}")
            got = [label(t) for t in block.decrypted]
            if "expect_decrypted" in step and got != step["expect_decrypted"]:
                raise Mismatch(f"{where}: decrypted expected {step['expect_decrypted']}, got {got}")
        elif "expect_state" in step:
            for addr, fields in step["expect_state"].items():
                acc = state.account(addr)
                for key, want in fields.items():
                    have = getattr(acc, key)
                    if key in ("storage", "nonce_seqs"):
                        want = {int(k): v for k, v in want.items()}
                    if have != want:
                        raise Mismatch(f"{where}: {addr}.{key} expected {want}, got {have}")
        else:
            raise ValueError(f"{where}: unknown step {sorted(step)}")


def _compare(expected, got, where: str) -> None:
    """Every key `expected` names must match; a null expects the field absent (None)."""
    if isinstance(expected, dict):
        if not isinstance(got, dict):
            raise Mismatch(f"{where}: expected an object, got {got!r}")
        for k, v in expected.items():
            _compare(v, got.get(k), f"{where}.{k}")
    elif isinstance(expected, list) and expected and isinstance(expected[0], dict):
        if not isinstance(got, list) or len(got) != len(expected):
            raise Mismatch(f"{where}: expected {len(expected)} entries, got {got!r}")
        for i, (e, g) in enumerate(zip(expected, got)):
            _compare(e, g, f"{where}[{i}]")
    elif expected != got:
        raise Mismatch(f"{where}: expected {expected!r}, got {got!r}")


def _model_json(tx: FrameTx) -> dict:
    """SF-3's model transaction, in the vectors' names."""
    return {"sender": tx.sender, "nonce_keys": list(tx.nonce_keys), "nonce_seq": tx.nonce_seq, "tip": tx.tip,
            "max_fee": tx.max_fee, "size": tx.size, "zero_bytes": tx.zero_bytes,
            "frames": [{"mode": f.mode, "flags": f.flags, "target": f.target, "exec_gas": f.exec_gas,
                        "state_gas": f.state_gas, "value": f.value, "data_size": f.data_size,
                        "deadline": f.deadline, "roots": [list(r) for r in f.roots]} for f in tx.frames],
            "signatures": [{"scheme": s.scheme, "signer": s.signer, "canonical_msg": s.canonical_msg,
                            "valid": s.valid, "length": s.length} for s in tx.signatures]}


def run_surface(case: dict) -> None:
    """`docs/spec/11-surface.md`: one node's surface over the pool of `run_pool`."""
    name = case.get("profile", EIP_8141.name)
    config = case.get("config", {})
    frame_cfg = address_form(PROFILES[name].with_(**config.get("frame", {})))
    surface_cfg = SURFACE_PROFILES[name].with_(**config.get("surface", {}))
    head_d = dict(DEFAULT_HEAD)
    head_d.update(case.get("head", {}))
    state = merge_state(None, case.get("state", {}))
    focil_cfg = FOCIL_PROFILES[case.get("focil", "off")].with_(**config.get("focil", {}))
    pool = TxPool(Head(**head_d), state, GETH, frame_cfg)
    node = Surface(pool, surface_cfg, case.get("peers", []))
    named = {label: decode(bytes.fromhex(raw[2:]), frame_cfg, surface_cfg) for label, raw in case.get("txs", {}).items()}
    alias: dict[str, str] = {}
    names = lambda hashes: [next((a for a, x in alias.items() if x == h), h) for h in hashes]  # noqa: E731
    now = 0
    for n, step in enumerate(case["steps"]):
        where = f"step {n}"
        now = step.get("now", now)
        if "decode" in step:
            raw = bytes.fromhex(step["decode"][2:])
            try:
                tx = decode(raw, frame_cfg, surface_cfg)
                got = {"result": "ok", "hash": tx.label, "tx": _model_json(tx),
                       "gas": {"max_gas": tx.max_gas, "max_cost": tx.max_cost}}
            except TxError as err:
                got = {"result": err.code}
            _compare(step["expect"], got, where)
        elif "verdict" in step:
            _compare(step["expect"], verdict(step["verdict"]), where)
        elif "rpc" in step or "peer" in step:
            try:
                if "rpc" in step:
                    got = node.rpc(step["rpc"], step.get("client"), now)
                else:
                    got = node.peer(step["peer"], step["from"], step.get("client"), now)
            except ValueError as err:  # the surface asked the client about something the vector did not expect
                raise Mismatch(f"{where}: {err}") from None
            if "as" in step:
                alias[step["as"]] = got["hash"] if "hash" in got else decode(
                    bytes.fromhex((step.get("rpc") or step["peer"])[2:]), frame_cfg, surface_cfg).label
            _compare(step["expect"], got, where)
        elif "head" in step:
            head_d.update(step["head"])
            state = merge_state(state, step.get("state", {}))
            answers = {alias.get(k, k): v for k, v in step.get("client", {}).items()}
            try:
                asked = node.head(Head(**head_d), state, answers, now)
            except ValueError as err:
                raise Mismatch(f"{where}: {err}") from None
            if "expect_asked" in step and names(asked) != step["expect_asked"]:
                raise Mismatch(f"{where}: asked expected {step['expect_asked']}, got {names(asked)}")
            resim = names([tx.label for tx in pool.frame.resimulated])
            if "expect_resimulated" in step and resim != step["expect_resimulated"]:
                raise Mismatch(f"{where}: re-simulated expected {step['expect_resimulated']}, got {resim}")
            pending = names(node.pending())
            if "expect_pending" in step and pending != step["expect_pending"]:
                raise Mismatch(f"{where}: pending expected {step['expect_pending']}, got {pending}")
        elif "il" in step:  # IL-2, from the node's pool
            got = names([tx.label for tx in build_il(pool, step["il"].get("base_fee", pool.head.next_base_fee()),
                                                    focil_cfg)])
            if got != step["expect"]:
                raise Mismatch(f"{where}: listed expected {step['expect']}, got {got}")
        elif "inclusion" in step:  # IL-4 and IL-6, the node's own reading of the slot's ILs
            inc = step["inclusion"]
            ils = tuple(tuple(named[label] for label in il) for il in inc["ils"])
            delivered = None
            if "delivered" in inc:
                delivered = [named[label] for label in inc["delivered"]]
                if sorted(inc["delivered"]) != sorted({label for il in inc["ils"] for label in il}):
                    raise Mismatch(f"{where}: delivered is not the ILs' transactions, each once")
            label_of = {tx.hash: label for label, tx in named.items()}
            got = [label_of[h] for h in admitted(ils, pool.head, frame_cfg, focil_cfg, delivered)]
            if "expect_admitted" in step and got != step["expect_admitted"]:
                raise Mismatch(f"{where}: admitted expected {step['expect_admitted']}, got {got}")
            if "block" in inc:
                verdicts = {named[label].hash: True for label in inc.get("valid", [])}
                missing = omission([named[label] for label in inc["block"]], state, pool.head, inc["gas_left"], ils,
                                   frame_cfg, focil_cfg, delivered, verdicts)
                got_o = label_of[missing.hash] if missing is not None else None
                if got_o != step.get("expect_omission"):
                    raise Mismatch(f"{where}: omission expected {step.get('expect_omission')}, got {got_o}")
        else:
            raise Mismatch(f"{where}: unknown step {sorted(step)}")


def _ticket_claim(d: dict) -> TicketClaim:
    return TicketClaim(int(d["chain_id"], 16), int(d.get("epoch", "0x0"), 16), bytes.fromhex(d["sender"][2:]),
                       int(d["nonce_seq"], 16), tuple(int(k, 16) for k in d["nonce_keys"]),
                       bytes.fromhex(d.get("salt", "0x")[2:]))


def run_claim_ticket(case: dict) -> None:
    """`docs/spec/10-claim-gated-admission.md`, CG-8 to CG-10: a ticket's message, its verdict, and where it rides."""
    if "frames" in case:  # CG-10
        epoch = int(case["head_epoch"], 16)
        paymasters, accepted = {}, {}
        for p in case["paymasters"]:
            key = bytes.fromhex(p["key"][2:])
            accepted.setdefault(int(p["epoch"], 16), set()).add(key)
            if int(p["epoch"], 16) == epoch:
                paymasters[bytes.fromhex(p["address"][2:])] = key
        frames = [TicketFrame(f["mode"], bytes.fromhex(f["target"][2:]), bytes.fromhex(f["data"][2:]))
                  for f in case["frames"]]
        found = ticket_carried(_ticket_claim(case["tx"]), frames, paymasters, accepted)
        if found is None:
            got = {"claim": None}
        else:
            (e, salt, issuer), ok = found
            got = {"claim": {"epoch": None if e is None else hex(e), "salt": None if salt is None else "0x" + salt.hex(),
                             "issuer": "0x" + issuer.hex()}, "valid": ok}
        _compare(case["expect"], got, "claim_ticket")
        return
    claim = _ticket_claim(case["claim"])
    m = ticket_message(claim)
    got = {"message": None if m is None else "0x" + m.hex()}
    if "issuer" in case:
        accepted: dict[int, set[bytes]] = {}
        for a in case["issuers"]:
            accepted.setdefault(int(a["epoch"], 16), set()).update(bytes.fromhex(k[2:]) for k in a["keys"])
        got["valid"] = ticket_valid(claim, bytes.fromhex(case["issuer"][2:]),
                                    bytes.fromhex(case["signature"][2:]), accepted)
    _compare(case["expect"], got, "claim_ticket")


def run_replay(case: dict) -> None:
    """`docs/spec/12-replay.md`: one fixture under one profile."""
    name = case.get("profile", EIP_8141.name)
    config = case.get("config", {})
    frame_cfg = address_form(PROFILES[name].with_(**config.get("frame", {})))
    surface_cfg = SURFACE_PROFILES[name].with_(**config.get("surface", {}))
    f = case["fixture"]
    got = replay(bytes.fromhex(f["raw"][2:]), f["hash"], f["payer"], f["parent"], frame_cfg, surface_cfg)
    _compare(case["expect"], got, "replay")


OPERATIONS = {"next_base_fee": run_next_base_fee, "intrinsic_gas": run_intrinsic_gas,
              "frame_gas": run_frame_gas, "ticket_fee": run_ticket_fee, "pool": run_pool,
              "surface": run_surface, "replay": run_replay, "claim_ticket": run_claim_ticket}


def vector_files(args: list[str]) -> list[Path]:
    paths = [Path(a) for a in args] or [ROOT / "conformance" / "vectors"]
    files: list[Path] = []
    for p in paths:
        files.extend(sorted(p.rglob("*.json")) if p.is_dir() else [p])
    return files


def main(argv: list[str]) -> int:
    verbose = "-v" in argv
    files = vector_files([a for a in argv if a != "-v"])
    passed = failed = 0
    for path in files:
        vector = json.loads(path.read_text())
        run = OPERATIONS[vector["operation"]]
        for case in vector["cases"]:
            try:
                run(case)
            except Mismatch as m:
                failed += 1
                print(f"FAIL {vector['clause']} {path.name}: {case['name']}: {m}")
                continue
            passed += 1
            if verbose:
                print(f"ok   {vector['clause']} {path.name}: {case['name']}")
    print(f"{passed} passed, {failed} failed, {len(files)} vector files")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
