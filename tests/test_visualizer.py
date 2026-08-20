import io
import sys

from resource_flow.dag import DAG, DAGEdge, DAGNode
from resource_flow.models import Process, Quantity, Query, Resource, Tool
from resource_flow.visualization import Visualizer


def _make_simple_dag():
    """Single-process DAG: smelt iron_ore -> iron_ingot."""
    iron_ore = Resource("iron_ore", basic=True, cost=5.0)
    iron_ingot = Resource("iron_ingot")

    smelt = Process(
        name="smelt",
        inp={(Quantity(2.0, "kg"), iron_ore)},
        out={(Quantity(1.0, "kg"), iron_ingot)},
        cost=10.0,
        time=15.0,
        time_unit="min",
    )

    node = DAGNode(process=smelt, scale=2.0)
    # basic input edge
    edge_in = DAGEdge(
        source=None,
        target=smelt,
        resource=iron_ore,
        quantity=Quantity(4.0, "kg"),
    )
    # query output edge
    query_res = Resource("iron_ingot")
    edge_out = DAGEdge(
        source=smelt,
        target="Query",
        resource=iron_ingot,
        quantity=Quantity(2.0, "kg"),
    )

    dag = DAG(nodes=[node], edges=[edge_in, edge_out])
    demands = {"iron_ore": Quantity(4.0, "kg")}
    surplus: dict[str, Quantity] = {}
    basic_resources = {"iron_ore": [iron_ore]}
    query = Query(query={(Quantity(2.0, "kg"), query_res)})
    return dag, demands, surplus, basic_resources, query, smelt


def test_visualizer_get_metrics():
    dag, demands, surplus, basic_resources, query, smelt = _make_simple_dag()
    viz = Visualizer(dag, demands, surplus, basic_resources, query)

    metrics = viz.get_metrics(time_unit="min")

    # resource cost: 4.0 kg * 5.0/kg = 20.0
    assert metrics["resource_cost"] == 20.0
    # process cost: 10.0 * 2.0 = 20.0
    assert metrics["process_cost"] == 20.0
    assert metrics["total_cost"] == 40.0
    # time: 15.0 min * 2.0 = 30.0
    assert metrics["total_time"] == 30.0
    assert metrics["time_unit"] == "min"


def test_visualizer_print_plan_contains_step_and_resource():
    dag, demands, surplus, basic_resources, query, smelt = _make_simple_dag()
    viz = Visualizer(dag, demands, surplus, basic_resources, query)

    captured = io.StringIO()
    sys.stdout = captured
    try:
        viz.print_plan(time_unit="min")
    finally:
        sys.stdout = sys.__stdout__

    output = captured.getvalue()
    assert "Step 1: smelt" in output
    assert "iron_ore *" in output
    assert "TOTAL BASIC RESOURCES REQUIRED" in output
    assert "METRICS SUMMARY" in output
    assert "30.00 min" in output


def test_visualizer_generate_mermaid_structure():
    dag, demands, surplus, basic_resources, query, smelt = _make_simple_dag()
    viz = Visualizer(dag, demands, surplus, basic_resources, query)

    mermaid = viz.generate_mermaid(time_unit="min")

    assert "```mermaid" in mermaid
    assert "graph TD" in mermaid
    assert 'smelt["smelt' in mermaid
    assert 'basic_iron_ore[' in mermaid
    assert 'Query["Query:' in mermaid
    assert "Metrics Summary" in mermaid
    assert "```" in mermaid


def test_visualizer_with_tools():
    iron_ore = Resource("iron_ore", basic=True, cost=5.0)
    iron_ingot = Resource("iron_ingot")

    smelt = Process(
        name="smelt",
        inp={(Quantity(2.0, "kg"), iron_ore)},
        out={(Quantity(1.0, "kg"), iron_ingot)},
        tools={Tool("furnace", Quantity(1.0, "piece"))},
        cost=10.0,
        time=15.0,
        time_unit="min",
    )

    node = DAGNode(process=smelt, scale=1.0)
    dag = DAG(nodes=[node], edges=[])
    demands = {"iron_ore": Quantity(2.0, "kg")}
    surplus: dict[str, Quantity] = {}
    basic_resources = {"iron_ore": [iron_ore]}
    query = Query(query={(Quantity(1.0, "kg"), iron_ingot)})

    viz = Visualizer(dag, demands, surplus, basic_resources, query)

    # Test print_plan
    captured = io.StringIO()
    sys.stdout = captured
    try:
        viz.print_plan(time_unit="min")
    finally:
        sys.stdout = sys.__stdout__

    output = captured.getvalue()
    assert "Tools: 1.0 piece furnace" in output

    # Test generate_mermaid
    mermaid = viz.generate_mermaid(time_unit="min")
    assert "using 1.0 piece furnace" in mermaid
