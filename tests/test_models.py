import pytest
from resource_flow.models import Resource, Quantity, Process, Query


def test_resource_basics():
    r1 = Resource("eggs", basic=True)
    r2 = Resource("eggs", basic=True)
    r3 = Resource("eggs", basic=False)
    r4 = Resource("flour", basic=True)

    assert r1 == r2
    assert r1 != r3
    assert r1 != r4
    assert hash(r1) == hash(r2)
    assert hash(r1) != hash(r3)
    assert repr(r1) == "eggs (basic)"
    assert repr(r3) == "eggs"


def test_resource_calculate_cost():
    r_no_cost = Resource("water", basic=True)
    assert r_no_cost.calculate_cost(Quantity(100, "l")) == 0.0

    r_cost = Resource("flour", basic=True, cost=0.002, cost_unit="g")
    assert r_cost.calculate_cost(Quantity(500, "g")) == 1.0
    assert r_cost.calculate_cost(Quantity(1.5, "kg")) == 3.0



def test_quantity_basics():
    q = Quantity(2.5, "kg")
    assert repr(q) == "2.5 kg"
    assert q == Quantity(2.5, "kg")
    assert q != Quantity(2.5, "g")


def test_quantity_conversion():
    # Weight conversion
    q_kg = Quantity(1.5, "kg")
    q_g = q_kg.convert_to("g")
    assert q_g.val == 1500.0
    assert q_g.unit == "g"

    q_g2 = Quantity(500, "g")
    q_kg2 = q_g2.convert_to("kg")
    assert q_kg2.val == 0.5
    assert q_kg2.unit == "kg"

    # Volume conversion
    q_l = Quantity(2.0, "l")
    q_ml = q_l.convert_to("ml")
    assert q_ml.val == 2000.0
    assert q_ml.unit == "ml"

    q_ml2 = Quantity(250, "ml")
    q_l2 = q_ml2.convert_to("l")
    assert q_l2.val == 0.25
    assert q_l2.unit == "l"

    # Invalid unit conversion
    with pytest.raises(ValueError, match="Cannot convert unit 'kg' to 'ml'"):
        Quantity(1, "kg").convert_to("ml")


def test_quantity_arithmetic():
    q1 = Quantity(500, "g")
    q2 = Quantity(1.5, "kg")

    # Addition
    res_add = q1 + q2
    assert res_add.val == 2000.0
    assert res_add.unit == "g"

    # Subtraction
    res_sub = q2 - q1
    assert res_sub.val == 1.0
    assert res_sub.unit == "kg"

    # Multiplication
    res_mul1 = q1 * 3
    assert res_mul1.val == 1500.0
    assert res_mul1.unit == "g"

    res_mul2 = 2 * q2
    assert res_mul2.val == 3.0
    assert res_mul2.unit == "kg"

    # Incompatible addition/subtraction
    with pytest.raises(ValueError, match="Incompatible units"):
        _ = q1 + Quantity(10, "ml")

    with pytest.raises(ValueError, match="Incompatible units"):
        _ = q1 - Quantity(10, "ml")


def test_process_basics():
    r_in = Resource("flour", basic=True)
    r_out = Resource("bread", basic=False)
    q_in = Quantity(500, "g")
    q_out = Quantity(1, "piece")

    p = Process("bake_bread", {(q_in, r_in)}, {(q_out, r_out)})
    assert p.name == "bake_bread"
    assert p.inp == {(q_in, r_in)}
    assert p.out == {(q_out, r_out)}
    assert "bake_bread" in repr(p)


def test_query_basics():
    r = Resource("bread", basic=False)
    q = Quantity(2, "piece")

    query = Query({(q, r)})
    assert query.query == {(q, r)}
    assert "Query for" in repr(query)

    # Adding query
    r2 = Resource("butter", basic=True)
    q2 = Quantity(50, "g")
    query2 = Query({(q2, r2)})
    query.add(query2)
    assert query.query == {(q, r), (q2, r2)}
