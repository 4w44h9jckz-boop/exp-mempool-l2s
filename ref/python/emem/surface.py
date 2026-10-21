"""The surface around a frame pool: `docs/spec/11-surface.md`, SF-1 to SF-9.

Bytes in (SF-2, SF-3), a client's verdict on the prefix (SF-4), answers over
JSON-RPC (SF-5), relay to peers and what is taken from them (SF-6, SF-7), head
changes (SF-8) and hand-off to a client (SF-9). The client and the network are
not here: a caller passes the client's answer for each transaction it could be
asked about, and the peers the node has, and reads back what was asked, relayed
and handed on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from . import errors as E
from .errors import TxError
from .framepool.config import FramePoolConfig
from .keccak import keccak256
from .model import Head, State
from .claimticket import TicketClaim, TicketFrame, TxSignature, bound, carried
from .tx import Claim, Frame, FrameTx, Signature
from .txpool import TxPool

FRAME_TX_TYPE = 0x06
SCHEMES = {0: "arbitrary", 1: "secp256k1", 2: "p256"}
SIGNATURE_LENGTH = {"secp256k1": 65, "p256": 128}  # SF-3: any other length is malformed, so not valid
U64, U256 = 1 << 64, 1 << 256
INVALID_PARAMS, SERVER_ERROR = -32602, -32000  # SF-5


@dataclass(frozen=True)
class SurfaceConfig:
    """SF-1."""

    envelope: str = "keyed"
    chain_id: int = 1
    max_tx_size: int = 131072
    relay: str = "eth"
    handoff: bool = False

    def with_(self, **kw) -> "SurfaceConfig":
        return replace(self, **kw)


SURFACE_PROFILES = {
    "eip-8141": SurfaceConfig(),
    "hegota-testnet": SurfaceConfig(chain_id=8141),
}


def address_form(cfg: FramePoolConfig) -> FramePoolConfig:
    """SF-3: the profile's distinguished addresses compared in the form the surface writes addresses in."""
    return cfg.with_(expiry_verifier=cfg.expiry_verifier.lower(), recent_root_address=cfg.recent_root_address.lower())


# --- canonical RLP, SF-2 step 3 ---------------------------------------------------

class Malformed(Exception):
    """SF-2 step 3: the bytes are not one canonical RLP item of the envelope's shape."""


def _length(b: bytes, i: int, n: int) -> int:
    if i + n > len(b) or b[i] == 0:
        raise Malformed("length")
    length = int.from_bytes(b[i:i + n], "big")
    if length <= 55:
        raise Malformed("long form for a short length")
    return length


def _item(b: bytes, i: int):
    """One RLP item at `i`: bytes or a list, and the index after it."""
    if i >= len(b):
        raise Malformed("truncated")
    p = b[i]
    if p < 0x80:
        return b[i:i + 1], i + 1
    if p <= 0xB7:
        n, start = p - 0x80, i + 1
        if n == 1 and start < len(b) and b[start] < 0x80:
            raise Malformed("a single byte below 0x80 with a length")
    elif p <= 0xBF:
        n, start = _length(b, i + 1, p - 0xB7), i + 1 + (p - 0xB7)
    else:
        if p <= 0xF7:
            n, start = p - 0xC0, i + 1
        else:
            n, start = _length(b, i + 1, p - 0xF7), i + 1 + (p - 0xF7)
        end = start + n
        if end > len(b):
            raise Malformed("truncated list")
        items, j = [], start
        while j < end:
            item, j = _item(b, j)
            items.append(item)
        if j != end:
            raise Malformed("list overruns")
        return items, end
    end = start + n
    if end > len(b):
        raise Malformed("truncated string")
    return b[start:end], end


def _int(x) -> int:
    if not isinstance(x, bytes) or (x and x[0] == 0):
        raise Malformed("integer")
    return int.from_bytes(x, "big")


def _bytes(x) -> bytes:
    if not isinstance(x, bytes):
        raise Malformed("byte string")
    return x


