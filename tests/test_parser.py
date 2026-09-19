import pytest
from resource_flow.parser import RecipeParser
from resource_flow.models import Process, Query, Quantity, Resource, ConvertStatement


def test_parser_with_simple_recipe(tmp_path):
    recipe_content = """
    peel: 300 g carrots * -> 280 g peeled_carrots;
    cook: 280 g peeled_carrots, 500 ml water * -> 700 g carrot_soup;
    make 700 g carrot_soup;
    """
    recipe_file = tmp_path / "test_recipe.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    resources, processes, query = ctx.resources, ctx.processes, ctx.query

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



def test_parser_with_tags_and_metrics(tmp_path):
    recipe_content = """
    cut_carrots [cost: 1.50, time: 10 min, manual]: 500 g carrots * [cost: 2.00, !cut, organic] -> 450 g carrots [cut, organic];
    make 450 g carrots [cut];
    """
    recipe_file = tmp_path / "test_tags.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    resources, processes, query = ctx.resources, ctx.processes, ctx.query

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
    recipe_content = "P1: 100 g flour [basic] -> 100 g dough; make 100 g dough;"
    recipe_file = tmp_path / "test_basic_tag.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    resources, processes, query = ctx.resources, ctx.processes, ctx.query

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
    ctx = parser.parse_file(str(recipe_file))
    resources, processes, query = ctx.resources, ctx.processes, ctx.query

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
    ctx = parser.parse_file(str(recipe_file))
    resources, processes, query = ctx.resources, ctx.processes, ctx.query

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
    with pytest.raises((ValueError, VisitError), match="Non-basic resource 'carrots' cannot have a cost in a transition."):
        parser.parse_file(str(recipe_file))


def test_parse_general_goals(tmp_path):
    from resource_flow.models import AggregateGoal, RelationalGoal

    recipe_content = """
    P1: 100 g A -> 100 g B;
    [min manual_labour, max throughput, cost <= 10, time < 30 min, cheapest] make 100 g B;
    """
    recipe_file = tmp_path / "test_goals.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    query = ctx.query

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
    ctx = parser.parse_file(str(recipe_file))
    resources, processes, query = ctx.resources, ctx.processes, ctx.query

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


def test_module_processes_not_in_scope(tmp_path):
    recipe_content = """
    mod prep {
        peel: 300 g carrots * -> 280 g peeled_carrots;
    }
    cook: 280 g peeled_carrots -> 700 g carrot_soup;
    make 700 g carrot_soup;
    """
    recipe_file = tmp_path / "test_module.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    resources, processes, query = ctx.resources, ctx.processes, ctx.query
    
    # process inside module should not be in the returned set
    assert len(processes) == 1
    assert list(processes)[0].name == "cook"


def test_module_processes_with_import_all(tmp_path):
    recipe_content = """
    mod prep {
        peel: 300 g carrots * -> 280 g peeled_carrots;
    }
    use prep;
    cook: 280 g peeled_carrots -> 700 g carrot_soup;
    make 700 g carrot_soup;
    """
    recipe_file = tmp_path / "test_module_use_all.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    resources, processes, query = ctx.resources, ctx.processes, ctx.query
    
    assert len(processes) == 2
    process_names = {p.name for p in processes}
    assert process_names == {"prep::peel", "cook"}
    
    peel_proc = next(p for p in processes if p.name == "prep::peel")
    assert peel_proc.fully_qualified_label == "prep::peel"
    assert peel_proc.original_label == "peel"


def test_module_processes_with_import_specific(tmp_path):
    recipe_content = """
    mod prep {
        peel: 300 g carrots * -> 280 g peeled_carrots;
        chop: 280 g peeled_carrots -> 280 g chopped_carrots;
    }
    use prep::{peel};
    make 700 g carrot_soup;
    """
    recipe_file = tmp_path / "test_module_use_specific.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    resources, processes, query = ctx.resources, ctx.processes, ctx.query
    
    assert list(processes)[0].name == "prep::peel"

def test_let_macro_multiset(tmp_path):
    recipe_content = """
    let veggies = 300 g carrots, 200 g potatoes;
    prep: veggies -> 450 g chopped_veggies;
    make 450 g chopped_veggies;
    """
    recipe_file = tmp_path / "test_let.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    
    assert len(ctx.processes) == 1
    proc = list(ctx.processes)[0]
    assert proc.name == "prep"
    assert len(proc.inp) == 2
    names = {res.name for qty, res in proc.inp}
    assert names == {"carrots", "potatoes"}


def test_let_macro_reassignment(tmp_path):
    recipe_content = """
    let veggies = 300 g carrots;
    let veggies = 200 g potatoes;
    """
    recipe_file = tmp_path / "test_let_reassign.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    with pytest.raises((ValueError, VisitError), match="Macro 'veggies' is already defined."):
        parser.parse_file(str(recipe_file))


def test_let_macro_use_before_decl_succeeds(tmp_path):
    recipe_content = """
    prep: veggies -> 450 g chopped_veggies;
    let veggies = 300 g carrots, 200 g potatoes;
    """
    recipe_file = tmp_path / "test_let_use_before_decl.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    p = next(p for p in ctx.processes if p.name == "prep")
    assert len(p.inp) == 2
    res_names = {res.name for qty, res in p.inp}
    assert "carrots" in res_names
    assert "potatoes" in res_names

def test_let_macro_undefined(tmp_path):
    recipe_content = """
    prep: veggies -> 450 g chopped_veggies;
    """
    recipe_file = tmp_path / "test_let_undefined.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    with pytest.raises(ValueError, match="Macro 'veggies' is used before declaration or not defined."):
        parser.parse_file(str(recipe_file))

