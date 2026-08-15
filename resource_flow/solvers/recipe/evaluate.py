from ...models import Goal, RelationalGoal, Quantity, SolutionCandidate
from .scale import ScaleResolver

class GoalEvaluator:
    """Evaluates fully resolved graphs against constraints and ranks them by aggregate goals."""
    
    def __init__(self, scale_resolver: ScaleResolver):
        self.scale_resolver = scale_resolver

    def evaluate_candidates(self, candidates: list[SolutionCandidate], relational_goals: list[Goal], aggregate_goals: list[Goal]) -> tuple[list[SolutionCandidate], tuple[Goal, float] | None]:
        """Filter candidates by relational goals and compute scores for ranking."""
        valid_candidates = []
        closest_diff = float("inf")
        closest_info = None

        for cand in candidates:
            self.scale_resolver.solve_dag(cand)

            passed_all = True
            for g in relational_goals:
                passed = g.evaluate(cand.dag)
                if not passed:
                    passed_all = False
                    # track closest for error reporting
                    target_val = g.val
                    if g.unit:
                        target_val = Quantity(g.val, g.unit).to_base_unit().val
                    metric_val = cand.dag.calculate_metric(g.tag, unit="s" if g.unit in {"s", "min", "h"} else g.unit)
                    diff = abs(metric_val - target_val)
                    if diff < closest_diff:
                        closest_diff = diff
                        display_val = cand.dag.calculate_metric(g.tag, unit=g.unit) if g.unit else cand.dag.calculate_metric(g.tag)
                        closest_info = (g, display_val)
                    break

            if passed_all:
                scores = tuple(g.evaluate(cand.dag) for g in aggregate_goals)
                tie_breaker = tuple(sorted(p.name for p in cand.processes))
                cand.scores = scores
                cand.tie_breaker = tie_breaker
                valid_candidates.append(cand)

        return valid_candidates, closest_info
