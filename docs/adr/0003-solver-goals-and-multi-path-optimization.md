# 3. Solver Goals and Multi-Path Process Optimization

Date: 2026-07-28

## Status

Accepted

## Context

Previously, `RecipeSolver` selected the first matching producer process for each resource demand using a deterministic linear lookup (`find_producer`). If multiple processes could produce the same resource (forks in recipe execution), `RecipeSolver` had no mechanism to evaluate alternative process paths or optimize for specific criteria (such as lowest cost or fastest duration).

Users require the ability to specify optimization goals when solving queries (e.g., finding the cheapest or fastest sequence of processes to produce target outputs). In addition, the design must accommodate future user-defined custom tag metrics (e.g., minimizing baking time or manual labor) without requiring structural rewrites of the solver search engine.

## Decision

1. **DSL Syntax & Query Tag Representation**:
   - Solver goals are declared using tag syntax on query statements, e.g., `[cheapest] make 1 kg cake;` or `[cheapest, fastest] make 1 kg cake;`.
   - Multiple goals form an ordered tie-breaking cascade evaluated left-to-right.
   - If omitted, query goals default to `[any]` (equivalent to legacy behavior).
   - In programs with multiple query statements, the last explicitly declared goal cascade overrides preceding ones when queries are combined.

2. **Metric Definitions**:
   - `cheapest`: Minimizes `total_cost` (`resource_cost` + `process_cost`).
   - `fastest`: Minimizes `total_time` (sum of process durations scaled by process scale factors).
   - `any`: Returns `0.0` (constant score, picking the first valid DAG found).

3. **Multi-Path Search & Cycle Pruning**:
   - `RecipeSolver` recursively explores candidate producer choices at forks in the process graph.
   - Active ancestor paths are tracked in a `temp_visited` set. Any candidate path containing a cycle is pruned/discarded.
   - Shared intermediate nodes in DAGs (fan-in dependencies) are supported and properly scaled.
   - If candidate DAGs tie on all specified goal scores, tie-breaking settles deterministically using the sorted tuple of process names in each DAG.

4. **Extensible Score Calculator Architecture**:
   - Goal evaluation is encapsulated in `evaluate_goal(proc_scales, basic_demands, goal) -> float`.
   - Candidate DAGs are ranked by comparing score tuples `(eval(DAG, g1), eval(DAG, g2), ...)` lexicographically.
   - Future custom quantity tags (e.g. `[min: manual_labour]`) can be added directly by extending `evaluate_goal` to compute tag sums across candidate DAGs without modifying solver search or tie-breaking logic.

## Consequences

- Queries can optimize for cost, speed, or tie-breaking cascades.
- Multi-path process graphs with alternative production recipes are correctly evaluated and selected.
- Cycle detection cleanly prunes looping paths without crashing the solver when valid alternative paths exist.
- Future custom tag-based optimization goals can be added with zero churn to the solver core.