def test_module_exports(tmp_path):
    mod_content = """
    def 1 kg potatoes *;
    let veggies = 1 kg potatoes;
    """
    mod_file = tmp_path / "supplier.rf"
    mod_file.write_text(mod_content, encoding="utf-8")

    main_content = """
    use "supplier.rf";
    prep: veggies -> 1 kg chopped_veggies;
    """
    main_file = tmp_path / "main.rf"
    main_file.write_text(main_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(main_file))
    
    # Verify the def was exported and made available as a basic resource
    assert any(d.name == "potatoes" and d.basic for d in ctx.defs)
    
    # Verify the macro was exported and evaluated
    p = next(p for p in ctx.processes if p.name == "prep")
    assert any(res.name == "potatoes" for qty, res in p.inp)

def test_inline_module_exports(tmp_path):
    recipe_content = """
    mod supplier {
        def 1 kg potatoes *;
        let veggies = 1 kg potatoes;
    }
    use supplier;
    prep: veggies -> 1 kg chopped_veggies;
    """
    recipe_file = tmp_path / "test_inline_exports.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    
    assert any(d.name == "potatoes" and d.basic for d in ctx.defs)
    p = next(p for p in ctx.processes if p.name == "prep")
    assert any(res.name == "potatoes" for qty, res in p.inp)

def test_selective_module_exports(tmp_path):
    recipe_content = """
    mod supplier {
        def 1 kg potatoes *;
        let veggies = 1 kg potatoes;
        let meat = 1 kg beef;
    }
    use supplier::{veggies};
    prep: veggies -> 1 kg chopped_veggies;
    """
    recipe_file = tmp_path / "test_selective_exports.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    
    # We selectively imported `veggies`, so `veggies` should evaluate properly
    p = next(p for p in ctx.processes if p.name == "prep")
    assert any(res.name == "potatoes" for qty, res in p.inp)
    
    # We did not import `meat`, so using it should fail
    bad_content = recipe_content + "\nbad: meat -> 1 kg cooked_meat;"
    bad_file = tmp_path / "test_bad.rf"
    bad_file.write_text(bad_content, encoding="utf-8")
    
    with pytest.raises(ValueError, match="Macro 'meat' is used before declaration or not defined."):
        parser.parse_file(str(bad_file))

def test_cyclic_macro_definition(tmp_path):
    recipe_content = """
    let a = b;
    let b = a;
    prep: a -> 1 kg done;
    """
    recipe_file = tmp_path / "test_cycle.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")

    parser = RecipeParser()
    with pytest.raises(ValueError, match="Cyclic macro definition detected: (a -> b -> a|b -> a -> b)"):
        parser.parse_file(str(recipe_file))

def test_parse_supplier(tmp_path):
    recipe_content = "def 300g carrots at Lidl;"
    recipe_file = tmp_path / "test.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")
    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    
    assert len(ctx.defs) == 1
    d = ctx.defs[0]
    assert d.supplier == "Lidl"
    assert d.name == "carrots"
    assert d.quantity == Quantity(300.0, "g")

def test_parse_module_headers(tmp_path):
    recipe_content = "mod Lidl_Store [organic] at Lidl { def 300g carrots; }"
    recipe_file = tmp_path / "test.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")
    parser = RecipeParser()
    ctx = parser.parse_file(str(recipe_file))
    
    assert len(ctx.defs) == 1
    d = ctx.defs[0]
    assert d.supplier == "Lidl"
    assert "organic" in d.resource.tags

def test_parse_macro_def(tmp_path):
    recipe_content = "let x = 5 kg apples;"
    recipe_file = tmp_path / "test.rf"
    recipe_file.write_text(recipe_content, encoding="utf-8")
    parser = RecipeParser()
    ctx = parser._parse_file_internal(str(recipe_file), {})
    
    assert "x" in ctx.macros

def test_relative_import_parsing(tmp_path):
    # Create a local file to import in a subdirectory
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    local_mod = subdir / "local.rf"
    local_mod.write_text("def 1 piece imported_resource;")

    main_mod = tmp_path / "main.rf"
    main_mod.write_text('use ./subdir/local;')

    parser = RecipeParser()
    prog = parser.parse_file(str(main_mod))
    
    assert any(r.name == "imported_resource" for r in prog.resources)

def test_negated_tags():
    parser = RecipeParser()
    prog = parser.parse_string('def 1 piece apple [!discrete];', "virtual.rf")
    res = list(prog.resources)[0]
    assert "discrete" in res.negated_tags

def test_unit_less_quantities():
    parser = RecipeParser()
    prog = parser.parse_string('def 10 apple *;', "virtual.rf")
    assert len(prog.defs) == 1
    d = prog.defs[0]
    assert d.quantity.val == 10
    assert d.quantity.unit == "piece"

def test_currency_in_costs():
    parser = RecipeParser()
    prog = parser.parse_string('def 1 piece apple * [cost: 10 USD];', "virtual.rf")
    res = list(prog.resources)[0]
    assert res.cost == 10.0
    assert res.cost_currency == "USD"
    
    prog2 = parser.parse_string('def 1 piece banana * [cost: 5 €];', "virtual.rf")
    res2 = list(prog2.resources)[0]
    assert res2.cost == 5.0
    assert res2.cost_currency == "€"

def test_convert_stmt():
    parser = RecipeParser()
    prog = parser.parse_string('convert 1 € = 7.48 DKK;', "virtual.rf")
    assert len(prog.converts) == 1
    c = prog.converts[0]
    assert c.from_qty == Quantity(1.0, "€")
    assert c.to_qty == Quantity(7.48, "DKK")
