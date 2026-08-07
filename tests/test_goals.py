import pytest
from resource_flow.dag import DAG, DAGNode, DAGEdge
from resource_flow.models import (
    AggregateGoal,
    AnyGoal,
    Goal,
    Process,
    Quantity,
    Query,
    RelationalGoal,
    Resource,
)


def test_goal_base_and_any_goal():
    goal = AnyGoal()
    assert isinstance(goal, Goal)
    assert goal.evaluate(DAG()) == 0.0
    assert repr(goal) == "any"
    assert goal == "any"


def test_aggregate_goal_evaluate():
    proc = Process(
        name="P1",
        inp=set(),
        out=set(),
        cost=10.0,
        time=20.0,
        time_unit="min",
        tags={"co2: 5.0"},
    )
    dag = DAG(nodes=[DAGNode(process=proc, scale=2.0)])

    min_cost = AggregateGoal("min", "cost")
    max_co2 = AggregateGoal("max", "co2")

    # min cost: proc.cost 10 * scale 2 = 20.0
    assert min_cost.evaluate(dag) == 20.0

    # max co2: co2 5 * scale 2 = 10.0 -> max returns -10.0 for sorting
    assert max_co2.evaluate(dag) == -10.0


def test_relational_goal_evaluate():
    proc = Process(
        name="P1",
        inp=set(),
        out=set(),
        cost=10.0,
        time=30.0,
        time_unit="min",
    )
    dag = DAG(nodes=[DAGNode(process=proc, scale=1.0)])

    time_under_40 = RelationalGoal("time", "<=", 40.0, unit="min")
    time_under_20 = RelationalGoal("time", "<=", 20.0, unit="min")

    assert time_under_40.evaluate(dag) is True
    assert time_under_20.evaluate(dag) is False


def test_query_normalizes_string_goals_to_goal_objects():
    q = Query(
        query=set(),
        goals=["cheapest", "fastest", "any", "co2"],
    )

    assert isinstance(q.goals[0], AggregateGoal)
    assert q.goals[0].op == "min" and q.goals[0].tag == "cost"

    assert isinstance(q.goals[1], AggregateGoal)
    assert q.goals[1].op == "min" and q.goals[1].tag == "time"

    assert isinstance(q.goals[2], AnyGoal)

    assert isinstance(q.goals[3], AggregateGoal)
    assert q.goals[3].op == "min" and q.goals[3].tag == "co2"
