from ...dag import DAG, DAGEdge, DAGNode
from ...models import AggregateGoal, AnyGoal, Process, Query, Quantity, RelationalGoal, Resource, SolutionCandidate
from typing import Any
from .search import CandidateSearch
from .scale import ScaleResolver
from .evaluate import GoalEvaluator
from ..base import Solver

class RecipeSolver(Solver):
    """Orchestrates the resolution of queries by searching candidate graphs, scaling processes, and evaluating goals."""
    def __init__(self, processes: set[Process], query: Query) -> None:
        super().__init__(processes, query)
        
        filtered_processes = []
        for p in processes:
            if p.has_required_tools(self.query.tools):
                filtered_processes.append(p)
                
        self._all_processes = sorted(processes, key=lambda p: p.name)
        self.processes = sorted(filtered_processes, key=lambda p: p.name)
        self.basic_resources: dict[str, Resource] = {}
        self.basic_resource_names = self._identify_basic_resources()
        self.final_demands: dict[str, Quantity] = {}
        self.final_surplus: dict[str, Quantity] = {}
        self.processes_in_dag: list[Process] = []
        self.basic_requirements: set[str] = set()
        self._result_dag: DAG | None = None

    def _identify_basic_resources(self) -> set[str]:
        """Discover all resources marked as basic across processes and queries."""
        basics = set()
        for p in self.processes:
            for _, r in p.inp:
                if r.basic:
                    basics.add(r.name)
                    if r.name not in self.basic_resources or r.cost > 0:
                        self.basic_resources[r.name] = r
            for _, r in p.out:
                if r.basic:
                    basics.add(r.name)
                    if r.name not in self.basic_resources or r.cost > 0:
                        self.basic_resources[r.name] = r
        for _, r in self.query.query:
            if r.basic:
                basics.add(r.name)
                if r.name not in self.basic_resources or r.cost > 0:
                    self.basic_resources[r.name] = r
        return basics

    def is_basic(self, resource_name: str) -> bool:
        """Check if a resource name is known to be a basic resource."""
        return resource_name in self.basic_resource_names

    def find_producer(self, target: Resource | str) -> Process | None:
        """Find the first process capable of producing the target resource."""
        search = CandidateSearch(self.processes, self.query, self.basic_resources, self.basic_resource_names)
        producers = search.find_all_producers(target)
        return producers[0] if producers else None

    def build_dag(self) -> tuple[list[Process], set[str]]:
        """Build and cache the optimal process DAG. Returns (processes, basic_requirements)."""
        if self.processes_in_dag:
            return self.processes_in_dag, self.basic_requirements

        self.solve()
        return self.processes_in_dag, self.basic_requirements

    def _run_phase2_fallback(self, relational_goals) -> None:
        """Phase 2: Try with all processes to give a better error message about missing tools."""
        original_processes = self.processes
        original_basics = self.basic_resources
        original_basic_names = self.basic_resource_names
        
        self.processes = self._all_processes
        self.basic_resources = {}
        self.basic_resource_names = self._identify_basic_resources()
        
        try:
            search = CandidateSearch(self.processes, self.query, self.basic_resources, self.basic_resource_names)
            p2_candidates, _, _ = search.find_all_candidate_dags()
            
            scale = ScaleResolver(self.query, self.basic_resources, search)
            evaluator = GoalEvaluator(scale)
            p2_valid_candidates, _ = evaluator.evaluate_candidates(p2_candidates, relational_goals, [])
            
            if p2_valid_candidates:
                p2_valid = []
                for cand in p2_valid_candidates:
                    procs = cand.processes
                    missing_tools = self.query.calculate_missing_tools(procs)
                    p2_valid.append((missing_tools, procs))
                
                # Select candidate needing minimal additional tools (by number of distinct tools)
                p2_valid.sort(key=lambda item: len(item[0]))
                best_missing = p2_valid[0][0]
                tool_names = ", ".join(sorted(best_missing.keys()))
                
                raise ValueError(f"No solution found with available tools. Closest solution requires additional tools: {tool_names}")
        finally:
            self.processes = original_processes
            self.basic_resources = original_basics
            self.basic_resource_names = original_basic_names

    def solve(self) -> DAG:
        """Search candidate DAGs, evaluate goals, return the optimal result DAG."""
        self.processes_in_dag = []  # reset to re-solve if needed
        self._result_dag = None

        search = CandidateSearch(self.processes, self.query, self.basic_resources, self.basic_resource_names)
        candidates, cycle_procs, missing_resources = search.find_all_candidate_dags()

        relational_goals = [g for g in self.query.goals if isinstance(g, RelationalGoal)]
        aggregate_goals = [g for g in self.query.goals if not isinstance(g, RelationalGoal)]

        scale = ScaleResolver(self.query, self.basic_resources, search)
        evaluator = GoalEvaluator(scale)
        valid_candidates, closest_info = evaluator.evaluate_candidates(candidates, relational_goals, aggregate_goals)

        if not valid_candidates:
            if not candidates and len(self.processes) < len(self._all_processes):
                self._run_phase2_fallback(relational_goals)
                
            if not candidates:
                if cycle_procs:
                    proc_name = sorted(list(cycle_procs))[0]
                    raise ValueError(f"Cycle detected involving process '{proc_name}'")
                if missing_resources:
                    res_name = sorted(list(missing_resources))[0]
                    raise ValueError(f"No process found to produce non-basic resource '{res_name}'")
            if closest_info:
                g, val = closest_info
                raise ValueError(f"No solution found for {g}. Closest solution found: {g.tag} = {val}")
            raise ValueError("No valid processes found to satisfy the request.")

        valid_candidates.sort(key=lambda item: (item.scores, item.tie_breaker))
        best = valid_candidates[0]

        self.processes_in_dag = best.processes
        self.basic_requirements = best.basic_requirements
        self.final_demands = best.demands
        self.final_surplus = best.surplus
        self._result_dag = best.dag

        return self._result_dag