from typing import Any
from ..dag import DAG
from ..models import Process, Query, Quantity, Resource, BasicResourceDef, TimelineSchedule, ProgramContext
from .interfaces import DAGSolver, TimelineSolver

class Solver:
    """Orchestrates the 2-stage solver pipeline."""
    def __init__(
        self,
        ctx: ProgramContext | set[Process] | None = None,
        processes: set[Process] | list[Query] | Query | None = None,
        query: list[Query] | Query | list[Resource] | None = None,
        defs: list[Resource | BasicResourceDef] | None = None,
        dag_solver_class: type[DAGSolver] | type[Any] | None = None,
        timeline_solver_class: type[TimelineSolver] | None = None,
    ) -> None:
        if isinstance(ctx, ProgramContext):
            self.processes = ctx.processes
            self.queries = ctx.queries
            self.defs = ctx.defs
            self.ctx = ctx
        elif ctx is not None:
            # Called as Solver(processes, query)
            if isinstance(query, Query):
                self.queries = [query]
            elif isinstance(query, list) and (len(query) == 0 or isinstance(query[0], Query)):
                self.queries = query  # type: ignore
            else:
                self.queries = processes if isinstance(processes, list) else ([processes] if isinstance(processes, Query) else [])  # type: ignore
                self.defs = query if query is not None else defs
                
            self.processes = ctx if isinstance(ctx, set) else set()
            self.ctx = None
        else:
            self.processes = processes if isinstance(processes, set) else set()
            
            if isinstance(query, Query):
                self.queries = [query]
            elif isinstance(query, list) and (len(query) == 0 or isinstance(query[0], Query)):
                self.queries = query  # type: ignore
            else:
                self.queries = []
                
            self.defs = defs or []
            self.ctx = None
            
        if dag_solver_class is None:
            from .dag.basic_recipe_solver import BasicRecipeSolver
            self.dag_solver_class: type[DAGSolver] = BasicRecipeSolver
        else:
            self.dag_solver_class = dag_solver_class
            
        if timeline_solver_class is None:
            from .timeline.basic_timeline_solver import BasicTimelineSolver
            self.timeline_solver_class: type[TimelineSolver] = BasicTimelineSolver
        else:
            self.timeline_solver_class = timeline_solver_class

        self.final_demands: dict[str, Quantity] = {}
        self.final_surplus: dict[str, Quantity] = {}
        self.basic_resources: dict[str, list[Resource]] = {}

    @property
    def query(self) -> Query:
        raise DeprecationWarning("query property is deprecated. Use queries instead.")

    def solve(self) -> DAG | TimelineSchedule:
        """Resolve the queries and return the optimal result DAG or TimelineSchedule."""
        dag_solver = self.dag_solver_class(self.processes, self.queries, self.defs)  # type: ignore
        dag = dag_solver.solve()
        
        # Pull properties from dag_solver that might be expected on Solver (like final_demands)
        if hasattr(dag_solver, 'final_demands'):
            self.final_demands = dag_solver.final_demands
        if hasattr(dag_solver, 'final_surplus'):
            self.final_surplus = dag_solver.final_surplus
        if hasattr(dag_solver, 'basic_resources'):
            self.basic_resources = dag_solver.basic_resources
        
        if self._needs_timeline(dag):
            # pyrefly: ignore [bad-argument-type]
            timeline_solver = self.timeline_solver_class(dag, self.queries, self.ctx)
            return timeline_solver.solve()
            
        return dag

    def _needs_timeline(self, dag: DAG) -> bool:
        for q in self.queries:
            # pyrefly: ignore [missing-attribute]
            if q.location is not None or q.start_time is not None or q.deadline is not None:
                return True
        for node in dag.nodes:
            if node.process:
                if any("hold" in t or "shelf_life" in t for t in node.process.tags):
                    return True
                for _, res in node.process.inp:
                    if any("hold" in t or "shelf_life" in t for t in res.tags):
                        return True
                for _, res in node.process.out:
                    if any("hold" in t or "shelf_life" in t for t in res.tags):
                        return True
        for edge in dag.edges:
            if edge.resource:
                if any("hold" in t or "shelf_life" in t for t in edge.resource.tags):
                    return True
        return False

    def build_dag(self) -> tuple[list[Process], dict[str, Resource]]:
        """Pass-through for Stage 1 DAG solvers that support build_dag."""
        dag_solver = self.dag_solver_class(self.processes, self.queries, self.defs)  # type: ignore
        if hasattr(dag_solver, 'build_dag'):
            res = dag_solver.build_dag()
            
            if hasattr(dag_solver, 'final_demands'):
                self.final_demands = dag_solver.final_demands
            if hasattr(dag_solver, 'final_surplus'):
                self.final_surplus = dag_solver.final_surplus
            if hasattr(dag_solver, 'basic_resources'):
                self.basic_resources = dag_solver.basic_resources
                
            return res
        raise AttributeError(f"{self.dag_solver_class.__name__} does not implement build_dag")
