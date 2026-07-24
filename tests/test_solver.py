import pytest
from resource_flow.models import Resource, Quantity, Process, Query
from resource_flow.solver import RecipeSolver


def test_solver_basic_detection_and_dag():
    # Setup resources
    flour = Resource("flour", basic=True)
    water = Resource("water", basic=True)
    dough = Resource("dough", basic=False)
    bread = Resource("bread", basic=False)

    # Setup processes
    make_dough = Process(
        "make_dough",
        {(Quantity(300, "g"), flour), (Quantity(200, "ml"), water)},
        {(Quantity(450, "g"), dough)}
    )
    bake_bread = Process(
        "bake_bread",
        {(Quantity(450, "g"), dough)},
        {(Quantity(1, "piece"), bread)}
    )

    query = Query({(Quantity(2, "piece"), bread)})

    solver = RecipeSolver({make_dough, bake_bread}, query)

    # Basic resource identification
    assert solver.basic_resource_names == {"flour", "water"}
    assert solver.is_basic("flour") is True
    assert solver.is_basic("dough") is False

    # Producer lookup
    assert solver.find_producer("dough") == make_dough
    assert solver.find_producer("bread") == bake_bread
    assert solver.find_producer("flour") is None

    # DAG construction
    processes_in_dag, basic_reqs = solver.build_dag()
    assert len(processes_in_dag) == 2
    # Topological order: make_dough must be before bake_bread since bake_bread depends on dough
    assert processes_in_dag[0] == make_dough
    assert processes_in_dag[1] == bake_bread
    assert basic_reqs == {"flour", "water"}


def test_solver_cycle_detection():
    # A -> B -> A (cyclic)
    res_a = Resource("A", basic=False)
    res_b = Resource("B", basic=False)

    p1 = Process("p1", {(Quantity(1, "g"), res_a)}, {(Quantity(1, "g"), res_b)})
    p2 = Process("p2", {(Quantity(1, "g"), res_b)}, {(Quantity(1, "g"), res_a)})

    query = Query({(Quantity(1, "g"), res_a)})

    solver = RecipeSolver({p1, p2}, query)
    with pytest.raises(ValueError, match="Cycle detected involving process"):
        solver.build_dag()


def test_solver_no_producer_error():
    # A is not basic, but has no producer
    res_a = Resource("A", basic=False)
    query = Query({(Quantity(1, "g"), res_a)})
    solver = RecipeSolver(set(), query)
    with pytest.raises(ValueError, match="No process found to produce non-basic resource 'A'"):
        solver.build_dag()


def test_solver_scaling_solution():
    # Let's test a simple bread recipe
    flour = Resource("flour", basic=True)
    water = Resource("water", basic=True)
    dough = Resource("dough", basic=False)
    bread = Resource("bread", basic=False)

    make_dough = Process(
        "make_dough",
        {(Quantity(300, "g"), flour), (Quantity(200, "ml"), water)},
        {(Quantity(450, "g"), dough)}
    )
    bake_bread = Process(
        "bake_bread",
        {(Quantity(450, "g"), dough)},
        {(Quantity(1, "piece"), bread)}
    )

    # We want 2 pieces of bread
    query = Query({(Quantity(2, "piece"), bread)})

    solver = RecipeSolver({make_dough, bake_bread}, query)
    scales = solver.solve()

    # bake_bread output is 1 piece, we need 2, so scale = 2.0
    assert scales["bake_bread"] == 2.0
    # make_dough needs to supply 2 * 450 = 900g dough. Output is 450g, so scale = 2.0
    assert scales["make_dough"] == 2.0

    # Verify final demands
    # Flour needed: 2 * 300 = 600g
    # Water needed: 2 * 200 = 400ml
    assert flour.name in solver.final_demands
    assert solver.final_demands[flour.name] == Quantity(600.0, "g")
    assert water.name in solver.final_demands
    assert solver.final_demands[water.name] == Quantity(400.0, "ml")


def test_solver_mermaid_generation():
    flour = Resource("flour", basic=True)
    bread = Resource("bread", basic=False)
    bake = Process("bake", {(Quantity(500, "g"), flour)}, {(Quantity(1, "piece"), bread)})
    query = Query({(Quantity(1, "piece"), bread)})

    solver = RecipeSolver({bake}, query)
    scales = solver.solve()
    mermaid_str = solver.generate_mermaid(scales)
    
    assert "graph TD" in mermaid_str
    assert "bake" in mermaid_str
    assert "basic_flour" in mermaid_str
    assert "Query" in mermaid_str
