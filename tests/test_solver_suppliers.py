import pytest
from resource_flow.models import Resource, Quantity, Process, Query, BasicResourceDef, AggregateGoal
from resource_flow.solvers.recipe.recipe_solver import RecipeSolver
from resource_flow.parser import RecipeParser

def test_solver_branches_on_supplier_combinations():
    """
    Test that the solver evaluates supplier permutations against optimization goals.
    We define a basic resource 'Flour' from two different suppliers with different costs.
    The solver should select the cheaper one when the goal is 'min cost' ('cheapest').
    """
    # Define two basic resources for 'Flour' with different costs
    flour_expensive = Resource("Flour", basic=True, cost=10.0, cost_unit="kg")
    flour_cheap = Resource("Flour", basic=True, cost=5.0, cost_unit="kg")

    # The recipe requires 1 kg of Flour and outputs 1 Dough
    dough = Resource("Dough")
    process = Process(
        original_label="Make Dough",
        inp={(Quantity(1, "kg"), Resource("Flour"))},
        out={(Quantity(1, "kg"), dough)},
    )

    # Goal is to minimize cost ('cheapest')
    query = Query(
        query={(Quantity(1, "kg"), dough)},
        goals=["cheapest"]
    )

    # Defs contain both basic resources
    defs = [flour_expensive, flour_cheap]

    solver = RecipeSolver({process}, query, defs)
    dag = solver.solve()

    assert dag.calculate_metric("cost") == 5.0

    # Ensure the correct basic resource was selected in the basic_requirements
    _, basic_reqs = solver.build_dag()
    assert "Flour" in basic_reqs
    assert basic_reqs["Flour"].cost == 5.0


def test_solver_chooses_supplier_from_parser(tmp_path):
    """
    Test that the solver evaluates supplier permutations and correctly records the chosen
    supplier as the source of the basic resource DAGEdge.
    """
    recipe_content = """
    def 1 kg Flour [cost: 10.00] at ExpensiveFarm;
    def 1 kg Flour [cost: 5.00] at CheapFarm;
    
    make_dough: 1 kg Flour -> 1 kg Dough;
    
    [cheapest] make 1 kg Dough;
    """
    recipe_file = tmp_path / "test_supplier.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    
    solver = RecipeSolver(ctx)
    dag = solver.solve()
    
    # Cost should be 5.00 from the Cheap Farm
    assert dag.calculate_metric("cost") == 5.0
    
    # Verify that the DAGEdge for flour came from the right supplier
    basic_edge = next(e for e in dag.edges if e.resource.name == "Flour" and e.target is None)
    assert basic_edge.source == "CheapFarm"


def test_solver_chooses_inline_supplier_cost(tmp_path):
    """
    Test that the solver evaluates supplier permutations but can also pick an inline
    basic resource with a cost tag if it is the cheapest option available.
    """
    recipe_content = """
    def 1 kg Flour [cost: 10.00] at ExpensiveFarm;
    def 1 kg Flour [cost: 5.00] at CheapFarm;
    
    make_dough: 1 kg Flour * [cost: 2.00] -> 1 kg Dough;
    
    [cheapest] make 1 kg Dough;
    """
    recipe_file = tmp_path / "test_inline_supplier.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    
    solver = RecipeSolver(ctx)
    dag = solver.solve()
    
    # Cost should be 2.00 from the inline definition
    assert dag.calculate_metric("cost") == 2.0
    
    # Verify that the DAGEdge for flour has no supplier since it was defined inline
    basic_edge = next(e for e in dag.edges if e.resource.name == "Flour" and e.target is None)
    assert basic_edge.source is None

