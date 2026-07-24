import pytest
from resource_flow.parser import RecipeParser
from resource_flow.models import Process, Query, Quantity, Resource


def test_parser_with_simple_recipe(tmp_path):
    recipe_content = """
    peel: 300 g carrots * -> 280 g peeled_carrots;
    cook: 280 g peeled_carrots, 500 ml water * -> 700 g carrot_soup;
    make 700 g carrot_soup;
    """
    recipe_file = tmp_path / "test_recipe.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    resources, processes, query = parser.parse_file(str(recipe_file))

    # Verify processes
    assert len(processes) == 2
    process_names = {p.name for p in processes}
    assert process_names == {"peel", "cook"}

    peel_proc = next(p for p in processes if p.name == "peel")
    assert len(peel_proc.inp) == 1
    assert len(peel_proc.out) == 1

    # Verify basic resource check
    q_in, r_in = list(peel_proc.inp)[0]
    assert r_in.name == "carrots"
    assert r_in.basic is True
    assert q_in == Quantity(300.0, "g")

    q_out, r_out = list(peel_proc.out)[0]
    assert r_out.name == "peeled_carrots"
    assert r_out.basic is False
    assert q_out == Quantity(280.0, "g")

    # Verify query
    assert isinstance(query, Query)
    assert len(query.query) == 1
    q_target, r_target = list(query.query)[0]
    assert r_target.name == "carrot_soup"
    assert r_target.basic is False
    assert q_target == Quantity(700.0, "g")


def test_parser_with_no_labels(tmp_path):
    recipe_content = "100 g A -> 100 g B; make 100 g B;"
    recipe_file = tmp_path / "test_no_labels.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    resources, processes, query = parser.parse_file(str(recipe_file))

    assert len(processes) == 1
    proc = list(processes)[0]
    assert proc.name == ""  # No label
