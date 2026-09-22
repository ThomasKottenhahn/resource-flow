from ..dag import DAG
from ..models import Process, Query, Quantity, Resource, BasicResourceDef, TimelineSchedule, ProgramContext
from .interfaces import DAGSolver, TimelineSolver

class Solver:
    """Orchestrates the 2-stage solver pipeline."""
    def __init__(
        self,
        ctx: ProgramContext | set[Process] | None = None,
        processes: set[Process] | Query | None = None,
        query: Query | list[Resource] | None = None,
        defs: list[Resource | BasicResourceDef] | None = None,
        dag_solver_class: type[DAGSolver] | None = None,
        timeline_solver_class: type[TimelineSolver] | None = None,
    ) -> None:
        if isinstance(ctx, ProgramContext):
            self.processes = ctx.processes
            self.query = ctx.query
            self.defs = ctx.defs
        elif ctx is not None:
            # Called as Solver(processes, query)
            self.defs = query if isinstance(query, list) else defs
            self.query = processes
            self.processes = ctx
        else:
            self.processes = processes if processes is not None else set()
            self.query = query if query is not None else Query(set())
            self.defs = defs or []
            
        if dag_solver_class is None:
            from .dag.basic_recipe_solver import BasicRecipeSolver
            self.dag_solver_class = BasicRecipeSolver
        else:
            self.dag_solver_class = dag_solver_class
            
        if timeline_solver_class is None:
            from .timeline.basic_timeline_solver import BasicTimelineSolver
            self.timeline_solver_class = BasicTimelineSolver
        else:
            self.timeline_solver_class = timeline_solver_class

        self.final_demands: dict[str, Quantity] = {}
        self.final_surplus: dict[str, Quantity] = {}
        self.basic_resources: dict[str, list[Resource]] = {}

    def solve(self) -> DAG | TimelineSchedule:
        """Resolve the queries and return the optimal result DAG or TimelineSchedule."""
        dag_solver = self.dag_solver_class(self.processes, self.query, self.defs)
        dag = dag_solver.solve()
        
        # Pull properties from dag_solver that might be expected on Solver (like final_demands)
        if hasattr(dag_solver, 'final_demands'):
            self.final_demands = dag_solver.final_demands
        if hasattr(dag_solver, 'final_surplus'):
            self.final_surplus = dag_solver.final_surplus
        if hasattr(dag_solver, 'basic_resources'):
            self.basic_resources = dag_solver.basic_resources
        
        if self._needs_timeline(dag):
            timeline_solver = self.timeline_solver_class(dag, self.query)
            return timeline_solver.solve()
            
        return dag

    def _needs_timeline(self, dag: DAG) -> bool:
        if self.query.location is not None or self.query.start_time is not None or self.query.deadline is not None:
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
        dag_solver = self.dag_solver_class(self.processes, self.query, self.defs)
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
