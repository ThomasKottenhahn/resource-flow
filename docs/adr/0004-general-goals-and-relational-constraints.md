# 4. General Goals and Relational Constraints

Date: 2026-08-03

## Status

Accepted

## Context

ADR 0003 introduced basic solver goals (`cheapest`, `fastest`, `any`) for optimizing recipe process graph selection. However, users require generalized optimization goals on arbitrary tags (e.g. `min manual_labour`, `max throughput`) as well as relational constraints (e.g. `cost <= 10`, `time <= 30 min`, `manual_labour == 0`).

The goal engine needs a unified grammar, metric calculation model, and failure reporting mechanism for both aggregate optimizations and relational constraints.

## Decision

1. **DSL Syntax & Backward Compatibility**:
   - Aggregate goals use `min <tag>` or `max <tag>` syntax (e.g. `[min cost]`, `[max manual_labour]`).
   - Relational constraint goals use `<tag> <rel_op> <value>` syntax (e.g. `[cost <= 10]`, `[time < 30 min]`). Supported operators: `<=`, `<`, `>=`, `>`, `==`, `!=`.
   - `cheapest` remains supported as an internal shorthand alias for `min cost`.
   - `fastest` remains supported as an internal shorthand alias for `min time`.

2. **Relational Constraint Evaluation & Infeasibility Handling**:
   - Relational goals act as hard filters. Candidate DAGs violating any relational constraint are rejected.
   - If no candidate DAG satisfies all relational constraints, `RecipeSolver` returns no solution. The solver reports an informative message detailing the closest metric value achieved by any candidate DAG (e.g., `No solution found for manual_labour == 0. Closest solution found: manual_labour = 1`).

3. **Tag Metric Evaluation Rules**:
   - **Built-in quantitative tags** (`cost`, `time`): Computed using process scale factors $s$ and normalized basic resource quantities.
   - **Custom quantitative key-value tags** (e.g. `[co2: 5 kg]`): Summed across processes and basic resources in the candidate DAG, scaled by process scale factors $s$ and basic resource quantities.
   - **Non-quantitative flag tags** (e.g. `[manual_labour]`): Computed using discrete counts (1 point per process and 1 point per basic resource in the candidate DAG carrying the tag).

4. **Unit Conversion**:
   - Relational constraints can specify values with optional units (e.g. `[time <= 30 min]`).
   - Metric values and constraint thresholds are automatically converted to matching standard base units (`s` for time, `g` for mass, `ml` for volume) prior to comparison.

## Consequences

- Queries can express rich optimization objectives and bounds across arbitrary process and resource tags.
- Infeasible constraint queries provide clear diagnostic output identifying the closest candidate metric.
- Discrete flag counting and scaled kv tag metrics provide predictable and flexible domain modeling options.
