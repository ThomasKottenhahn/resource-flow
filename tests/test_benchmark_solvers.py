import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.append(str(scripts_dir))

from benchmark_solvers import run_benchmarks, discover_solvers

def test_discover_solvers():
    solvers = discover_solvers()
    assert len(solvers) > 0
    names = [s.__name__ for s in solvers]
    assert "RecipeSolver" in names

def test_run_benchmarks(tmp_path, capsys):
    recipe_content = """
    prep [cost: 2.00, time: 10 min]: 500 g carrots * [cost: 10.00] -> 450 g chopped_carrots;
    make 900 g chopped_carrots;
    """
    recipe_file = tmp_path / "recipe.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")
    
    # run_benchmarks should take a directory of .rf files and run them against discovered solvers
    results = run_benchmarks(tmp_path)
    
    assert len(results) > 0
    # Each result should be for a specific file and solver
    # Using Path name for easier dict keys
    file_result = results["recipe.rf"]
    assert "RecipeSolver" in file_result
    assert file_result["RecipeSolver"]["success"] is True
    assert "time_ms" in file_result["RecipeSolver"]
    
    # Not capturing since run_benchmarks might not print directly, 
    # but the script will print a report.
