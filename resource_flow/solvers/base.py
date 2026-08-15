import abc
from ..dag import DAG
from ..models import Process, Query, Quantity, Resource

class Solver(abc.ABC):
    """Abstract base class for all solvers in Resource Flow."""
    def __init__(self, processes: set[Process], query: Query) -> None:
        self.processes = processes
        self.query = query
        self.basic_resources: dict[str, Resource] = {}
        self.final_demands: dict[str, Quantity] = {}
        self.final_surplus: dict[str, Quantity] = {}

    @abc.abstractmethod
    def solve(self) -> DAG:
        """Resolve the queries and return the optimal result DAG."""
        pass
