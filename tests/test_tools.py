import pytest
from resource_flow.parser import RecipeParser
from resource_flow.solver import RecipeSolver

def test_tool_route_chosen_when_available(tmp_path):
    dsl = """
    tool_route [time: 5]: 1 piece wood* -> 1 piece carved_wood with 1 piece knife;
    hand_route [time: 15]: 1 piece wood* -> 1 piece carved_wood;
    
    [fastest] make 1 piece carved_wood using 1 piece knife;
    """
    
    recipe_file = tmp_path / "recipe.rf"
    recipe_file.write_text(dsl)
    
    parser = RecipeParser()
    _, procs, query = parser.parse_file(str(recipe_file))
    
    solver = RecipeSolver(procs, query)
    dag = solver.solve()
    
    processes_used = [node.process.name for node in dag.nodes if node.process]
    assert "tool_route" in processes_used
    assert "hand_route" not in processes_used

def test_fallback_route_chosen_when_tool_missing(tmp_path):
    dsl = """
    tool_route [time: 5]: 1 piece wood* -> 1 piece carved_wood with 1 piece knife;
    hand_route [time: 15]: 1 piece wood* -> 1 piece carved_wood;
    
    [fastest] make 1 piece carved_wood;
    """
    
    recipe_file = tmp_path / "recipe.rf"
    recipe_file.write_text(dsl)
    
    parser = RecipeParser()
    _, procs, query = parser.parse_file(str(recipe_file))
    
    solver = RecipeSolver(procs, query)
    dag = solver.solve()
    
    processes_used = [node.process.name for node in dag.nodes if node.process]
    assert "hand_route" in processes_used
    assert "tool_route" not in processes_used

def test_tool_quantity_matching(tmp_path):
    dsl = """
    tool_route [time: 5]: 1 piece wood* -> 1 piece carved_wood with 2 piece clamp;
    hand_route [time: 15]: 1 piece wood* -> 1 piece carved_wood;
    
    [fastest] make 1 piece carved_wood using 1 piece clamp;
    """
    
    recipe_file = tmp_path / "recipe.rf"
    recipe_file.write_text(dsl)
    
    parser = RecipeParser()
    _, procs, query = parser.parse_file(str(recipe_file))
    
    solver = RecipeSolver(procs, query)
    dag = solver.solve()
    
    processes_used = [node.process.name for node in dag.nodes if node.process]
    assert "hand_route" in processes_used
    assert "tool_route" not in processes_used

def test_solver_fallback_reports_minimal_additional_tools(tmp_path):
    # Two possible routes to get 'meal'
    # Route A needs 'knife' and 'oven' (2 tools missing)
    # Route B needs 'microwave' (1 tool missing)
    # The solver should prefer reporting Route B's missing tools if neither can be met
    recipe = """
    prep_a: 1 piece raw_food* -> 1 piece prepped_a with 1 piece knife;
    cook_a: 1 piece prepped_a -> 1 piece meal with 1 piece oven;
    
    cook_b: 1 piece raw_food* -> 1 piece meal with 1 piece microwave;
    
    make 1 piece meal;
    """
    recipe_file = tmp_path / "fallback.rf"
    recipe_file.write_text(recipe)

    parser = RecipeParser()
    _, procs, query = parser.parse_file(str(recipe_file))
    
    solver = RecipeSolver(procs, query)

    # query has no tools available, so both routes fail
    with pytest.raises(ValueError, match="No solution found with available tools. Closest solution requires additional tools: microwave"):
        solver.solve()

    recipe_with_tool = """
    prep_a: 1 piece raw_food* -> 1 piece prepped_a with 1 piece knife;
    cook_a: 1 piece prepped_a -> 1 piece meal with 1 piece oven;
    
    cook_b: 1 piece raw_food* -> 1 piece meal with 1 piece microwave;
    
    make 1 piece meal using 1 piece microwave;
    """
    recipe_file2 = tmp_path / "fallback_works.rf"
    recipe_file2.write_text(recipe_with_tool)

    _, procs2, query2 = parser.parse_file(str(recipe_file2))
    solver2 = RecipeSolver(procs2, query2)
    # If we provide microwave, Route B works!
    dag = solver2.solve()
    processes_used = [node.process.name for node in dag.nodes if node.process]
    assert "cook_b" in processes_used

def test_shared_tool_across_processes(tmp_path):
    dsl = """
    cut [time: 5]: 1 piece log* -> 1 piece wood with 1 piece knife;
    carve [time: 5]: 1 piece wood -> 1 piece carved_wood with 1 piece knife;
    
    [fastest] make 1 piece carved_wood using 1 piece knife;
    """
    # 1 knife satisfies both since it's shared/not consumed
    recipe_file = tmp_path / "recipe.rf"
    recipe_file.write_text(dsl)
    
    parser = RecipeParser()
    _, procs, query = parser.parse_file(str(recipe_file))
    
    solver = RecipeSolver(procs, query)
    dag = solver.solve()
    
    processes_used = [node.process.name for node in dag.nodes if node.process]
    assert "cut" in processes_used
    assert "carve" in processes_used
