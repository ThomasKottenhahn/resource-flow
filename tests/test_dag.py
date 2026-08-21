from resource_flow.dag import DAG, DAGEdge, DAGNode
from resource_flow.models import Process, Quantity, Resource


def test_dag_creation_and_node_edge_tracking():
    iron_ore = Resource("iron_ore", basic=True, cost=5.0)
    iron_ingot = Resource("iron_ingot")

    smelt = Process(
        original_label="Smelt Iron",
        inp={(Quantity(2.0, "kg"), iron_ore)},
        out={(Quantity(1.0, "kg"), iron_ingot)},
        cost=10.0,
        time=15.0,
        time_unit="min",
        tags={"smelting", "co2: 2.5"},
    )

    node = DAGNode(process=smelt, scale=3.0)
    edge = DAGEdge(
        source=None,
        target=smelt,
        resource=iron_ore,
        quantity=Quantity(6.0, "kg"),
    )

    dag = DAG(nodes=[node], edges=[edge])

    assert dag.processes == [smelt]
    assert dag.process_scales == {"Smelt Iron": 3.0}


def test_dag_calculate_metric_cost_and_time():
    iron_ore = Resource("iron_ore", basic=True, cost=5.0)
    iron_ingot = Resource("iron_ingot")

    smelt = Process(
        original_label="Smelt Iron",
        inp={(Quantity(2.0, "kg"), iron_ore)},
        out={(Quantity(1.0, "kg"), iron_ingot)},
        cost=10.0,
        time=15.0,
        time_unit="min",
    )

    node = DAGNode(process=smelt, scale=2.0)
    edge = DAGEdge(
        source=None,
        target=smelt,
        resource=iron_ore,
        quantity=Quantity(4.0, "kg"),
    )

    dag = DAG(
        nodes=[node],
        edges=[edge],
    )

    # basic resource cost: 4.0 kg * 5.0 = 20.0; process cost: 10.0 * 2.0 = 20.0 -> total 40.0
    assert dag.calculate_metric("cost") == 40.0

    # process time: 15.0 min * 2.0 = 30.0 min = 1800 s
    assert dag.calculate_metric("time", unit="min") == 30.0
    assert dag.calculate_metric("time", unit="s") == 1800.0


def test_dag_calculate_custom_metric_tags():
    raw_mat = Resource("raw_mat", basic=True, tags={"eco_tax: 0.5"})
    prod = Resource("prod")

    proc = Process(
        original_label="Make Product",
        inp={(Quantity(1.0, "kg"), raw_mat)},
        out={(Quantity(1.0, "kg"), prod)},
        tags={"manual", "co2: 3.0"},
    )

    node = DAGNode(process=proc, scale=4.0)
    edge = DAGEdge(
        source=None,
        target=proc,
        resource=raw_mat,
        quantity=Quantity(4.0, "kg"),
    )

    dag = DAG(
        nodes=[node],
        edges=[edge],
    )


    # flag tag count: 'manual' present in proc -> 1.0
    assert dag.calculate_metric("manual") == 1.0

    # numerical tag: co2: 3.0 * scale 4.0 = 12.0
    assert dag.calculate_metric("co2") == 12.0

    # resource tag: eco_tax: 0.5 * qty 4.0 = 2.0
    assert dag.calculate_metric("eco_tax") == 2.0


def test_dag_calculate_custom_metric_unit_conversion():
    prod = Resource("prod")
    proc = Process(
        original_label="Make Product",
        inp=set(),
        out={(Quantity(1.0, "kg"), prod)},
        tags={"co2: 12500.0"},
    )
    node = DAGNode(process=proc, scale=1.0)
    dag = DAG(nodes=[node], edges=[])

    assert dag.calculate_metric("co2") == 12500.0
    assert dag.calculate_metric("co2", unit="kg") == 12.5

