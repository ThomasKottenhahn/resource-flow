# 8. Resource Flow Is a Planner, Not a Scheduler

Date: 2026-11-14

## Status

Accepted. Reverses the timing and scheduling engine (PR #12, `.scratch/timing-scheduling-engine/`).

## Context

PR #12 added a second solver stage that placed processes on a wall-clock timeline. It came with `map` blocks (locations, travel, shopping time), `calendar` blocks (working hours), `hold` and `shelf_life` tags, `[passive]`/`[unsupervised]` execution types, `at`/`starting`/`by` clauses on `make`, a single implicit "user" actor, a non-deterministic constructive heuristic with local search, and a Gantt chart.

In practice, the output of Resource Flow is mostly consumed by machines that do their own scheduling of work blocks. Building a scheduler inside the language duplicated that job, pulled calendars and geography into a recipe language, made results non-deterministic, and made the system feel inconsistent with its core role as a resource calculator.

## Decision

1. Resource Flow answers *what* work is needed to make the queried resources and *how long* each piece takes. It does not decide *when* anything happens.
2. PR #12 is reverted as a whole (`git revert -m 1 ef0fd8b`). That removes the timeline solver, `TimelineSchedule`, the `map` and `calendar` blocks, `hold`/`shelf_life`, execution types, `at`/`starting`/`by` on `make`, the Gantt output, and the `Solver`/`DAGSolver` two-stage split (back to `RecipeSolver`).
3. `--` line comments, which arrived in the same PR, are re-added on their own.
4. The `--json` output is kept as the machine-facing interface, minus its timeline/Gantt sections.

## Consequences

- Solving is a single deterministic stage again.
- Durations remain expressed through the `time` tag on processes, and `fastest` / `time <= X` goals keep working as aggregate metrics.
- Anything about calendars, locations, perishability or parallelism is now the consumer's job. If the consumer needs more information to schedule (e.g. dependencies between work blocks), it goes into the JSON output, not into a solver stage.
