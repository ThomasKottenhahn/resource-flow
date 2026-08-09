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


def test_solver_globally_valid_basic_resource():
    cheese_basic = Resource("cheese", basic=True, cost=0.02)
    pasta_sheets = Resource("pasta_sheets", basic=True)
    lasagna = Resource("lasagna", basic=False)

    assemble = Process(
        "assemble",
        {(Quantity(100, "g"), cheese_basic), (Quantity(400, "g"), pasta_sheets)},
        {(Quantity(1000, "g"), lasagna)},
    )

    # Query cheese without specifying basic=True in the query Resource
    cheese_query = Resource("cheese", basic=False)
    query = Query({(Quantity(900, "g"), lasagna), (Quantity(200, "g"), cheese_query)})

    solver = RecipeSolver({assemble}, query)
    assert solver.is_basic("cheese") is True
    processes_in_dag, basic_reqs = solver.build_dag()
    assert "cheese" in basic_reqs
    scales = solver.solve()
    assert solver.final_demands["cheese"] == Quantity(290, "g")


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
    dag = solver.solve()
    from resource_flow.visualization import Visualizer
    viz = Visualizer(dag, solver.final_demands, solver.final_surplus, solver.basic_resources, solver.query)
    mermaid_str = viz.generate_mermaid()
    
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


def test_solver_metric_aggregation():
    res_carrots = Resource("carrots", basic=True, cost=0.50)
    res_water = Resource("water", basic=True, cost=0.02)
    res_chopped = Resource("chopped_carrots", basic=False)
    res_soup = Resource("soup", basic=False)

    p_prep = Process(
        "prep",
        {(Quantity(500, "g"), res_carrots)},
        {(Quantity(450, "g"), res_chopped)},
        cost=1.50,
        time=10.0,
        time_unit="min",
    )
    p_cook = Process(
        "cook",
        {(Quantity(450, "g"), res_chopped), (Quantity(1000, "ml"), res_water)},
        {(Quantity(1, "l"), res_soup)},
        cost=4.00,
        time=0.5,
        time_unit="h",  # 30 min
    )

    query = Query({(Quantity(2, "l"), res_soup)})

    solver = RecipeSolver({p_prep, p_cook}, query)
    dag = solver.solve()

    # Scale factor for both processes is 2.0
    assert dag["cook"] == 2.0
    assert dag["prep"] == 2.0

    from resource_flow.visualization import Visualizer
    viz = Visualizer(dag, solver.final_demands, solver.final_surplus, solver.basic_resources, solver.query)
    metrics = viz.get_metrics(time_unit="min")

    assert metrics["resource_cost"] == pytest.approx(540.0)
    assert metrics["process_cost"] == pytest.approx(11.0)
    assert metrics["total_cost"] == pytest.approx(551.0)
    assert metrics["total_time"] == pytest.approx(80.0)


def test_solver_batch_cost_unit_conversion(tmp_path):
    from resource_flow.parser import RecipeParser

    recipe_content = """
    peel: 300 g carrots * [cost: 20.00] -> 250 g peeled_carrots;
    make 1.5 kg peeled_carrots;
    """
    recipe_file = tmp_path / "batch_cost.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    resources, processes, query = parser.parse_file(str(recipe_file))

    solver = RecipeSolver(processes, query)
    dag = solver.solve()

    assert dag["peel"] == 6.0
    # Demanded carrots: 6.0 * 300g = 1800g = 1.8 kg
    # Cost: 1800g * (20.00 / 300g) = 120.00
    from resource_flow.visualization import Visualizer
    viz = Visualizer(dag, solver.final_demands, solver.final_surplus, solver.basic_resources, solver.query)
    res_cost = viz.get_metrics()["resource_cost"]
    assert res_cost == pytest.approx(120.00)


