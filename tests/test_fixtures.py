import os
import json
from pathlib import Path
import pytest
from resource_flow.parser import RecipeParser
from resource_flow.solvers import RecipeSolver
from resource_flow.models import Quantity

# Determine the fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Collect all .rf files in the fixtures directory
if FIXTURES_DIR.exists():
    rf_files = list(FIXTURES_DIR.glob("*.rf"))
else:
    rf_files = []

def serialize_quantity(q: Quantity) -> dict:
    return {"value": q.val, "unit": q.unit}

def dump_solver_output(solver: RecipeSolver, dag) -> dict:
    # Serialize the solver output to a standard dictionary format
    output = {
        "process_scales": {proc: float(scale) for proc, scale in dag.process_scales.items()},
        "final_demands": {res: serialize_quantity(q) for res, q in solver.final_demands.items()},
        "final_surplus": {res: serialize_quantity(q) for res, q in solver.final_surplus.items()}
    }
    # Sort dictionaries by key to ensure stable JSON serialization
    output["process_scales"] = dict(sorted(output["process_scales"].items()))
    output["final_demands"] = dict(sorted(output["final_demands"].items()))
    output["final_surplus"] = dict(sorted(output["final_surplus"].items()))
    return output

@pytest.mark.parametrize("rf_file", rf_files, ids=lambda p: p.name)
def test_fixture(rf_file: Path):
    json_file = rf_file.with_suffix(".json")
    
    # 1. Parse and run the solver
    parser = RecipeParser()
    ctx = parser.parse_file(str(rf_file))
    processes, query = ctx.processes, ctx.query
    
    solver = RecipeSolver(processes, query)
    dag = solver.solve()
    
    # 2. Serialize actual output
    actual_output = dump_solver_output(solver, dag)
    
    # 3. Check for UPDATE_FIXTURES
    update_fixtures = os.environ.get("UPDATE_FIXTURES") == "1"
    
    if update_fixtures:
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(actual_output, f, indent=2)
            f.write("\n")
        # If we updated the fixture, we pass
        return
        
    # 4. If not updating, assert against existing JSON
    assert json_file.exists(), f"Expected JSON fixture missing: {json_file}. Run with UPDATE_FIXTURES=1 to generate it."
    
    with open(json_file, "r", encoding="utf-8") as f:
        expected_output = json.load(f)
        
    # Standard pytest dict comparison gives a nice diff
    assert actual_output == expected_output, f"Solver output mismatch for {rf_file.name}"
