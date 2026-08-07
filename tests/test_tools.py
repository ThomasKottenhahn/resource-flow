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