def _list(x, n: int | None = None) -> list:
    if not isinstance(x, list) or (n is not None and len(x) != n):
        raise Malformed("list")
    return x


def _parse(payload: bytes, envelope: str) -> dict:
    """SF-2 step 3: the envelope's fields, each of its kind."""
    top, end = _item(payload, 0)
    if end != len(payload):
        raise Malformed("bytes after the list")
    top = _list(top, 8 if envelope == "keyed" else 7)
    if envelope == "keyed":
        chain, keys, seq, sender, frames, sigs, fees, blobs = top
        keys = [_int(k) for k in _list(keys)]
    else:
        chain, seq, sender, frames, sigs, fees, blobs = top
        keys = None
    out = {"chain_id": _int(chain), "nonce_keys": keys, "nonce_seq": _int(seq), "sender": _bytes(sender)}
    out["frames"] = []
    for f in _list(frames):
        mode, flags, target, limits, value, data = _list(f, 6)
        execution, state = _list(limits, 2)
        out["frames"].append({"mode": _int(mode), "flags": _int(flags), "target": _bytes(target),
                              "exec": _int(execution), "state": _int(state), "value": _int(value),
                              "data": _bytes(data)})
    out["signatures"] = []
    for s in _list(sigs):
        scheme, signer, msg, signature = _list(s, 4)
        out["signatures"].append({"scheme": _int(scheme), "signer": _bytes(signer), "msg": _bytes(msg),
                                  "signature": _bytes(signature)})
    tip, max_fee, blob_fee = (_int(x) for x in _list(fees, 3))
    out.update(tip=tip, max_fee=max_fee, blob_fee=blob_fee)
    out["blobs"] = [_bytes(h) for h in _list(blobs)]
    return out


