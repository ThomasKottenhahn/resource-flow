import pytest
from resource_flow.parser import RecipeParser
from resource_flow.solvers import RecipeSolver

def test_default_base_currency(tmp_path):
    main_file = tmp_path / "main.rf"
    main_file.write_text("""
    convert 1 EUR = 7.5 DKK;
    convert 1 USD = 0.9 EUR;
    
    def 1 piece A [cost: 10 DKK];
    make 1 piece A;
    """, encoding="utf-8")
    parser = RecipeParser()
    ctx = parser.parse_file(str(main_file))
    
    # Base currency should be EUR (first LHS)
    assert ctx.converts[0].from_qty.unit == "EUR"
    
    # 10 DKK -> EUR = 10 / 7.5 = 1.333...
    resource_A = next(d.resource for d in ctx.defs if d.resource.name == "A")
    assert resource_A.cost_currency == "EUR"
    assert pytest.approx(resource_A.cost, 0.001) == 10 / 7.5

def test_mixed_currency_evaluation(tmp_path):
    main_file = tmp_path / "main.rf"
    main_file.write_text("""
    convert 1 DKK = 0.13 EUR;
    convert 1 DKK = 0.15 USD;
    
    def 1 piece A [cost: 100 DKK];
    def 1 piece B [cost: 2 EUR];
    def 1 piece C [cost: 1 USD];
    
    make 1 piece A;
    make 1 piece B;
    make 1 piece C;
    """, encoding="utf-8")
    parser = RecipeParser()
    ctx = parser.parse_file(str(main_file))
    
    # Base is DKK
    assert ctx.converts[0].from_qty.unit == "DKK"
    
    res_A = next(d.resource for d in ctx.defs if d.resource.name == "A")
    res_B = next(d.resource for d in ctx.defs if d.resource.name == "B")
    res_C = next(d.resource for d in ctx.defs if d.resource.name == "C")
    
    assert res_A.cost_currency == "DKK"
    assert res_B.cost_currency == "DKK"
    assert res_C.cost_currency == "DKK"
    
    assert pytest.approx(res_A.cost, 0.001) == 100.0
    assert pytest.approx(res_B.cost, 0.001) == 2.0 / 0.13
    assert pytest.approx(res_C.cost, 0.001) == 1.0 / 0.15

def test_missing_conversions_throws(tmp_path):
    main_file = tmp_path / "main.rf"
    main_file.write_text("""
    convert 1 A = 2 B;
    
    def 1 piece X [cost: 10 A];
    def 1 piece Y [cost: 10 C];
    """, encoding="utf-8")
    parser = RecipeParser()
    with pytest.raises(ValueError, match="Missing conversion for currency 'C' to base currency 'A'."):
        parser.parse_file(str(main_file))

def test_missing_conversions_no_convert_statements_throws(tmp_path):
    main_file = tmp_path / "main.rf"
    main_file.write_text("""
    def 1 piece X [cost: 10 A];
    def 1 piece Y [cost: 10 B];
    """, encoding="utf-8")
    parser = RecipeParser()
    with pytest.raises(ValueError, match="Multiple currencies used but no convert statements provided."):
        parser.parse_file(str(main_file))

def test_cyclical_conversions_handled(tmp_path):
    main_file = tmp_path / "main.rf"
    main_file.write_text("""
    convert 1 A = 2 B;
    convert 1 B = 0.5 A;
    
    def 1 piece X [cost: 10 B];
    """, encoding="utf-8")
    parser = RecipeParser()
    ctx = parser.parse_file(str(main_file))
    
    # Base is A
    assert ctx.converts[0].from_qty.unit == "A"
    
    res_X = next(d.resource for d in ctx.defs if d.resource.name == "X")
    assert res_X.cost_currency == "A"
    # 10 B = 5 A (since 1 A = 2 B, 1 B = 0.5 A)
    assert pytest.approx(res_X.cost, 0.001) == 5.0
