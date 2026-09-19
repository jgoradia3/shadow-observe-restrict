# Design and limitations

## System model

The reference implementation models an authorization request as an exact `(subject, action, resource)` tuple. It includes:

- a stable policy currently in force;
- a candidate policy proposed for reduction;
- a generator-defined set of required permissions used only by the synthetic evaluation workload;
- shadow comparison between stable and candidate decisions;
- promotion gates;
- bounded candidate enforcement; and
- rollback/convergence behavior across simulated authorization nodes.

## Example policies

The small local example uses four synthetic service identities and eight stable entitlements.

- `policy_stable.json` contains eight entitlements.
- `policy_required.json` contains seven generator-defined required entitlements.
- `policy_candidate_lower_risk.json` removes the one deliberately injected redundant entitlement.
- `policy_candidate_over_aggressive.json` removes three permissions, including permissions exercised by required synthetic requests.

The required-policy file is an evaluation aid, not a production source of truth. In real deployments, whether access is required would need to be established from workload semantics, ownership, business context, explicit policy, and/or human validation.

## Promotion logic

The controlled replay uses a fixed observation prefix and three gate signals:

1. stable/candidate mismatch rate;
2. candidate denials of requests marked required by the synthetic workload; and
3. candidate permission expansions.

These are demonstration parameters. SOR does not prescribe universal thresholds.

## Distributed rollback

The distributed simulator models three nodes receiving candidate and restoration state at different times. Stable authorization remains enforced during shadow evaluation. The simulation is intended to illustrate a practical distinction: a rollback command is not the same as completed rollback across all enforcement points.

## Claim boundary

This repository demonstrates mechanism behavior under controlled synthetic conditions. It does **not**:

- reproduce a production enterprise IAM environment;
- prove that unobserved permissions are globally redundant;
- infer business necessity from access frequency alone;
- validate provider-specific policy translation;
- model every network, controller, cache, or Byzantine failure mode;
- establish production throughput or availability; or
- claim that the example thresholds are appropriate for other environments.

The reference implementation should therefore be read as an operational rollout pattern and executable example, not a production-ready authorization system.
