//! How much memory leanVM takes to prove one aggregate, against what the aggregate
//! holds (the plan's item 32, decision record 0041). Built as an example of leanVM's
//! `leanvm-cli` package by `bench/leanvm-memory/run.sh`, which copies this file into
//! the checkout; it is not part of leanVM.
//!
//! One subject a process, so that nothing an earlier subject allocated is counted:
//!
//! - `memory recursive N PER_LEAF`: N leaf aggregates of PER_LEAF leanSPHINCS
//!   signatures each are made first, the recursive inputs an aggregate takes from
//!   its peers; then one aggregate over the N of them is proved.
//! - `memory sphincs N`: one aggregate over N leanSPHINCS signatures, verified
//!   directly.
//!
//! Before the aggregate is proved, the process's peak resident set is reset
//! (`/proc/self/clear_refs`, 5), so the peak printed is the aggregate's own, over
//! whatever the process already held, which is printed too. The aggregate is proved
//! once after one warmup, the warmup's own peak included, since leanVM's caches are
//! what a node that proves every interval keeps.
//!
//! Output is ASCII, for `bench/leanvm-memory/fit.py`.

#[global_allocator]
static ALLOCATOR: bench::Jemalloc = bench::Jemalloc;

use rec_aggregation::{EthereumProof, aggregate, aggregate_with_stats, signers_cache};
use std::time::Instant;

const LOG_INV_RATE: usize = 1;
const WARMUP: usize = 1;

fn status_kib(field: &str) -> u64 {
    let status = std::fs::read_to_string("/proc/self/status").unwrap();
    let line = status.lines().find(|l| l.starts_with(field)).unwrap();
    line.split_whitespace().nth(1).unwrap().parse().unwrap()
}

fn reset_peak() {
    std::fs::write("/proc/self/clear_refs", "5").expect("the peak resets");
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let kind = args.get(1).expect("recursive or sphincs").as_str();
    let n: usize = args.get(2).expect("N").parse().expect("N is a count");
    let per_leaf: usize = args.get(3).map_or(1, |s| s.parse().expect("PER_LEAF is a count"));
    leanvm_core::init_prover();
    rec_aggregation::warm_up();

    let (children, sphincs) = match kind {
        "recursive" => {
            assert!((1..=rec_aggregation::MAX_RECURSIONS).contains(&n), "1 to MAX_RECURSIONS children");
            let signers = signers_cache::get_sphincs_signers(n * per_leaf);
            let children: Vec<EthereumProof> = (0..n)
                .map(|k| {
                    aggregate(&[], vec![], signers[k * per_leaf..(k + 1) * per_leaf].to_vec(), &[], None, LOG_INV_RATE)
                        .expect("a leaf aggregates")
                })
                .collect();
            (children, vec![])
        }
        "sphincs" => (vec![], signers_cache::get_sphincs_signers(n)[..n].to_vec()),
        _ => panic!("recursive or sphincs"),
    };

    println!();
    println!("subject: {kind} n={n} per_leaf={}", if kind == "recursive" { per_leaf } else { 0 });
    println!("  kind: {kind}");
    println!("  n: {n}");
    println!("  per leaf: {}", if kind == "recursive" { per_leaf } else { 0 });
    reset_peak();
    println!("  held kib: {}", status_kib("VmRSS:"));
    let mut proved = None;
    for rep in 0..=WARMUP {
        let started = Instant::now();
        let (proof, stats) =
            aggregate_with_stats(&children, vec![], sphincs.clone(), &[], None, LOG_INV_RATE).expect("it aggregates");
        if rep == WARMUP {
            println!("  prove ms: {:.3}", started.elapsed().as_secs_f64() * 1000.0);
            println!("  cycles: {}", stats.cycles);
            proved = Some(proof);
        }
    }
    println!("  peak kib: {}", status_kib("VmHWM:"));
    let proof = proved.unwrap();
    println!("  proof bytes: {}", proof.to_bytes().len());
    proof.verify().expect("the aggregate verifies");
    println!("  verified: yes");
}
