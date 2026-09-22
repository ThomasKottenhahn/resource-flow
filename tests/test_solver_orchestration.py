from datetime import datetime
from resource_flow.dag import DAG
from resource_flow.models import Query, Process, Resource, Quantity, TimelineSchedule
from resource_flow.solvers.base import Solver
from resource_flow.solvers.interfaces import DAGSolver

class DummyDAGSolver(DAGSolver):
    def __init__(self, stub_dag: DAG):
        super().__init__(set(), Query(set()), [])
        self.stub_dag = stub_dag

    def solve(self) -> DAG:
        return self.stub_dag

def get_solver(query: Query, dag: DAG) -> Solver:
    # Wrap in lambda to pass the initialized instance
    class ConfiguredDummy(DummyDAGSolver):
        def __init__(self, processes, q, defs):
            super().__init__(dag)
            
    return Solver(processes=set(), query=query, defs=[], dag_solver_class=ConfiguredDummy)

def test_legacy_script():
    # No timing tags, map, or calendar
    query = Query(query={(Quantity(1, "piece"), Resource("Cake"))})
    dag = DAG([], [])
    solver = get_solver(query, dag)
    
    result = solver.solve()
    assert isinstance(result, DAG)

def test_script_with_by_deadline():
    query = Query(query={(Quantity(1, "piece"), Resource("Cake"))}, deadline=datetime.now())
    dag = DAG([], [])
    solver = get_solver(query, dag)
    
    result = solver.solve()
    assert isinstance(result, TimelineSchedule)

def test_script_with_starting_date():
    query = Query(query={(Quantity(1, "piece"), Resource("Cake"))}, start_time=datetime.now())
    dag = DAG([], [])
    solver = get_solver(query, dag)
    
    result = solver.solve()
    assert isinstance(result, TimelineSchedule)

def test_script_with_at_location():
    query = Query(query={(Quantity(1, "piece"), Resource("Cake"))}, location="Home")
    dag = DAG([], [])
    solver = get_solver(query, dag)
    
    result = solver.solve()
    assert isinstance(result, TimelineSchedule)

def test_script_with_hold_tag():
    query = Query(query={(Quantity(1, "piece"), Resource("Cake"))})
    res_with_hold = Resource("Water", tags={"hold <= 5 min"})
    # create dummy process to hold the resource
    p = Process("boil", inp=set(), out={(Quantity(1, "l"), res_with_hold)})
    from resource_flow.dag import DAGNode
    dag = DAG([DAGNode(p, 1.0)], [])
    
    solver = get_solver(query, dag)
    result = solver.solve()
    assert isinstance(result, TimelineSchedule)

def test_script_with_shelf_life_tag():
    query = Query(query={(Quantity(1, "piece"), Resource("Cake"))})
    res_with_shelf_life = Resource("Carrot", tags={"shelf_life: 7 days"})
    # create dummy process to hold the resource
    p = Process("buy", inp=set(), out={(Quantity(1, "kg"), res_with_shelf_life)})
    from resource_flow.dag import DAGNode
    dag = DAG([DAGNode(p, 1.0)], [])
    
    solver = get_solver(query, dag)
    result = solver.solve()
    assert isinstance(result, TimelineSchedule)

def test_stage_1_error_propagation():
    # Provide a script with an impossible basic resource.
    # We can mock this by having solve raise ValueError
    class ErrorSolver(DAGSolver):
        def solve(self) -> DAG:
            raise ValueError("No process found to produce non-basic resource")
            
    query = Query(query={(Quantity(1, "piece"), Resource("Cake"))}, deadline=datetime.now())
    solver = Solver(set(), query, dag_solver_class=ErrorSolver)
    
    import pytest
    with pytest.raises(ValueError, match="No process found"):
        solver.solve()

def test_empty_dag_with_deadline():
    # Empty DAG with deadline
    query = Query(query=set(), deadline=datetime.now())
    dag = DAG([], [])
    solver = get_solver(query, dag)
    
    result = solver.solve()
    assert isinstance(result, TimelineSchedule)
