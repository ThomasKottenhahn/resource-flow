import pytest
from unittest.mock import patch
from resource_flow.cli import main


def test_cli_console_output(tmp_path, capsys):
    recipe_content = """
    prep [cost: 2.00, time: 10 min]: 500 g carrots * [cost: 10.00] -> 450 g chopped_carrots;
    make 900 g chopped_carrots;
    """
    recipe_file = tmp_path / "recipe.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    test_args = ["rflow", str(recipe_file), "--time-unit", "h"]
    with patch("sys.argv", test_args):
        main()

    captured = capsys.readouterr().out
    assert "Solving Recipe..." in captured
    assert "Step 1: prep (Scale: 2.0000, Cost: 4.00, Time: 20.00 min)" in captured
    assert "Total Time:    0.33 h" in captured
    assert "Mermaid Visualization:" in captured
    assert "Metrics Summary" in captured


def test_cli_file_output_dir(tmp_path):
    recipe_content = """
    prep [cost: 2.00, time: 15 min]: 500 g carrots * -> 450 g chopped_carrots;
    make 450 g chopped_carrots;
    """
    recipe_file = tmp_path / "recipe.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    out_dir = tmp_path / "output_dir"
    out_dir.mkdir()
    test_args = ["rflow", str(recipe_file), "-o", str(out_dir)]
    with patch("sys.argv", test_args):
        main()

    plan_file = out_dir / "plan.txt"
    mermaid_file = out_dir / "flow.mermaid"

    assert plan_file.exists()
    assert mermaid_file.exists()

    plan_content = plan_file.read_text(encoding="utf-8")
    mermaid_content = mermaid_file.read_text(encoding="utf-8")

    assert "=== RECIPE EXECUTION PLAN ===" in plan_content
    assert "=== METRICS SUMMARY ===" in plan_content
    assert "```mermaid" in mermaid_content


def test_cli_file_output_prefix(tmp_path):
    recipe_content = """
    prep [cost: 2.00, time: 15 min]: 500 g carrots * -> 450 g chopped_carrots;
    make 450 g chopped_carrots;
    """
    recipe_file = tmp_path / "recipe.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    out_prefix = tmp_path / "my_recipe"
    test_args = ["rflow", str(recipe_file), "-o", str(out_prefix)]
    with patch("sys.argv", test_args):
        main()

    plan_file = tmp_path / "my_recipe_plan.txt"
    mermaid_file = tmp_path / "my_recipe_flow.mermaid"

    assert plan_file.exists()
    assert mermaid_file.exists()
