"""FP-1: the `eip-8141` and `hegota-testnet` profiles; MA-1: the `matcha` proposal; AG-1: `eip-8288`;
RR-1: `eip-8272`; EN-1: `eip-8266`; CG-1: the `claim-gated` proposal; AG-1 also `eip-8288-master`."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

PRECOMPILES = frozenset(["0x%040x" % i for i in range(0x01, 0x12)] + ["0x%040x" % 0x100])

EXPIRY_VERIFIER_MASTER = "0x81413f0cF12e9b6a49B1D0439E081c577D57FfFf"
EXPIRY_VERIFIER_TESTNET = "0x0000000000000000000000000000000000008141"
RECENT_ROOT_ADDRESS = "0x0000000000000000000000000000000000008272"
EXPIRING_KEY = 2**256 - 1


@dataclass(frozen=True)
class FramePoolConfig:
    name: str = "eip-8141"
    max_verify_gas: int = 100_000
    max_verify_state_gas: int | None = 500_000
    max_pending_noncanonical: int = 1
    cap_codeless_payers: bool = False
    per_sender: str = "one"
    expiry_verifier: str = EXPIRY_VERIFIER_MASTER
    price_bump: int = 10
    price_limit: int = 1
    max_pending: int = 4096
    canonical_paymaster_code: str = "canonical-paymaster"
    expiry_verifier_code: str = "expiry-verifier"
    precompiles: frozenset[str] = field(default=PRECOMPILES)
    reuse_balance: bool = False  # FP-15 step 3, or MA-9 under "matcha"
    evict_first: str = "expiry"  # FP-14: "expiry", the EIP's order, or "tip"
    expiry_margin: int = 0  # FP-8, FP-15 step 2: seconds added to the head's timestamp
    static_first: bool = False  # Admission: FP-11 and FP-12 before FP-8
    # MA-1, read only when per_sender is "matcha"
    width_cap: int = 2**24
    safety_factor: int | float = 2
    lifetime: float = 10800
    load_price: int = 0  # MA-13: the floor, in wei, for the first additional transaction; 0 turns it off
    contention: str = "sender"  # MA-14: what a class is, "sender", "storage" or "slot"
    # AG-1, read only when dependency_frames is true
    dependency_frames: bool = False
    dep_frame_mode: int = 3  # DEP_VERIFY_FRAME_MODE: 3 at the pinned commit, 4 on master
    leanstark: str = "defined"  # or "reserved", as on master (AG-2)
    dep_in_batch: bool = True  # whether a dependency frame may follow a frame with ATOMIC_BATCH_FLAG (AG-2)
    zero_data_hash: str = "literal"  # or "sig_hash": a zero data_hash stands for the signature hash (AG-4)
    mode_1_union: bool = False  # whether AG-5 checks a mode 1 wrapper's deps against its transactions
    max_dependencies_per_frame: int = 256
    max_sigs_per_tx: int = 16
    max_starks_per_tx: int = 1
    max_sig_deps_per_wrapper: int = 16
    max_stark_deps_per_wrapper: int = 1
    aggregation_interval: float = 1.0  # seconds; read by the network, not the pool
    cap_aggregates: bool = True
    forward_wrappers: bool = False
    # AG-9: ms; a budget of None bounds nothing
    proving_budget: float | None = None
    prove_base: float = 0
    prove_recursive: float = 0
    prove_sig: float = 0
    prove_stark: float = 0
    # AG-10: MiB; a budget of None bounds nothing
    memory_budget: float | None = None
    memory_base: float = 0
    memory_recursive: float = 0
    memory_sig: float = 0
    memory_stark: float = 0
    # RR-1, read only when recent_roots is true
    recent_roots: bool = False
    recent_root_address: str = RECENT_ROOT_ADDRESS
    recent_root_code: str = "recent-root"
    recent_root_length: int = 8192
    max_recent_root_references: int = 16
    root_margin: int = 0  # RR-5: slots before its eviction within which a reference is refused
    # EN-1, read only when expiring is true
    expiring: bool = False
    expiring_key: int = EXPIRING_KEY
    nonce_ring: str = "nonce-ring"  # EN-2: the account whose storage holds seen(h)
    max_expiry_secs: int = 60
    expiring_nonce_gas: int = 13_000
    expiring_per_sender: str = "many"  # EN-6: "many", the EIP's MAY, or "one", FP-12 as for any transaction
    # CG-1, read only when claims is true
    claims: bool = False
    claim_epoch: int = 384  # seconds; a head's epoch is its timestamp divided by this
    claim_memory: str = "slot"  # CG-4: "slot" (R3), "claim" (its variant) or "none"
    signed_proofs: bool = False  # CG-3: whether a sender's signature covers its wrapper's proofs
    verifies: bool = True  # CG-7: false makes the node a relay, which verifies no proof
    bond: bool = False  # CG-11: a bond on the ticket paymaster, with AM-1's stake and reputation parameters below
    binding: bool = False  # CG-12: a claim must be bound to its transaction by its binder's signature
    bound_template_length: int | None = None  # CG-10: the bound template's length and keccak256, or none
    bound_template_keccak: str | None = None
    # 14-erc-8421.md, AM-1, read when ruleset is "erc-8421", and the stake and reputation ones under `bond` (CG-11);
    # a descriptor sets them (13-descriptors.md, DS-6)
    ruleset: str = "eip-8141"
    max_verify_gas_per_entity: int = 100_000
    max_verify_gas_staked_entity: int = 1_000_000
    min_stake_value: int = 10**18
    min_unstake_delay: int = 86400
    min_inclusion_rate_denominator: int = 10
    throttling_slack: int = 10
    ban_slack: int = 50
    refresh_seconds: int = 3600
    throttled_entity_mempool_count: int = 4
    throttled_entity_live_blocks: int = 10  # not modelled
    throttled_entity_block_count: int = 4  # not modelled
    same_unstaked_entity_mempool_count: int = 10
    max_txs_allowed_unstaked_entity: int = 10000
    same_nonce_key_mempool_count: int = 4
    same_sender_mempool_count: int = 64

    def with_(self, **changes) -> FramePoolConfig:
        return replace(self, **changes)


EIP_8141 = FramePoolConfig()

HEGOTA_TESTNET = FramePoolConfig(
    name="hegota-testnet",
    max_verify_gas=500_000,
    max_verify_state_gas=None,
    cap_codeless_payers=True,
    per_sender="disjoint-keys",
    expiry_verifier=EXPIRY_VERIFIER_TESTNET,
    recent_roots=True,  # RR-1's hegota-testnet column: the testnet runs EIP-8272, at eip-8272's constants
)

MATCHA = FramePoolConfig(name="matcha", per_sender="matcha", reuse_balance=True)

EIP_8288 = FramePoolConfig(name="eip-8288", dependency_frames=True)

EIP_8288_MASTER = EIP_8288.with_(name="eip-8288-master", dep_frame_mode=4, leanstark="reserved", dep_in_batch=False,
                                 zero_data_hash="sig_hash", mode_1_union=True)  # AG-1, decision record 0063

EIP_8272 = FramePoolConfig(name="eip-8272", recent_roots=True)

EIP_8266 = FramePoolConfig(name="eip-8266", expiring=True)

# CG-1: the bound template is exp-frames experiment 48's (10-claim-gated-admission.md version 7)
CLAIM_GATED = EIP_8288.with_(name="claim-gated", claims=True, bond=True, binding=True, bound_template_length=1185,
                             bound_template_keccak="0x52c656815e560bb189c3fb362c9628432ca1ed6b720e239857775236c18bc1d3")

PROFILES = {c.name: c for c in (EIP_8141, HEGOTA_TESTNET, MATCHA, EIP_8288, EIP_8288_MASTER, EIP_8272, EIP_8266,
                                 CLAIM_GATED)}
