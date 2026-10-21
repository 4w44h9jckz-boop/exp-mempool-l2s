"""Descriptors: a ruleset as a file a node loads, `docs/spec/13-descriptors.md`, DS-1 to DS-7, with the modules of
`14-erc-8421.md`.

A descriptor parses strictly (DS-1), has one canonical encoding (DS-2) and an identifier, the base32 CIDv1 of that
encoding as a raw block (DS-3). Its modules are rules with fixed parameters (DS-4); it inherits its parent's
(DS-5); a complete ruleset (DS-6) compiles to the frame pool profile its modules carry; and a refusal under it
names the module that raised the code and the descriptor (DS-7). Decision record 0060.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass, field

from . import claimticket
from .framepool.config import EIP_8141, FramePoolConfig

MAX_INT = 2**53 - 1
MEMBERS = ("format", "name", "source", "parent", "rules", "remove")


class DescriptorError(Exception):
    """A node's answer when it cannot load a descriptor: a code of 13-descriptors.md, and the module it names."""

    def __init__(self, code: str, rule: str | None = None):
        super().__init__(code if rule is None else f"{code} {rule}")
        self.code, self.rule = code, rule


# --- DS-1 and DS-2 -------------------------------------------------------------------------------------

def _pairs(pairs):
    seen = set()
    for k, _ in pairs:
        if k in seen:
            raise ValueError("a member name twice")
        seen.add(k)
    return dict(pairs)


def _no_float(_text):
    raise ValueError("not an integer")


def _check(v) -> None:
    if v is None or isinstance(v, bool):
        return
    if isinstance(v, int):
        if not 0 <= v <= MAX_INT:
            raise ValueError("integer out of range")
        return
    if isinstance(v, str):
        if any(not 0x20 <= ord(c) <= 0x7E for c in v):
            raise ValueError("not printable ASCII")
        return
    if isinstance(v, list):
        for x in v:
            _check(x)
        return
    if isinstance(v, dict):
        for k, x in v.items():
            _check(k)
            _check(x)
        return
    raise ValueError("not a value DS-1 allows")


def parse(text: str) -> dict:
    """DS-1: the descriptor's value, or ErrDescriptorMalformed."""
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_float=_no_float, parse_constant=_no_float)
        _check(value)
    except ValueError:
        raise DescriptorError("ErrDescriptorMalformed") from None
    if not isinstance(value, dict) or set(value) != set(MEMBERS) or value["format"] != 1 \
            or isinstance(value["format"], bool) or not isinstance(value["name"], str) \
            or not isinstance(value["source"], str) or not (value["parent"] is None or isinstance(value["parent"], str)) \
            or not isinstance(value["rules"], dict) or not all(isinstance(p, dict) for p in value["rules"].values()) \
            or not isinstance(value["remove"], list) or not all(isinstance(r, str) for r in value["remove"]):
        raise DescriptorError("ErrDescriptorMalformed")
    return value


