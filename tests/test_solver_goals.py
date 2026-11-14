import pytest
from resource_flow.models import Resource, Quantity, Process, Query
from resource_flow.parser import RecipeParser
from resource_flow.solvers import RecipeSolver


def test_solver_goal_default_any():
    query = Query({(Quantity(1, "piece"), Resource("bread"))})
    assert query.goals == ("any",)


def test_solver_goal_cheapest_selection():
    # Two alternative recipes for producing 1 kg flour_mix:
    # Recipe 1: expensive_grind (cost: 10.0, time: 5 min)
    # Recipe 2: cheap_grind (cost: 2.0, time: 20 min)
    wheat = Resource("wheat", basic=True, cost=1.0)
    flour_mix = Resource("flour_mix", basic=False)

    expensive_grind = Process(
        "expensive_grind",
        {(Quantity(1, "kg"), wheat)},
        {(Quantity(1, "kg"), flour_mix)},
        cost=10.0,
        time=5.0,
    )
    cheap_grind = Process(
        "cheap_grind",
        {(Quantity(1, "kg"), wheat)},
        {(Quantity(1, "kg"), flour_mix)},
        cost=2.0,
        time=20.0,
    )

    query_cheapest = Query({(Quantity(1, "kg"), flour_mix)}, goals=["cheapest"])
    solver_cheap = RecipeSolver({expensive_grind, cheap_grind}, query_cheapest)
    scales_cheap = solver_cheap.solve()

    assert "cheap_grind" in scales_cheap
    assert "expensive_grind" not in scales_cheap
    assert scales_cheap["cheap_grind"] == 1.0


def test_solver_goal_fastest_selection():
    # Two alternative recipes for producing 1 kg flour_mix:
    # Recipe 1: expensive_grind (cost: 10.0, time: 5 min)
    # Recipe 2: cheap_grind (cost: 2.0, time: 20 min)
    wheat = Resource("wheat", basic=True, cost=1.0)
    flour_mix = Resource("flour_mix", basic=False)

    expensive_grind = Process(
        "expensive_grind",
        {(Quantity(1, "kg"), wheat)},
        {(Quantity(1, "kg"), flour_mix)},
        cost=10.0,
        time=5.0,
    )
    cheap_grind = Process(
        "cheap_grind",
        {(Quantity(1, "kg"), wheat)},
        {(Quantity(1, "kg"), flour_mix)},
        cost=2.0,
        time=20.0,
    )

    query_fastest = Query({(Quantity(1, "kg"), flour_mix)}, goals=["fastest"])
    solver_fast = RecipeSolver({expensive_grind, cheap_grind}, query_fastest)
    scales_fast = solver_fast.solve()

    assert "expensive_grind" in scales_fast
    assert "cheap_grind" not in scales_fast
    assert scales_fast["expensive_grind"] == 1.0


def test_solver_goal_cascade_tie_breaking():
    # Two processes with EQUAL cost (5.0), but different time (10 min vs 30 min)
    # Goal cascade [cheapest, fastest] should tie on cost and use fastest to break tie
    raw = Resource("raw", basic=True, cost=1.0)
    out = Resource("out", basic=False)

    proc_slow = Process(
        "proc_slow",
        {(Quantity(1, "kg"), raw)},
        {(Quantity(1, "kg"), out)},
        cost=5.0,
        time=30.0,
    )
    proc_fast = Process(
        "proc_fast",
        {(Quantity(1, "kg"), raw)},
        {(Quantity(1, "kg"), out)},
        cost=5.0,
        time=10.0,
    )

    query = Query({(Quantity(1, "kg"), out)}, goals=["cheapest", "fastest"])
    solver = RecipeSolver({proc_slow, proc_fast}, query)
    scales = solver.solve()

    assert "proc_fast" in scales
    assert "proc_slow" not in scales


def test_solver_goal_lexicographical_tie_breaking():
    # Two identical processes (cost 5.0, time 10 min)
    # Ties on both cheapest and fastest -> deterministic lexicographical tie break selects 'proc_a' over 'proc_b'
    raw = Resource("raw", basic=True, cost=1.0)
    out = Resource("out", basic=False)

    proc_b = Process(
        "proc_b",
        {(Quantity(1, "kg"), raw)},
        {(Quantity(1, "kg"), out)},
        cost=5.0,
        time=10.0,
    )
    proc_a = Process(
        "proc_a",
        {(Quantity(1, "kg"), raw)},
        {(Quantity(1, "kg"), out)},
        cost=5.0,
        time=10.0,
    )

    query = Query({(Quantity(1, "kg"), out)}, goals=["cheapest", "fastest"])
    solver = RecipeSolver({proc_b, proc_a}, query)
    scales = solver.solve()

    assert "proc_a" in scales
    assert "proc_b" not in scales