def _rlp_int(x: int) -> bytes:
    if x == 0:
        return b"\x80"
    b = x.to_bytes((x.bit_length() + 7) // 8, "big")
    return b if len(b) == 1 and b[0] < 0x80 else bytes([0x80 + len(b)]) + b


def _rlp_list(items: list[bytes]) -> bytes:
    body = b"".join(items)
    if len(body) <= 55:
        return bytes([0xC0 + len(body)]) + body
    n = len(body).to_bytes((len(body).bit_length() + 7) // 8, "big")
    return bytes([0xF7 + len(n)]) + n + body


def _encode(item) -> bytes:
    """Canonical RLP of an item `_item` parsed: a byte string or a list."""
    if isinstance(item, list):
        return _rlp_list([_encode(x) for x in item])
    if len(item) == 1 and item[0] < 0x80:
        return item
    if len(item) <= 55:
        return bytes([0x80 + len(item)]) + item
    n = len(item).to_bytes((len(item).bit_length() + 7) // 8, "big")
    return bytes([0xB7 + len(n)]) + n + item


def sig_hash(raw: bytes, envelope: str = "keyed") -> bytes:
    """EIP-8141's `compute_sig_hash` of a transaction that SF-2 decoded: the `signature` bytes of every signature
    with an empty `msg` emptied, then the keccak256 of the type byte and the payload (CG-12)."""
    top, _ = _item(raw[1:], 0)
    for s in top[5 if envelope == "keyed" else 4]:
        if s[2] == b"":
            s[3] = b""
    return keccak256(raw[:1] + _encode(top))


def _malformed(t: dict, envelope: str) -> bool:
    """SF-2 step 5: the EIP's constraints FP-3 does not check itself."""
    if t["nonce_seq"] >= U64 or t["chain_id"] >= U256 or len(t["sender"]) != 20:
        return True
    if envelope == "keyed" and any(k >= U256 for k in t["nonce_keys"]):
        return True
    if t["tip"] >= U256 or t["max_fee"] >= U256 or t["blob_fee"] != 0:
        return True
    total = 0
    for f in t["frames"]:
        if f["value"] >= U256 or len(f["target"]) not in (0, 20) or f["exec"] >= U64 or f["state"] >= U64:
            return True
        total += f["exec"] + f["state"]
    if total >= U64:
        return True
    for s in t["signatures"]:
        if s["scheme"] not in SCHEMES or len(s["signer"]) not in (0, 20):
            return True
        if s["scheme"] == 0 and s["signer"]:
            return True
        if len(s["msg"]) not in (0, 32) or s["msg"] == b"\x00" * 32:
            return True
    return False


def _hex(b: bytes) -> str:
    return "0x" + b.hex()


def decode(raw: bytes, frame_cfg: FramePoolConfig, cfg: SurfaceConfig,
           codes: dict[str, bytes] | None = None) -> FrameTx:
    """SF-2 and SF-3: the model transaction, or a TxError with the first failure. `codes` is the code at the
    head of the accounts the transaction's frames target, as the client answers it (SF-3's `claim`)."""
    if not raw or raw[0] != FRAME_TX_TYPE:
        raise TxError(E.ErrTxTypeNotSupported)
    if len(raw) > cfg.max_tx_size:
        raise TxError(E.ErrOversizedData)
    try:
        t = _parse(raw[1:], cfg.envelope)
    except Malformed:
        raise TxError(E.ErrFrameDecode) from None
    if t["blobs"]:
        raise TxError(E.ErrFrameBlobs)
    if _malformed(t, cfg.envelope):
        raise TxError(E.ErrFrameMalformed)
    if t["chain_id"] != cfg.chain_id:
        raise TxError(E.ErrInvalidChainId)
    keys = t["nonce_keys"] if t["nonce_keys"] is not None else [0]
    expiry = frame_cfg.expiry_verifier.lower()
    root_verifier = frame_cfg.recent_root_address.lower() if frame_cfg.recent_roots else None
    frames, data = [], []
    for f in t["frames"]:
        target = _hex(f["target"]) if f["target"] else None
        deadline = int.from_bytes(f["data"], "big") if target == expiry and len(f["data"]) == 8 else None
        roots = _roots(f["data"]) if target is not None and target == root_verifier else ()
        frames.append(Frame(mode=f["mode"], flags=f["flags"], target=target, exec_gas=f["exec"],
                            state_gas=f["state"], value=f["value"], data_size=len(f["data"]), deadline=deadline,
                            roots=roots))
        data.append(f["data"])
    signatures = []
    for s in t["signatures"]:
        scheme = SCHEMES[s["scheme"]]
        signatures.append(Signature(scheme=scheme, signer=_hex(s["signer"]) if s["signer"] else None,
                                    canonical_msg=not s["msg"],
                                    valid=len(s["signature"]) == SIGNATURE_LENGTH.get(scheme, len(s["signature"])),
                                    length=len(s["signature"]) if scheme == "arbitrary" else 0))
        data += [s["signer"], s["msg"], s["signature"]]
    data.append(_rlp_list([_rlp_int(k) for k in keys]) + _rlp_int(t["nonce_seq"]))
    claim = _claim(t, keys, frame_cfg, codes or {}, raw, cfg.envelope) if frame_cfg.claims else None
    return FrameTx(sender=_hex(t["sender"]), frames=tuple(frames), nonce_keys=tuple(keys),
                   nonce_seq=t["nonce_seq"], signatures=tuple(signatures), max_fee=t["max_fee"], tip=t["tip"],
                   size=len(raw), label=tx_hash(raw), zero_bytes=sum(d.count(0) for d in data), claim=claim)


def bound_template(cfg: FramePoolConfig) -> tuple[int, bytes] | None:
    """CG-1's `bound_template` as CG-10 reads it, or None while the profile names none."""
    if cfg.bound_template_length is None or cfg.bound_template_keccak is None:
        return None
    return cfg.bound_template_length, bytes.fromhex(cfg.bound_template_keccak[2:])


def ticket(t: dict, keys: list[int], codes: dict[bytes, bytes], frame_cfg: FramePoolConfig, raw: bytes,
           envelope: str):
    """CG-10's claim of a decoded transaction as (epoch, salt, binder, issuer), with CG-9's and CG-12's verdicts,
    or None if no frame carries a ticket."""
    frames = [TicketFrame(f["mode"], f["target"] or t["sender"], f["data"]) for f in t["frames"]]
    found = carried(TicketClaim(t["chain_id"], 0, t["sender"], t["nonce_seq"], tuple(keys), b""), frames, codes,
                    bound_template(frame_cfg))
    if found is None:
        return None
    (epoch, salt, binder, issuer), ok = found
    signatures = [TxSignature(s["scheme"], s["signer"], s["msg"], s["signature"]) for s in t["signatures"]]
    is_bound = binder is not None and bound(binder, t["sender"], signatures, sig_hash(raw, envelope))
    return (epoch, salt, binder, issuer), ok, is_bound


def _claim(t: dict, keys: list[int], frame_cfg: FramePoolConfig, codes: dict[str, bytes], raw: bytes,
           envelope: str) -> Claim | None:
    """SF-3's `claim`: CG-10's, from the code of each frame's target, with CG-12's verdict over the bytes received."""
    found = ticket(t, keys, {bytes.fromhex(a[2:]): code for a, code in codes.items()}, frame_cfg, raw, envelope)
    if found is None:
        return None
    (epoch, salt, binder, _), ok, is_bound = found
    return Claim(sender=_hex(t["sender"]), nonce_seq=t["nonce_seq"], epoch=epoch or 0, nonce_keys=tuple(keys),
                 valid=ok, salt="" if salt is None else _hex(salt), binder="" if binder is None else _hex(binder),
                 bound=is_bound)


def _roots(data: bytes) -> tuple[tuple[str, int, str], ...]:
    """SF-3: a recent-root verifier frame's tuples, `source_id(32) || uint64_be(slot) || root(32)` (RR-1)."""
    if len(data) % 72:
        return ()
    return tuple((_hex(data[i:i + 32]), int.from_bytes(data[i + 32:i + 40], "big"), _hex(data[i + 40:i + 72]))
                 for i in range(0, len(data), 72))


def tx_hash(raw: bytes) -> str:
    """SF-3: the chain's hash, keccak256 of the bytes received."""
    return _hex(keccak256(raw))


# --- SF-4 ---------------------------------------------------------------------------

VERDICTS = {
    "BannedOpcode": E.ErrFrameBannedOpcode,
    "StateWriteOutsideDeploy": E.ErrFrameStateWrite,
    "StorageReadNonSender": E.ErrFrameStorageReadNonSender,
    "CallToNonexistentOrDelegated": E.ErrFrameCallTarget,
    "DeployInstalledNoCode": E.ErrFrameDeployNoCode,
    "validation prefix frame reverted": E.ErrFramePrefixReverted,
    "validation prefix did not establish a payer": E.ErrFrameMissingApprove,
    "frame signature list does not authenticate the sender": E.ErrInvalidSender,
}
_NAMED = re.compile(r"^([A-Za-z]+)\(.*\)$", re.S)


def verdict(answer: dict) -> str:
    """SF-4: a client's answer, `{"valid": ..., "violation": ...}`, as a verdict."""
    if answer.get("valid") is True:
        return E.OK
    text = answer.get("violation") or ""
    named = _NAMED.match(text)
    return VERDICTS.get(named.group(1) if named else text, E.ErrFrameClientRefused)


# --- SF-5 to SF-9 ---------------------------------------------------------------------

class Surface:
    """A node's surface: its pool, its peers, and what it asked, relayed and handed on."""

    def __init__(self, pool: TxPool, cfg: SurfaceConfig, peers: list[str] = (), codes: dict[str, bytes] | None = None):
        self.pool, self.cfg, self.peers = pool, cfg, list(peers)
        self.codes = codes or {}  # SF-3's `claim`: the client's code at the head, by address
        self.known: dict[str, set[str]] = {}  # SF-6: by hash, the peers known to have it
        self.by_hash: dict[str, FrameTx] = {}  # chain hash to model transaction, for what the pool may hold
        self.handed: list[str] = []  # SF-9: the hashes handed to the client, in order

    def _admit(self, raw: bytes, answer: dict | None, now: float) -> tuple[str, str | None, bool]:
        """SF-2, FP-2 to FP-7, SF-4 and `add`: the result, the hash if the bytes decode, whether the client was asked."""
        try:
            tx = decode(raw, self.pool.frame.config, self.cfg, self.codes)
        except TxError as err:
            return err.code, None, False
        h = tx.label  # the model's hash covers the label, so FP-2 refuses the same bytes twice
        try:
            self.pool.frame.before_prefix(tx)
        except TxError as err:
            return err.code, h, False
        if answer is None:
            raise ValueError(f"the client would be asked about {h} and no answer was given")
        tx = replace(tx, verdict=verdict(answer))
        result = self.pool.add([tx], now)[0]
        if result == E.OK:
            self.by_hash[h] = tx
            if self.cfg.handoff:
                self.handed.append(h)
        return result, h, True

    def _relay(self, h: str, source: str | None) -> list[str]:
        """SF-6: every peer not known to have it, never the one it came from."""
        known = self.known.setdefault(h, set())
        if source is not None:
            known.add(source)
        out = sorted(p for p in self.peers if p not in known)
        known.update(out)
        return out

    def rpc(self, param, answer: dict | None = None, now: float = 0) -> dict:
        """SF-5."""
        if not isinstance(param, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", param):
            return {"error_code": INVALID_PARAMS, "asked_client": False, "relay_to": [], "handed": False}
        result, h, asked = self._admit(bytes.fromhex(param[2:]), answer, now)
        out = {"result": result, "asked_client": asked, "handed": result == E.OK and self.cfg.handoff}
        if result == E.OK:
            out["hash"] = h
            out["relay_to"] = self._relay(h, None)
        else:
            out["error_code"] = SERVER_ERROR
            out["relay_to"] = []
        return out

    def peer(self, raw_hex: str, source: str, answer: dict | None = None, now: float = 0) -> dict:
        """SF-7."""
        result, h, asked = self._admit(bytes.fromhex(raw_hex[2:]), answer, now)
        if h is not None:
            self.known.setdefault(h, set()).add(source)
        at_fault = result in (E.ErrTxTypeNotSupported, E.ErrFrameDecode)
        gossip = "accept" if result == E.OK else "reject" if at_fault else "ignore"
        return {"result": result, "gossip": gossip, "disconnect": at_fault, "asked_client": asked,
                "relay_to": self._relay(h, source) if result == E.OK else [],
                "handed": result == E.OK and self.cfg.handoff}

    def pending(self) -> list[str]:
        """The chain's hashes of what the pool holds, in the order admitted."""
        held = {tx.hash for txs in self.pool.frame.content().values() for tx in txs}
        return [h for h, tx in self.by_hash.items() if tx.hash in held]

    def to_ask(self, state: State) -> list[str]:
        """SF-8 steps 1 and 2: the pending transactions the new state does not show included."""
        return [h for h in self.pending()
                if not any(state.nonce_seq(self.by_hash[h].sender, k) > self.by_hash[h].nonce_seq
                           for k in self.by_hash[h].nonce_keys)]

    def head(self, head: Head, state: State, answers: dict[str, dict], now: float = 0) -> list[str]:
        """SF-8: ask about what is still pending, then reset; returns the hashes asked about."""
        asked = self.to_ask(state)
        missing = [h for h in asked if h not in answers]
        if missing:
            raise ValueError(f"the client would be asked about {missing} and no answer was given")
        self.pool.reset(head, state, now, {self.by_hash[h].hash: verdict(answers[h]) for h in asked})
        return asked
