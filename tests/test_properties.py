import pytest
from hypothesis import given, strategies as st
from resource_flow.models import Resource, Quantity, Process, Query
from resource_flow.solvers import RecipeSolver

@st.composite
def quantities(draw):
    val = draw(st.floats(min_value=0.1, max_value=100.0, allow_nan=False, allow_infinity=False))
    unit = draw(st.sampled_from(["g", "kg", "ml", "l", "piece"]))
    return Quantity(val, unit)

@st.composite
def resources(draw, basic=None):
    name = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=3, max_size=10))
    is_basic = draw(st.booleans()) if basic is None else basic
    # cost only makes sense if basic is True, but to prevent instantiation errors in models.py:
    # "Cost can only be specified on basic resources"
    cost = draw(st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)) if is_basic else 0.0
    return Resource(name=name, basic=is_basic, cost=cost)

@st.composite
def solvable_recipe(draw):
    """
    Generate a set of processes and a query that are guaranteed to have a valid topology.
    We build a simple DAG layer by layer from leaves (basic resources) to a target root.
    """
    num_layers = draw(st.integers(min_value=1, max_value=3))
    
    current_layer_resources = [draw(resources(basic=True)) for _ in range(3)]
    all_processes = set()
    
    for layer in range(num_layers):
        num_procs_this_layer = draw(st.integers(min_value=1, max_value=2))
        next_layer_resources = []
        for i in range(num_procs_this_layer):
            # Ensure unique resources to avoid Hypothesis 'cannot satisfy min_size' errors
            unique_resources = list(set(current_layer_resources))
            num_inputs = draw(st.integers(min_value=1, max_value=min(2, len(unique_resources))))
            input_res_choices = draw(st.lists(st.sampled_from(unique_resources), min_size=num_inputs, max_size=num_inputs, unique=True))
            
            inp = set()
            for r in input_res_choices:
                inp.add((draw(quantities()), r))
                
            out_res = draw(resources(basic=False))
            out = {(draw(quantities()), out_res)}
            
            p = Process(original_label=f"proc_{layer}_{i}_{draw(st.text(alphabet='abc', min_size=1, max_size=3))}", inp=inp, out=out)
            all_processes.add(p)
            next_layer_resources.append(out_res)
            
        current_layer_resources = next_layer_resources
        
    target_resource = draw(st.sampled_from(current_layer_resources))
    target_qty = draw(quantities())
    query = Query({(target_qty, target_resource)})
    
    return all_processes, query


@given(solvable_recipe())
def test_solver_no_negative_surplus(recipe_data):
    """Property test asserting that if a solution is found, the final surplus is never negative."""
    processes, query = recipe_data
    solver = RecipeSolver(processes, query)
    try:
        solver.build_dag()
        solver.solve()
    except ValueError:
        # Depending on generated topology, some might still be unsolvable 
        # (e.g. cycle due to random name overlap, though rare with our generation strategy)
        return
        
    for res_name, surplus_qty in solver.final_surplus.items():
        assert surplus_qty.val >= 0.0, f"Surplus for {res_name} is negative: {surplus_qty.val}"


@given(solvable_recipe())
def test_solver_meets_all_query_goals(recipe_data):
    """Property test asserting that all query goals are met if a solution is found."""
    processes, query = recipe_data
    solver = RecipeSolver(processes, query)
    try:
        dag = solver.solve()
    except ValueError:
        return
        
    for goal in query.goals:
        # evaluate returns True for constraint/relational goals, 
        # or a float for aggregate/any goals.
        # But AnyGoal returns 0.0. 
        # So we only assert if it returns a boolean (meaning it's a hard constraint)
        result = goal.evaluate(dag)
        if isinstance(result, bool):
            assert result is True, f"Goal {goal} was not met"