def test_solver_goal_multi_query_override(tmp_path):
    recipe_content = """
    proc_slow [cost: 2.0, time: 30 min]: 1 kg wheat * -> 1 kg flour;
    proc_fast [cost: 5.0, time: 5 min]: 1 kg wheat * -> 1 kg flour;

    [cheapest] make 1 kg flour;
    [fastest] make 2 kg flour;
    """
    recipe_file = tmp_path / "multi_query.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    _, processes, query = ctx.resources, ctx.processes, ctx.query

    # Last query goal [fastest] overrides preceding [cheapest]
    assert query.goals == ("fastest",)

    solver = RecipeSolver(processes, query)
    scales = solver.solve()
    assert "proc_fast" in scales


def test_solver_goal_cycle_pruning_with_valid_alternative():
    # Process 1 & 2 form a cycle (A -> B -> A)
    # Process 3 is a direct acyclic route (C * -> A)
    # Solver should prune cyclic P1/P2 route and select valid P3 route!
    res_a = Resource("A", basic=False)
    res_b = Resource("B", basic=False)
    res_c = Resource("C", basic=True, cost=1.0)

    p1 = Process("p1_cycle", {(Quantity(1, "g"), res_a)}, {(Quantity(1, "g"), res_b)})
    p2 = Process("p2_cycle", {(Quantity(1, "g"), res_b)}, {(Quantity(1, "g"), res_a)})
    p3 = Process("p3_valid", {(Quantity(1, "g"), res_c)}, {(Quantity(1, "g"), res_a)})

    query = Query({(Quantity(1, "g"), res_a)}, goals=["cheapest"])

    solver = RecipeSolver({p1, p2, p3}, query)
    scales = solver.solve()

    assert "p3_valid" in scales
    assert "p1_cycle" not in scales
    assert "p2_cycle" not in scales


def test_solver_goal_extensibility():
    res_a = Resource("A", basic=True)
    res_out = Resource("out", basic=False)
    proc = Process("proc", {(Quantity(1, "kg"), res_a)}, {(Quantity(1, "kg"), res_out)}, cost=10.0, time=15.0)

    query = Query({(Quantity(1, "kg"), res_out)})
    solver = RecipeSolver({proc}, query)

    dag = solver.solve()

    # Built-in evaluation checks
    from resource_flow.models import AggregateGoal, AnyGoal
    cost_val = AggregateGoal("min", "cost").evaluate(dag)
    time_val = AggregateGoal("min", "time").evaluate(dag)
    any_val = AnyGoal().evaluate(dag)

    assert cost_val == 10.0
    assert time_val == 15.0
    assert any_val == 0.0


def test_solver_goal_basic_vs_process_cost_comparison(tmp_path):
    recipe_content = """
    mix_batter [time: 10 min]: 200 g flour * [cost: 2.00], 300 ml milk * [cost: 1.50], 2 piece eggs * [cost: 2.00] -> 480 g pancake_batter * [cost: 15.00];
    fry [time: 15 min]: 500 g pancake_batter, 20 ml oil * [cost: 0.02] -> 500 g pancakes;

    [cheapest] make 500 g pancakes;
    """
    recipe_file = tmp_path / "pancakes_cheapest.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    _, processes, query = ctx.resources, ctx.processes, ctx.query

    solver = RecipeSolver(processes, query)
    scales = solver.solve()
    # Mixing batter costs ~5.75 total vs buying pre-made batter @ 15.64 total.
    # [cheapest] must select mix_batter!
    assert "mix_batter" in scales
    assert "fry" in scales
    assert scales.calculate_metric("cost") == pytest.approx(5.75, abs=0.01)