def canonical(value) -> str:
    """DS-2: sorted members, no whitespace, only quote and backslash escaped (the value holds printable ASCII)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def identifier(value) -> str:
    """DS-3: "b" and the base32 CIDv1 (raw, sha2-256) of the canonical encoding."""
    digest = hashlib.sha256(canonical(value).encode("ascii")).digest()
    return "b" + base64.b32encode(bytes([0x01, 0x55, 0x12, 0x20]) + digest).decode("ascii").lower().rstrip("=")


# --- DS-4: the modules ----------------------------------------------------------------------------------

INT, INT_OR_NULL, BOOL, STR, STRS, AMOUNT = "int", "int|null", "bool", "str", "str[]", "amount"


@dataclass(frozen=True)
class Module:
    params: dict = field(default_factory=dict)  # name -> type, or a tuple of allowed strings
    kind: str = "rule"  # "core" or "rule"
    codes: tuple[str, ...] = ()  # what it refuses with, from its document's Errors table


def _m(kind="rule", codes=(), **params) -> Module:
    return Module(params, kind, tuple(codes))


FRAME_POOL = {
    "FP-2": _m("core", ["ErrAlreadyKnown"]),
    "FP-3": _m("core", ["ErrFrameMalformed", "ErrGasLimitTooHigh", "ErrInvalidSender", "ErrTipAboveFeeCap",
                        "ErrTxGasPriceTooLow", "ErrGasLimit"], price_limit=INT),
    "FP-4": _m("core"),
    "FP-5": _m("rule", ["ErrFrameExpiryNotFirst", "ErrFrameNoPayer", "ErrFrameAtomicInPrefix",
                        "ErrFrameUnrecognizedPrefix", "ErrFrameVerifyAfterPrefix"], expiry_verifier=STR),
    "FP-6": _m("rule", ["ErrFrameVerifyGas", "ErrFrameVerifyStateGas"], max_verify_gas=INT,
               max_verify_state_gas=INT_OR_NULL),
    "FP-7": _m("rule", ["ErrNonceTooLow", "ErrNonceTooHigh"]),
    "FP-8": _m("core", ["ErrFrameExpired", "ErrFramePrefixReverted", "ErrFrameMissingApprove", "ErrFrameDeployNoCode",
                        "ErrInsufficientFunds"], expiry_margin=INT, expiry_verifier_code=STR),
    "FP-9": _m("rule", ["ErrFrameBannedOpcode", "ErrFrameStateWrite", "ErrFrameStorageReadNonSender",
                        "ErrFrameCallTarget"], canonical_paymaster_code=STR, precompiles=STRS),
    "FP-10": _m("core"),
    "FP-11": _m("rule", ["ErrFramePayerExposure", "ErrFramePaymasterBusy"], max_pending_noncanonical=INT,
                cap_codeless_payers=BOOL),
    "FP-12": _m("rule", ["ErrReplaceUnderpriced", "ErrFrameSenderBusy"], per_sender=("one", "disjoint-keys"),
                price_bump=INT),
    "FP-13": _m("core", ["ErrAlreadyReserved"]),
    "FP-14": _m("core", ["ErrTxPoolOverflow"], max_pending=INT, evict_first=("expiry", "tip")),
    "FP-15": _m("core", reuse_balance=BOOL),
    "FP-16": _m("core"),
}
AGGREGATION = {
    "AG-2": _m("rule", ["ErrDepFrameMalformed"], max_dependencies_per_frame=INT),
    "AG-3": _m(),
    "AG-4": _m("rule", ["ErrFrameTooManyDeps"], max_sigs_per_tx=INT, max_starks_per_tx=INT),
    "AG-5": _m("rule", ["ErrWrapperMalformed", "ErrWrapperUnknownTx", "ErrWrapperDeps", "ErrWrapperTooManyDeps",
                        "ErrWrapperProof"], max_sig_deps_per_wrapper=INT, max_stark_deps_per_wrapper=INT),
    "AG-6": _m("rule", ["ErrFrameDepsUnproven"]),
    "AG-7": _m("rule", aggregation_interval_ms=INT, cap_aggregates=BOOL, forward_wrappers=BOOL),
    "AG-8": _m(),
}
CLAIMS = {
    "CG-2": _m("rule", ["ErrClaimMissing", "ErrClaimInvalid", "ErrClaimWrongSlot", "ErrClaimEpoch"], claim_epoch=INT),
    "CG-3": _m("rule", ["ErrProofUnsigned"], signed_proofs=BOOL),
    "CG-4": _m("rule", ["ErrSlotRefused", "ErrClaimRefused"], claim_memory=("slot", "claim", "none")),
    "CG-5": _m("rule", ["ErrClaimUsed"]),
    "CG-6": _m("rule", ["ErrClaimExpired"]),
    "CG-7": _m("rule", ["ErrRelayAggregate"], verifies=BOOL),
    "CG-8": _m("rule", namespace=(claimticket.NAMESPACE.decode("ascii"),)),
    "CG-9": _m(),
    "CG-10": _m("rule", template_length=(claimticket.TEMPLATE_LENGTH,),
                template_keccak=("0x" + claimticket.TEMPLATE_KECCAK.hex(),)),
}
_ERC_CODES = {
    "PREFIX-010": ["ErrFrameExpiryNotFirst", "ErrFrameNoPayer", "ErrFrameUnrecognizedPrefix"],
    "PREFIX-020": ["ErrFrameDeployNoCode"], "PREFIX-040": ["ErrFrameAtomicInPrefix"],
    "PREFIX-050": ["ErrFrameVerifyAfterPrefix"],
    "PREFIX-060": ["ErrFramePrefixReverted", "ErrFrameMissingApprove", "ErrInsufficientFunds"],
    "PREFIX-080": ["ErrFrameExpired"], "PREFIX-110": ["ErrFramePreVerifyNoCode"],
    "PREFIX-120": ["ErrFrameStrayDefault"], "BUDGET-010": ["ErrEntityVerifyGas"], "SIGNATURE-010": ["ErrInvalidSender"],
    "OPCODES-010": ["ErrFrameBannedOpcode"], "OPCODES-030": ["ErrFrameUnassignedOpcode"],
    "OPCODES-040": ["ErrFrameOutOfGasRevert"], "CREATION-010": ["ErrFrameCreation"],
    "CALLING-010": ["ErrFrameCallTarget"], "STORAGE-000": ["ErrFrameStorageAccess"],
    "LIFECYCLE-010": ["ErrNonceTooLow", "ErrNonceGap"], "LIFECYCLE-020": ["ErrReplaceUnderpriced"],
    "LIFECYCLE-030": ["ErrNonceKeyLimit", "ErrSenderLimit"], "LOCAL-010": ["ErrEntityIsSender"],
    "LOCAL-020": ["ErrLocalStorage"], "SOLVENCY-010": ["ErrFramePayerExposure"],
    "REPUTATION-010": ["ErrEntityBanned"], "REPUTATION-020": ["ErrEntityThrottled"],
    "REPUTATION-210": ["ErrSenderThrottled"], "REPUTATION-220": ["ErrPayerOpsAllowed"],
}
_ERC_PARAMS = {
    "ASSOC-020": {"max_offset": INT},
    "PREFIX-010": {"expiry_verifier": STR},
    "PREFIX-100": {"canonical_paymaster_code": STR},
    "BUDGET-010": {"max_verify_gas_per_entity": INT, "max_verify_gas_staked_entity": INT},
    "CALLING-040": {"precompiles": STRS},
    "STAKING-010": {"min_stake_value": AMOUNT, "min_unstake_delay": INT, "staking_registry": STR},
    "REPUTATION-010": {"min_inclusion_rate_denominator": INT, "throttling_slack": INT, "ban_slack": INT,
                       "refresh_seconds": INT},
    "REPUTATION-020": {"throttled_entity_mempool_count": INT, "throttled_entity_live_blocks": INT,
                       "throttled_entity_block_count": INT},
    "REPUTATION-220": {"same_unstaked_entity_mempool_count": INT, "max_txs_allowed_unstaked_entity": INT},
    "LIFECYCLE-020": {"price_bump": INT},
    "LIFECYCLE-030": {"same_nonce_key_mempool_count": INT, "same_sender_mempool_count": INT},
}
# 14-erc-8421.md, AM-2: the ruleset's own modules, in the ERC's order
ERC_ORDER = (
    "ASSOC-010", "ASSOC-020", "PREFIX-010", "PREFIX-020", "PREFIX-040", "PREFIX-050", "PREFIX-060", "PREFIX-080",
    "PREFIX-100", "PREFIX-110", "PREFIX-120", "BUDGET-010", "SIGNATURE-010", "OPCODES-010", "OPCODES-020",
    "OPCODES-030", "OPCODES-040", "CREATION-010", "CALLING-010", "CALLING-040", "STORAGE-000", "STORAGE-010",
    "STORAGE-021", "STORAGE-022", "STORAGE-031", "STORAGE-032", "STORAGE-033", "LOCAL-010", "LOCAL-020",
    "STAKING-010", "SOLVENCY-010", "SOLVENCY-020", "SOLVENCY-030", "REPUTATION-010", "REPUTATION-020",
    "REPUTATION-040", "REPUTATION-210", "REPUTATION-220", "REPUTATION-310", "REPUTATION-320", "REPUTATION-330",
    "LIFECYCLE-010", "LIFECYCLE-020", "LIFECYCLE-030", "LIFECYCLE-040", "PROPAGATION-010", "PROPAGATION-020",
    "PROPAGATION-030", "PROPAGATION-040", "PROPAGATION-050",
)
ERC = {name: Module(_ERC_PARAMS.get(name, {}), "rule", tuple(_ERC_CODES.get(name, ()))) for name in ERC_ORDER}
MODULES: dict[str, Module] = {**FRAME_POOL, **AGGREGATION, **CLAIMS, **ERC}
REPLACED = ("FP-5", "FP-6", "FP-7", "FP-9", "FP-11", "FP-12")  # DS-6 step 3, AM-2


def _type_ok(t, v) -> bool:
    if isinstance(t, tuple):
        return v in t and type(v) is type(t[0])
    if t == INT:
        return isinstance(v, int) and not isinstance(v, bool)
    if t == INT_OR_NULL:
        return v is None or (isinstance(v, int) and not isinstance(v, bool))
    if t == BOOL:
        return isinstance(v, bool)
    if t == STR:
        return isinstance(v, str)
    if t == STRS:
        return isinstance(v, list) and all(isinstance(x, str) for x in v)
    if t == AMOUNT:
        return isinstance(v, str) and v.isdigit() and (v == "0" or v[0] != "0")
    raise ValueError(t)


def check_modules(rules: dict) -> None:
    """DS-4, in the byte order of the module names, each name before its parameters."""
    for name in sorted(rules):
        module = MODULES.get(name)
        if module is None:
            raise DescriptorError("ErrDescriptorUnknownRule", name)
        params = rules[name]
        if set(params) != set(module.params) or not all(_type_ok(t, params[p]) for p, t in module.params.items()):
            raise DescriptorError("ErrDescriptorParams", name)


# --- DS-5 and DS-6 --------------------------------------------------------------------------------------

@dataclass
class Descriptor:
    id: str
    value: dict
    effective: dict[str, tuple[dict, str]]  # module -> (parameters, the identifier of the descriptor that set it)

    def rule_of(self, code: str) -> str | None:
        """DS-7: the effective module whose Errors table holds `code`; an ERC-8421 module claims its codes."""
        owner = None
        for name in self.effective:
            if code in MODULES[name].codes:
                if name in ERC:
                    return name
                owner = owner or name
        return owner


def _complete(effective: dict) -> None:
    """DS-6, in its order."""
    for name, m in FRAME_POOL.items():
        if m.kind == "core" and name not in effective:
            raise DescriptorError("ErrDescriptorIncomplete", name)
    erc = any(name in effective for name in ERC)
    if erc:
        for name in ERC_ORDER:
            if name not in effective:
                raise DescriptorError("ErrDescriptorIncomplete", name)
    for name in REPLACED:
        if name in effective and erc:
            raise DescriptorError("ErrDescriptorConflict", name)
        if name not in effective and not erc:
            raise DescriptorError("ErrDescriptorIncomplete", name)
    if erc:
        for name in {**AGGREGATION, **CLAIMS}:
            if name in effective:
                raise DescriptorError("ErrDescriptorConflict", name)
    for family, needs in (("AG", AGGREGATION), ("CG", {**AGGREGATION, **CLAIMS})):
        if any(name.startswith(family + "-") for name in effective):
            for name in needs:
                if name not in effective:
                    raise DescriptorError("ErrDescriptorIncomplete", name)


class Store:
    """The descriptors a node holds, by identifier (DS-5)."""

    def __init__(self):
        self.held: dict[str, Descriptor] = {}

    def load(self, text: str) -> Descriptor:
        """DS-1, the parent, DS-4, the removals, DS-6: the order DS-5 gives. A loaded descriptor is held."""
        value = parse(text)
        return self.load_value(value)

    def load_value(self, value: dict) -> Descriptor:
        parent = None
        if value["parent"] is not None:
            parent = self.held.get(value["parent"])
            if parent is None:
                raise DescriptorError("ErrDescriptorParentUnknown")
        check_modules(value["rules"])
        ident = identifier(value)
        effective = dict(parent.effective) if parent else {}
        for name in value["remove"]:
            if name not in effective:
                raise DescriptorError("ErrDescriptorRemove", name)
            del effective[name]
        for name, params in value["rules"].items():
            effective[name] = (params, ident)
        _complete(effective)
        d = Descriptor(ident, value, effective)
        self.held[ident] = d
        return d


# --- compiling a ruleset to a pool profile (DS-6) ---------------------------------------------------------

_FIELDS = {  # module parameter -> FramePoolConfig field, where the names differ
    ("AG-7", "aggregation_interval_ms"): None,
    ("ASSOC-020", "max_offset"): None, ("STAKING-010", "staking_registry"): None,
    ("CG-8", "namespace"): None, ("CG-10", "template_length"): None, ("CG-10", "template_keccak"): None,
}


def compile_config(d: Descriptor) -> FramePoolConfig:
    """DS-6: the profile a complete ruleset's modules carry, with every parameter set; one no module carries keeps
    the `eip-8141` profile's value."""
    eff = d.effective
    changes: dict = {}
    for name, (params, _) in eff.items():
        for p, v in params.items():
            if (name, p) in _FIELDS:
                continue
            changes[p] = frozenset(v) if p == "precompiles" else v
    if "AG-7" in eff:
        changes["aggregation_interval"] = eff["AG-7"][0]["aggregation_interval_ms"] / 1000
    if "STAKING-010" in eff:
        changes["min_stake_value"] = int(eff["STAKING-010"][0]["min_stake_value"])
    if any(name in eff for name in ERC):
        name = "erc-8421"
        changes["ruleset"] = "erc-8421"
    elif "CG-2" in eff:
        name = "claim-gated"
    elif "AG-2" in eff:
        name = "eip-8288"
    else:
        name = "eip-8141"
    changes["dependency_frames"] = "AG-2" in eff
    changes["claims"] = "CG-2" in eff
    return EIP_8141.with_(name=name, **changes)
