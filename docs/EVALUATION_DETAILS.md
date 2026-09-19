# Controlled evaluation details

This document contains the detailed supporting results intentionally kept out of the practitioner article's main narrative.

## Purpose

The experiments exercise the rollout control loop under controlled synthetic workloads. They illustrate mechanism behavior; they are not intended to establish production-scale effectiveness.

## Primary replay

The primary replay uses 50,000 deterministic weighted synthetic requests with seed 2026. The stable policy contains eight entitlements. Seven are marked required by the generator-defined evaluation workload; one is deliberately injected as redundant.

Two candidates are evaluated over the same replay:

- **Over-aggressive candidate:** removes three stable entitlements, including permissions exercised by required synthetic requests.
- **Lower-risk candidate:** removes only the generator-labeled redundant entitlement. The replay still includes low-frequency accesses to that tuple, so policy mismatches can occur without required-request denials.

Aggregate reference output: `results/summary/baseline_comparison.csv`.

### Article-facing observation: blast radius

Under immediate enforcement, the over-aggressive candidate produces 3,036 required-request denials in the 50,000-request controlled replay. Under the configured complete SOR gate, promotion is withheld and the stable policy remains enforced, producing no enforced required-request denials for that candidate.

This comparison illustrates why candidate evaluation before broad enforcement can reduce rollout blast radius. It does not establish that SOR can independently determine which permissions are safe to remove in a production environment.

## Threshold tuning

Aggregate reference output: `results/summary/threshold_sensitivity.csv`.

The lower-risk candidate has an observation mismatch rate of 0.0093 in the fixed replay. A mismatch threshold of 0.005 therefore withholds it even though the synthetic required-request signal records no required would-deny events. Thresholds of 0.010 and above allow it to proceed under the other fixed gates.

The operational lesson is that a promotion gate can be too strict as well as too permissive. Expected permission reductions inherently create stable/candidate differences, so mismatch rate should not be treated as a universal proxy for harm.

## Scale sensitivity

Aggregate outputs:

- `results/summary/scale_sensitivity.csv`
- `results/summary/scale_sensitivity_summary.csv`

The repository includes deterministic generated policy sets at three sizes and three seeds. These runs test whether the same gate implementation behaves consistently as policy cardinality changes. They are not an enterprise-traffic model and are not presented as a scalability benchmark.

## Propagation-delay simulation

Aggregate output: `results/summary/delay_sensitivity.csv`.

A deterministic three-node simulation introduces candidate/restoration state with different propagation delays. Longer delay increases the time during which nodes can observe different evaluator versions; the largest included delay produces temporary decision divergence. The practical point is that rollout and rollback gates should reason about convergence, not only controller state.

## Runtime benchmark

`experiments/benchmark_runtime.py` is retained as an optional local diagnostic. Host-specific timing is deliberately excluded from the article because the prototype is not presented as a production-performance implementation.
