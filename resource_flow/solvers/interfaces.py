import abc
from ..dag import DAG
from ..models import Process, Query, Quantity, Resource, BasicResourceDef, TimelineSchedule

class DAGSolver(abc.ABC):
    """Abstract base class for all Stage 1 DAG solvers in Resource Flow."""
    def __init__(self, processes: set[Process], query: Query, defs: list[Resource | BasicResourceDef] | None = None) -> None:
        self.processes = processes
        self.query = query
        self.defs = defs or []
        self.basic_resources: dict[str, list[Resource]] = {}
        self.final_demands: dict[str, Quantity] = {}
        self.final_surplus: dict[str, Quantity] = {}
        
    @abc.abstractmethod
    def solve(self) -> DAG:
        """Resolve the queries and return the optimal result DAG."""
        pass

class TimelineSolver(abc.ABC):
    """Abstract base class for all Stage 2 Timeline solvers in Resource Flow."""
    def __init__(self, dag: DAG, query: Query) -> None:
        self.dag = dag
        self.query = query
        
    @abc.abstractmethod
    def solve(self) -> TimelineSchedule:
        """Resolve the queries and return the resulting TimelineSchedule."""
        pass
