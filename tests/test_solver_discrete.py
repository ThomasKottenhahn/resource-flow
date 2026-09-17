import pytest
from resource_flow.models import Resource, Quantity, Process, Query
from resource_flow.solvers.recipe.recipe_solver import RecipeSolver

def test_solver_discrete_batch_scaling_single_process():
    pack = Resource("pack", basic=True, tags={"discrete"})
    final_a = Resource("final_a", basic=False)

    process_a = Process(
        "process_a",
        {(Quantity(1.1, "piece"), pack)},
        {(Quantity(1, "piece"), final_a)}
    )

    query = Query({(Quantity(1, "piece"), final_a)})
    
    solver = RecipeSolver({process_a}, query)
    dag = solver.solve()
    
    # Demand 1.1 should be rounded to 2.0
    assert solver.final_demands["pack"] == Quantity(2.0, "piece")
    # Surplus should be 0.9
    assert solver.final_surplus["pack"].val == pytest.approx(0.9)
    assert solver.final_surplus["pack"].unit == "piece"

def test_solver_discrete_batch_scaling_with_producer():
    # Test when the discrete resource is produced by a process
    egg = Resource("egg", basic=False, tags={"discrete"})
    final = Resource("final", basic=False)

    # A chicken lays 1 egg
    chicken = Process(
        "chicken",
        set(),
        {(Quantity(1, "piece"), egg)}
    )
    # We need 1.5 eggs for our recipe
    cook = Process(
        "cook",
        {(Quantity(1.5, "piece"), egg)},
        {(Quantity(1, "piece"), final)}
    )

    query = Query({(Quantity(1, "piece"), final)})
    
    solver = RecipeSolver({chicken, cook}, query)
    dag = solver.solve()
    
    # Cook demands 1.5 eggs. It should round to 2 eggs.
    # Chicken scales by 2, produces 2 eggs.
    # Surplus is 0.5 eggs.
    assert dag["chicken"] == 2.0
    assert solver.final_surplus["egg"] == Quantity(0.5, "piece")