def test_solver_dimension_mismatch_error():
    res_carrots = Resource("carrots", basic=True, cost=0.05, cost_unit="g")
    p_peel = Process(
        "peel",
        {(Quantity(100, "ml"), res_carrots)},  # Invalid: ml used for resource with cost in g
        {(Quantity(100, "g"), Resource("peeled_carrots", basic=False))},
    )
    query = Query({(Quantity(100, "g"), Resource("peeled_carrots"))})

    solver = RecipeSolver({p_peel}, query)
    dag = solver.solve()

    from resource_flow.visualization import Visualizer
    viz = Visualizer(dag, solver.final_demands, solver.final_surplus, solver.basic_resources, solver.query)
    with pytest.raises(ValueError, match="Cannot convert unit"):
        viz.get_metrics()


def test_solver_print_plan_formatting(capsys):
    res_carrots = Resource("carrots", basic=True, tags={"organic"}, negated_tags={"frozen"}, cost=0.02, cost_unit="g")
    res_chopped = Resource("chopped_carrots", basic=False, tags={"organic", "cut"})
    res_soup = Resource("soup", basic=False, tags={"organic"})

    p_prep = Process(
        "prep",
        {(Quantity(500, "g"), res_carrots)},
        {(Quantity(450, "g"), res_chopped)},
        cost=1.50,
        time=10.0,
        time_unit="min",
        tags={"manual"},
    )
    p_cook = Process(
        "cook",
        {(Quantity(450, "g"), res_chopped)},
        {(Quantity(1, "l"), res_soup)},
        cost=4.00,
        time=0.5,
        time_unit="h",
    )

    query = Query({(Quantity(2, "l"), res_soup)})
    solver = RecipeSolver({p_prep, p_cook}, query)
    dag = solver.solve()

    from resource_flow.visualization import Visualizer
    viz = Visualizer(dag, solver.final_demands, solver.final_surplus, solver.basic_resources, solver.query)
    viz.print_plan(time_unit="min")
    captured = capsys.readouterr().out

    # Step headers format
    assert "Step 1: prep (Scale: 2.0000, Cost: 3.00, Time: 20.00 min) [manual]" in captured
    assert "Step 2: cook (Scale: 2.0000, Cost: 8.00, Time: 1.00 h)" in captured

    # Tag formatting on inputs and outputs
    assert "- 1000.00 g carrots * [organic, !frozen]" in captured
    assert "- 900.00 g chopped_carrots [cut, organic]" in captured

    # Basic resource cost formatting
    assert "- 1000.00 g carrots [organic, !frozen] (Cost: 20.00)" in captured

    # Metrics Summary
    assert "=== METRICS SUMMARY ===" in captured
    assert "Resource Cost: 20.00" in captured
    assert "Process Cost:  11.00" in captured
    assert "Total Cost:    31.00" in captured
    assert "Total Time:    80.00 min" in captured


def test_solver_generate_mermaid_reporting():
    res_carrots = Resource("carrots", basic=True, tags={"organic"}, cost=0.02, cost_unit="g")
    res_chopped = Resource("chopped_carrots", basic=False, tags={"organic", "cut"})
    res_soup = Resource("soup", basic=False, tags={"organic"})

    p_prep = Process(
        "prep",
        {(Quantity(500, "g"), res_carrots)},
        {(Quantity(450, "g"), res_chopped)},
        cost=1.50,
        time=10.0,
        time_unit="min",
        tags={"manual"},
    )
    p_cook = Process(
        "cook",
        {(Quantity(450, "g"), res_chopped)},
        {(Quantity(1, "l"), res_soup)},
        cost=4.00,
        time=0.5,
        time_unit="h",
    )

    query = Query({(Quantity(2, "l"), res_soup)})
    solver = RecipeSolver({p_prep, p_cook}, query)
    dag = solver.solve()

    from resource_flow.visualization import Visualizer
    viz = Visualizer(dag, solver.final_demands, solver.final_surplus, solver.basic_resources, solver.query)
    mermaid_str = viz.generate_mermaid(time_unit="min")

    # Process nodes with cost, time, and tags
    assert 'prep["prep (x2.00)\\nCost: 3.00, Time: 20.00 min\\n[manual]"]' in mermaid_str
    assert 'cook["cook (x2.00)\\nCost: 8.00, Time: 1.00 h"]' in mermaid_str

    # Basic resource node with tags and cost
    assert 'basic_carrots["carrots* [organic] (1000.00 g, Cost: 20.00)"]' in mermaid_str

    # Edge labels with resource tags
    assert 'basic_carrots -->|"1000.00 g carrots [organic]"| prep' in mermaid_str
    assert 'prep -->|"900.00 g chopped_carrots [cut, organic]"| cook' in mermaid_str

    # Query node with tags
    assert 'Query["Query: 2.00 l soup [organic]"]' in mermaid_str

    # Metrics node
    assert 'Metrics["Metrics Summary\\nResource Cost: 20.00\\nProcess Cost: 11.00\\nTotal Cost: 31.00\\nTotal Time: 80.00 min"]' in mermaid_str


