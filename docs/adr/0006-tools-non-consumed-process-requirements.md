# 6. Tools as Non-Consumed Process Requirements

Date: 2026-08-08

## Status

Accepted

## Context

Processes in Resource Flow often require specific equipment (e.g., knives, ovens) to execute. Originally, all process inputs were treated as consumable resources that flow through the recipe graph and scale linearly with the process volume. However, equipment ("tools") is not consumed; a single knife can cut 500g of carrots or 5kg without needing 10 knives, and a knife can be shared across multiple consecutive processes.

If tools were modeled as standard input resources, they would generate demand that scales with the process scale factor, requiring complex recursive loops or infinite tool generation to resolve, cluttering the directed acyclic graph (DAG) and misrepresenting real-world constraints.

## Decision

1. **Tools are Properties of Processes**: Tools are modeled as a non-consumable requirement attached directly to a `Process` (via `with` or `using` clauses), rather than as distinct resource nodes connected by edges in the DAG.
2. **Tool Availability**: Tools provided in the Query (e.g., `make 1 meal using 1 knife`) act as an inventory check. The solver ensures all required tools across all chosen processes are met by the available tools in the query.
3. **No Scale Multiplier**: The quantity of a tool required by a process does not scale with the process's scale factor.
4. **Visibility in Outputs**: Tool usage is surfaced in the text execution plan (`print_plan`) under each step, and appended to the process node labels in Mermaid diagrams (`generate_mermaid`), ensuring they are visible without altering the core resource flow graph structure.

## Consequences

- Recipes can accurately model equipment constraints without distorting the resource flow DAG or scale multipliers.
- Tools are evaluated cleanly during the pathfinding phase: paths requiring missing tools are excluded from valid candidate DAGs.
- Tool information is embedded within process nodes rather than creating new nodes/edges, keeping visualizations focused on consumable resource flow.
- A fallback error mechanism provides clear feedback to the user on the minimal additional tools needed if no valid path can be found due to tool constraints.
