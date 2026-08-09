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


def test_parser_with_tags_and_metrics(tmp_path):
    recipe_content = """
    cut_carrots [cost: 1.50, time: 10 min, manual]: 500 g carrots * [cost: 2.00, !cut, organic] -> 450 g carrots [cut, organic];
    make 450 g carrots [cut];
    """
    recipe_file = tmp_path / "test_tags.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    resources, processes, query = parser.parse_file(str(recipe_file))

    proc = list(processes)[0]
    assert proc.name == "cut_carrots"
    assert proc.cost == 1.50
    assert proc.time == 10.0
    assert proc.time_unit == "min"
    assert proc.tags == frozenset({"manual"})

    q_in, r_in = list(proc.inp)[0]
    assert r_in.name == "carrots"
    assert r_in.basic is True
    assert r_in.cost == pytest.approx(2.00 / 500.0)
    assert r_in.cost_unit == "g"
    assert r_in.tags == frozenset({"organic", "basic"})
    assert r_in.negated_tags == frozenset({"cut"})

    q_out, r_out = list(proc.out)[0]
    assert r_out.name == "carrots"
    assert r_out.tags == frozenset({"cut", "organic"})


def test_parser_basic_as_tag(tmp_path):
    recipe_content = "100 g flour [basic] -> 100 g dough; make 100 g dough;"
    recipe_file = tmp_path / "test_basic_tag.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    resources, processes, query = parser.parse_file(str(recipe_file))

    proc = list(processes)[0]
    q_in, r_in = list(proc.inp)[0]
    assert r_in.name == "flour"
    assert r_in.basic is True
    assert "basic" in r_in.tags



from lark.exceptions import VisitError


def test_resource_time_tag_forbidden(tmp_path):
    recipe_content = "cut: 100 g A [time: 5 min] -> 100 g B; make 100 g B;"
    recipe_file = tmp_path / "test_invalid_tag.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    with pytest.raises((ValueError, VisitError), match="Resources cannot have a time tag"):
        parser.parse_file(str(recipe_file))


def test_parser_multiple_positive_and_negated_tags(tmp_path):
    recipe_content = """
    prep [cost: 5.00, time: 20 min, automated]: 1 kg apples * [organic, local, !frozen, !sliced] -> 900 g apples [cut, organic, local];
    make 900 g apples [cut, organic];
    """
    recipe_file = tmp_path / "test_multi_tags.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    resources, processes, query = parser.parse_file(str(recipe_file))

    proc = list(processes)[0]
    assert proc.name == "prep"
    assert proc.cost == 5.00
    assert proc.time == 20.0
    assert proc.time_unit == "min"
    assert proc.tags == frozenset({"automated"})

    q_in, r_in = list(proc.inp)[0]
    assert r_in.name == "apples"
    assert r_in.basic is True
    assert r_in.tags == frozenset({"organic", "local", "basic"})
    assert r_in.negated_tags == frozenset({"frozen", "sliced"})

    q_out, r_out = list(proc.out)[0]
    assert r_out.name == "apples"
    assert r_out.tags == frozenset({"cut", "organic", "local"})
    assert len(r_out.negated_tags) == 0

    q_q, r_q = list(query.query)[0]
    assert r_q.name == "apples"
    assert r_q.tags == frozenset({"cut", "organic"})


def test_batch_cost_normalization_parsing(tmp_path):
    recipe_content = "prep: 300 g carrots * [cost: 20.00] -> 280 g peeled_carrots; make 280 g peeled_carrots;"
    recipe_file = tmp_path / "test_batch_cost.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    resources, processes, query = parser.parse_file(str(recipe_file))

    proc = list(processes)[0]
    q_in, r_in = list(proc.inp)[0]
    assert r_in.name == "carrots"
    assert r_in.basic is True
    # 20.00 for 300g = 0.06666... per g
    assert r_in.cost == pytest.approx(20.00 / 300.0)
    assert r_in.cost_unit == "g"


def test_non_basic_resource_cost_forbidden(tmp_path):
    recipe_content = "prep: 300 g carrots [cost: 20.00] -> 280 g peeled_carrots; make 280 g peeled_carrots;"
    recipe_file = tmp_path / "test_non_basic_cost.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    with pytest.raises((ValueError, VisitError), match="Cost can only be specified on basic resources"):
        parser.parse_file(str(recipe_file))


def test_parse_general_goals(tmp_path):
    from resource_flow.models import AggregateGoal, RelationalGoal

    recipe_content = """
    100 g A -> 100 g B;
    [min manual_labour, max throughput, cost <= 10, time < 30 min, cheapest] make 100 g B;
    """
    recipe_file = tmp_path / "test_goals.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    _, _, query = parser.parse_file(str(recipe_file))

    assert query.goals == (
        AggregateGoal("min", "manual_labour"),
        AggregateGoal("max", "throughput"),
        RelationalGoal("cost", "<=", 10.0, None),
        RelationalGoal("time", "<", 30.0, "min"),
        AggregateGoal("min", "cost"),
    )


def test_parser_tools(tmp_path):
    from resource_flow.models import Tool
    recipe_content = """
    cut: 500 g carrots * -> 450 g carrots [cut] with knife, 2 piece clamp;
    make 1 kg cake using knife, oven, 2 oven_mits;
    """
    recipe_file = tmp_path / "test_tools.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    resources, processes, query = parser.parse_file(str(recipe_file))

    assert len(processes) == 1
    proc = list(processes)[0]
    assert proc.name == "cut"
    
    assert proc.tools == frozenset({
        Tool("knife", Quantity(1.0, "piece")),
        Tool("clamp", Quantity(2.0, "piece"))
    })
    
    assert query.tools == frozenset({
        Tool("knife", Quantity(1.0, "piece")),
        Tool("oven", Quantity(1.0, "piece")),
        Tool("oven_mits", Quantity(2.0, "piece"))
    })