def test_solver_tagged_resource_and_multi_query_graph_edges(tmp_path):
    from resource_flow.parser import RecipeParser

    recipe_content = """
    cut_onions [time: 5 min]: 50 g onions * [cost: 0.20] -> 50 g onions [cut];
    make_tomato_sauce [time: 20 min]: 500 g tomatoes * [cost: 2.00], 50 g onions [cut] -> 450 g tomato_sauce;
    assemble [time: 15 min]: 600 g tomato_sauce, 100 g cheese * [cost: 2.00] -> 1000 g lasagna;
    bake [time: 45 min]: 1000 g lasagna -> 900 g lasagna [baked];

    make 900 g lasagna [baked];
    make 200 g cheese;
    """
    recipe_file = tmp_path / "lasagne_subset.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    _, processes, query = parser.parse_file(str(recipe_file))

    solver = RecipeSolver(processes, query)
    dag = solver.solve()
    from resource_flow.visualization import Visualizer
    viz = Visualizer(dag, solver.final_demands, solver.final_surplus, solver.basic_resources, solver.query)
    mermaid_str = viz.generate_mermaid()

    # Edge from plain onions to cut_onions
    assert 'basic_onions -->|"66.67 g onions"| cut_onions' in mermaid_str
    # Edge from cut_onions to make_tomato_sauce with cut tag
    assert 'cut_onions -->|"66.67 g onions [cut]"| make_tomato_sauce' in mermaid_str
    # basic_onions should NOT connect directly to make_tomato_sauce
    assert 'basic_onions -->|"66.67 g onions [cut]"| make_tomato_sauce' not in mermaid_str

    # Cheese outgoing edges: 100g to assemble, 200g to Query
    assert 'basic_cheese -->|"100.00 g cheese"| assemble' in mermaid_str
    assert 'basic_cheese -->|"200.00 g cheese"| Query' in mermaid_str

    # lasagna (raw) from assemble should NOT connect to Query (which asks for lasagna [baked])
    assert 'assemble -->|"1000.00 g lasagna"| Query' not in mermaid_str
    # bake output should connect to Query
    assert 'bake -->|"900.00 g lasagna [baked]"| Query' in mermaid_str


def test_basic_resource_cost_isolation(tmp_path):
    rf_code = """
    cheap_prep: 100 g carrots * [cost: 2] -> 100 g cheap_soup;
    expensive_prep: 100 g carrots * [cost: 50] -> 100 g exp_soup;

    [cheapest] make 100 g cheap_soup;
    """
    f = tmp_path / "cheap.rf"
    f.write_text(rf_code, encoding="utf-8")

    from resource_flow.parser import RecipeParser
    parser = RecipeParser()
    _, procs, q = parser.parse_file(str(f))
    solver = RecipeSolver(procs, q)
    dag = solver.solve()

    assert dag.calculate_metric("cost") == 2.0