def test_solver_goal_aggregate_custom_metrics(tmp_path):
    recipe_content = """
    harvest_manual [manual_labour, co2: 2, throughput: 10]: 100 g seeds * -> 100 kg crops;
    harvest_machine [automated, co2: 50, throughput: 100]: 100 g seeds * -> 100 kg crops;
    
    [min manual_labour] make 100 kg crops;
    """
    recipe_file = tmp_path / "custom_metrics_min.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    from resource_flow.parser import RecipeParser
    from resource_flow.solvers import RecipeSolver

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    solver = RecipeSolver(ctx)
    scales = solver.solve()
    
    # [min manual_labour] should prefer harvest_machine
    assert "harvest_machine" in scales
    assert "harvest_manual" not in scales

    recipe_content_max = """
    harvest_manual [manual_labour, co2: 2, throughput: 10]: 100 g seeds * -> 100 kg crops;
    harvest_machine [automated, co2: 50, throughput: 100]: 100 g seeds * -> 100 kg crops;
    
    [max throughput] make 100 kg crops;
    """
    recipe_file_max = tmp_path / "custom_metrics_max.rf"
    recipe_file_max.write_text(recipe_content_max, encoding="utf-8")
    
    ctx = parser.parse_file(str(recipe_file_max))
    _, processes, query = ctx.resources, ctx.processes, ctx.query
    solver = RecipeSolver(ctx)
    scales = solver.solve()
    
    # [max throughput] should also prefer harvest_machine
    assert "harvest_machine" in scales
    assert "harvest_manual" not in scales
    
    recipe_content_min_co2 = """
    harvest_manual [manual_labour, co2: 2, throughput: 10]: 100 g seeds * -> 100 kg crops;
    harvest_machine [automated, co2: 50, throughput: 100]: 100 g seeds * -> 100 kg crops;
    
    [min co2] make 100 kg crops;
    """
    recipe_file_min_co2 = tmp_path / "custom_metrics_min_co2.rf"
    recipe_file_min_co2.write_text(recipe_content_min_co2, encoding="utf-8")
    
    ctx = parser.parse_file(str(recipe_file_min_co2))
    _, processes, query = ctx.resources, ctx.processes, ctx.query
    solver = RecipeSolver(ctx)
    scales = solver.solve()
    
    # [min co2] should prefer harvest_manual
    assert "harvest_manual" in scales
    assert "harvest_machine" not in scales


def test_solver_goal_relational_constraints(tmp_path):
    recipe_content = """
    harvest_manual [manual_labour, time: 2 h]: 100 g seeds * -> 100 kg crops;
    harvest_machine [automated, time: 10 min]: 100 g seeds * -> 100 kg crops;
    
    [time <= 30 min] make 100 kg crops;
    """
    recipe_file = tmp_path / "relational_constraints.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    from resource_flow.parser import RecipeParser
    from resource_flow.solvers import RecipeSolver

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    solver = RecipeSolver(ctx)
    scales = solver.solve()
    
    # 2 h is 120 min, so harvest_manual fails the constraint.
    # harvest_machine (10 min) passes.
    assert "harvest_machine" in scales
    assert "harvest_manual" not in scales


def test_solver_goal_infeasible_closest_match(tmp_path):
    recipe_content = """
    harvest_manual [manual_labour: 5]: 100 g seeds * -> 100 kg crops;
    harvest_machine [manual_labour: 1]: 100 g seeds * -> 100 kg crops;
    
    [manual_labour == 0] make 100 kg crops;
    """
    recipe_file = tmp_path / "infeasible.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    from resource_flow.parser import RecipeParser
    from resource_flow.solvers import RecipeSolver
    import pytest

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    solver = RecipeSolver(ctx)
    
    with pytest.raises(ValueError, match=r"No solution found for manual_labour == 0\.0\. Closest solution found: manual_labour = 1\.0"):
        solver.solve()


def test_basic_resource_custom_tag_scaling(tmp_path):
    rf_code_grams = """
    carrots: 1000 g carrots * [co2: 0.2 kg] -> 1000 g prepped_carrots;
    [min co2] make 1000 g prepped_carrots;
    """
    rf_code_kg = """
    carrots: 1 kg carrots * [co2: 0.2 kg] -> 1000 g prepped_carrots;
    [min co2] make 1000 g prepped_carrots;
    """
    f_grams = tmp_path / "grams.rf"
    f_grams.write_text(rf_code_grams, encoding="utf-8")
    f_kg = tmp_path / "kg.rf"
    f_kg.write_text(rf_code_kg, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(f_grams))
    _, procs_g, q_g = ctx.resources, ctx.processes, ctx.query
    dag_g = RecipeSolver(ctx).solve()

    ctx = parser.parse_file(str(f_kg))
    _, procs_kg, q_kg = ctx.resources, ctx.processes, ctx.query
    dag_kg = RecipeSolver(ctx).solve()

    assert dag_g.calculate_metric("co2") == dag_kg.calculate_metric("co2") == 200.0


def test_relational_goal_error_message_unit_formatting(tmp_path):
    rf_code = """
    bake [time: 60 min]: 100 g dough -> 100 g bread;
    base: 100 g flour * -> 100 g dough;
    [time <= 45 min] make 100 g bread;
    """
    f = tmp_path / "bake.rf"
    f.write_text(rf_code, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(f))
    _, procs, q = ctx.resources, ctx.processes, ctx.query
    solver = RecipeSolver(ctx)

    with pytest.raises(ValueError, match=r"No solution found for time <= 45\.0 min\. Closest solution found: time = 60\.0"):
        solver.solve()
