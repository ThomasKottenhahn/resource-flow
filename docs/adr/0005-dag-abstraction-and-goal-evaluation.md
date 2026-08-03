# ADR 0005 — DAG Abstraction, Goal Evaluation, and Visualizer Separation

## Status

Accepted

## Context

`RecipeSolver` was a god class responsible for:
- Graph search (backtracking over candidate process combinations)
- Scale calculation (backward demand propagation)
- Goal evaluation (cheapest, fastest, relational constraints, custom tag metrics)
- Metric computation
- Plan formatting (text execution plan)
- Mermaid diagram rendering

This made the class large, hard to extend, and tightly coupled. Adding a new goal type required modifying the solver. The visualization logic accessed solver state directly and could not be reused independently.

## Decision

Decompose `RecipeSolver` into four focused abstractions:

### 1. `DAG` (`resource_flow/dag.py`)

A graph value object representing a solved candidate process graph:
- `DAGNode`: process + scale factor
- `DAGEdge`: directed resource flow between processes (or from basic inputs / to query)
- `DAG.calculate_metric(tag: str, unit: str | None = None) -> float`: evaluates cost, time, custom quantitative tags, and flag tag counts directly from graph structure

`DAG` is the unit that goals evaluate and that the solver returns.

### 2. `Goal` hierarchy (`resource_flow/models.py`)

Abstract base class `Goal` with `evaluate(dag: DAG) -> float | bool`:
- `AggregateGoal(op, tag)`: returns float score (`dag.calculate_metric(tag)`, negated for `max`)
- `RelationalGoal(tag, op, val, unit)`: returns bool pass/fail
- `AnyGoal`: always returns `0.0`

`Query` normalizes string aliases (`"cheapest"`, `"fastest"`, `"any"`, custom tag names) into `Goal` instances on construction.

### 3. `RecipeSolver` (`resource_flow/solver.py`)

Retains: graph search, scale calculation, goal dispatch. Returns `DAG` from `solve()`.

`solve() -> DAG`: builds candidate `DAG` objects, filters by `RelationalGoal.evaluate(dag)`, ranks by `AggregateGoal.evaluate(dag)`, returns the optimal `DAG`.

The solver retains `demands`, `surplus`, and `basic_resources` as query execution context (not part of `DAG`, since multiple solver configurations can solve the same graph).

### 4. `Visualizer` (`resource_flow/visualization.py`)

Class initialized with a result `DAG` plus solver context (`demands`, `surplus`, `basic_resources`, `query`). Provides `print_plan()`, `generate_mermaid()`, `get_metrics()` without performing any graph computation.

## Consequences

- Goal types can be added by subclassing `Goal` without touching `RecipeSolver`.
- `DAG` is a standalone value object usable outside the solver.
- `Visualizer` is reusable and independently testable.
- Backward-compatible: `RecipeSolver.print_plan()` and `generate_mermaid()` delegate to `Visualizer`; `DAG` supports dict-like subscript on `process_scales` for legacy callers.

## Alternatives Considered

- Keep everything in `RecipeSolver` with added methods: rejected because it compounds the god-class problem.
- Put metric calculation in `RecipeSolver`: rejected because goals then need access to solver state, coupling them tightly.
