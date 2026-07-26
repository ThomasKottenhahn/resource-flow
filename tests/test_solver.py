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


def test_solver_tag_matching_producer_selection():
    res_carrots_raw = Resource("carrots", basic=True, tags=frozenset({"organic", "basic"}))
    res_carrots_conv = Resource("carrots", basic=False)
    res_carrots_org = Resource("carrots", basic=False, tags=frozenset({"organic", "washed"}))

    proc_conv = Process("grow_conv", set(), {(Quantity(1, "kg"), res_carrots_conv)})
    proc_org = Process("grow_org", {(Quantity(1, "kg"), res_carrots_raw)}, {(Quantity(1, "kg"), res_carrots_org)})

    req_organic = Resource("carrots", basic=False, tags=frozenset({"organic"}))
    proc_soup = Process("make_soup", {(Quantity(1, "kg"), req_organic)}, {(Quantity(1, "l"), Resource("soup"))})

    query = Query({(Quantity(1, "l"), Resource("soup"))})

    solver = RecipeSolver({proc_conv, proc_org, proc_soup}, query)
    dag, basic_reqs = solver.build_dag()

    assert proc_org in dag
    assert proc_conv not in dag
    assert basic_reqs == {"carrots"}


def test_solver_negated_tag_rejection():
    res_frozen_carrots = Resource("carrots", basic=False, tags=frozenset({"frozen", "organic"}))
    proc_freeze = Process("freeze", set(), {(Quantity(1, "kg"), res_frozen_carrots)})

    # Target demands organic carrots but explicitly forbids frozen (!frozen)
    target_carrots = Resource("carrots", basic=False, tags=frozenset({"organic"}), negated_tags=frozenset({"frozen"}))
    query = Query({(Quantity(1, "kg"), target_carrots)})

    solver = RecipeSolver({proc_freeze}, query)
    with pytest.raises(ValueError, match="No process found to produce non-basic resource 'carrots'"):
        solver.build_dag()


def test_solver_tagged_recipe_end_to_end(tmp_path):
    from resource_flow.parser import RecipeParser

    recipe_content = """
    prep [cost: 2.00, time: 15 min]: 500 g carrots * [organic, !cut] -> 450 g carrots [organic, cut];
    cook [cost: 3.50, time: 30 min]: 450 g carrots [organic, cut], 1 l water * -> 1 l carrot_soup [organic];
    make 2 l carrot_soup [organic];
    """
    recipe_file = tmp_path / "tagged_recipe.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    resources, processes, query = parser.parse_file(str(recipe_file))

    solver = RecipeSolver(processes, query)
    scales = solver.solve()

    assert scales["cook"] == 2.0
    assert scales["prep"] == 2.0
    assert solver.final_demands["carrots"] == Quantity(1000.0, "g")
    assert solver.final_demands["water"] == Quantity(2.0, "l")

