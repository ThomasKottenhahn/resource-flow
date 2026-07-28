# 1. Resource Batch Cost Interpretation and Base Unit Normalization

Date: 2026-07-27

## Status

Accepted

## Context

In Resource Flow recipes, basic resources carry acquisition costs. Previously, `[cost: X]` was interpreted as cost per quantity unit (unit price). However, recipes naturally state batch purchases (e.g. `300 g carrots * [cost: 20.00]` meaning 300g of carrots costs $20.00 total).

If costs were specified per arbitrary unit without standard normalization, mismatched units across processes (e.g., specifying cost in `g` and demanding in `kg` or `ml`) could lead to price calculation errors.

## Decision

1. **Batch Cost Semantics**: `[cost: X]` attached to a resource declaration represents the total cost for the declared `Quantity` (`300 g`).
2. **Base Unit Normalization**: `RecipeParser` and `Resource` compute and store `unit_cost` normalized to the standard base unit (`g` for weight, `ml` for volume, or raw unit for discrete counts).
3. **Basic Resource Restriction**: Only basic resources (`*` or `[basic]`) may specify a cost tag. Attaching `[cost: ...]` to non-basic resources raises a `ValueError`.
4. **Unit Mismatch Validation**: Quantity conversions across incompatible dimensions (e.g., weight vs volume) raise a `ValueError`.

## Consequences

- Recipes can intuitively specify exact purchase prices for declared batch quantities.
- Cost calculations in `RecipeSolver` scale accurately across units (`g` $\leftrightarrow$ `kg`, `ml` $\leftrightarrow$ `l`).
- Conflicting or invalid cost specifications on intermediate resources are caught early during parsing.
