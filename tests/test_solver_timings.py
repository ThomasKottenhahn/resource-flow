import pytest
from datetime import datetime, timedelta
from resource_flow.models import (
    Query, Resource, Process, Quantity, TimelineSchedule, 
    ProgramContext, CalendarBlock, WorkWindow, MapBlock, TravelEdge, ShoppingHeuristic
)
from resource_flow.solvers import Solver
from resource_flow.solvers.exceptions import InfeasibleScheduleError

def _make_ctx(processes, queries, calendar_block=None, map_block=None):
    return ProgramContext(
        processes=set(processes),
        resources=set(),
        queries=queries,
        defs=[],
        calendar_block=calendar_block or CalendarBlock([]),
        map_block=map_block or MapBlock([], [])
    )

def test_single_bounded_process():
    # 1. Schedule a 2-hour process within a 4-hour `calendar` block.
    # Why: Verifies basic valid placement logic.
    res = Resource("out")
    p = Process("p1", inp=set(), out={(Quantity(1, "kg"), res)}, time=2.0, time_unit="h")
    q = Query({(Quantity(1, "kg"), res)}, deadline=datetime(2023, 1, 1, 12, 0))
    
    # 4-hour block from 8:00 to 12:00
    win = WorkWindow(start_time=datetime.strptime("08:00", "%H:%M").time(), end_time=datetime.strptime("12:00", "%H:%M").time())
    cal = CalendarBlock([win])
    ctx = _make_ctx([p], [q], calendar_block=cal)
    
    solver = Solver(ctx)
    schedule = solver.solve()
    assert isinstance(schedule, TimelineSchedule)
    
    start, end = schedule.process_times["p1"]
    assert end <= q.deadline
    assert (end - start).total_seconds() == 2 * 3600

def test_two_dependent_processes():
    # 2. Schedule Process A then Process B.
    # Why: Verifies topological sort and chronological enforcement.
    res_a = Resource("A")
    res_b = Resource("B")
    
    p_a = Process("p_a", inp=set(), out={(Quantity(1, "kg"), res_a)}, time=1.0, time_unit="h")
    p_b = Process("p_b", inp={(Quantity(1, "kg"), res_a)}, out={(Quantity(1, "kg"), res_b)}, time=1.0, time_unit="h")
    
    q = Query({(Quantity(1, "kg"), res_b)}, deadline=datetime(2023, 1, 1, 12, 0))
    ctx = _make_ctx([p_a, p_b], [q])
    
    solver = Solver(ctx)
    schedule = solver.solve()
    assert isinstance(schedule, TimelineSchedule)
    
    start_a, end_a = schedule.process_times["p_a"]
    start_b, end_b = schedule.process_times["p_b"]
    assert end_a <= start_b

def test_sequential_active_processes():
    # 3. Schedule two independent active processes.
    # Why: Verifies the solver enforces global sequential constraints for active processes.
    res_a = Resource("A")
    res_b = Resource("B")
    res_out = Resource("Out")
    
    p_a = Process("p_a", inp=set(), out={(Quantity(1, "kg"), res_a)}, time=1.0, time_unit="h")
    p_b = Process("p_b", inp=set(), out={(Quantity(1, "kg"), res_b)}, time=1.0, time_unit="h")
    p_c = Process("p_c", inp={(Quantity(1, "kg"), res_a), (Quantity(1, "kg"), res_b)}, out={(Quantity(1, "kg"), res_out)}, time=1.0, time_unit="h")
    
    q = Query({(Quantity(1, "kg"), res_out)}, deadline=datetime(2023, 1, 1, 12, 0))
    ctx = _make_ctx([p_a, p_b, p_c], [q])
    
    solver = Solver(ctx)
    schedule = solver.solve()
    assert isinstance(schedule, TimelineSchedule)
    
    start_a, end_a = schedule.process_times["p_a"]
    start_b, end_b = schedule.process_times["p_b"]
    
    # Active processes must not overlap
    assert end_a <= start_b or end_b <= start_a

def test_parallel_passive_processes():
    # 3b. Schedule two independent passive processes.
    # Why: Verifies the solver allows [passive] processes to overlap.
    from resource_flow.models import ExecutionType
    res_a = Resource("A")
    res_b = Resource("B")
    res_out = Resource("Out")
    
    p_a = Process("p_a", inp=set(), out={(Quantity(1, "kg"), res_a)}, time=1.0, time_unit="h", execution_type=ExecutionType.PASSIVE)
    p_b = Process("p_b", inp=set(), out={(Quantity(1, "kg"), res_b)}, time=1.0, time_unit="h", execution_type=ExecutionType.PASSIVE)
    p_c = Process("p_c", inp={(Quantity(1, "kg"), res_a), (Quantity(1, "kg"), res_b)}, out={(Quantity(1, "kg"), res_out)}, time=1.0, time_unit="h")
    
    q = Query({(Quantity(1, "kg"), res_out)}, deadline=datetime(2023, 1, 1, 12, 0))
    ctx = _make_ctx([p_a, p_b, p_c], [q])
    
    solver = Solver(ctx)
    schedule = solver.solve()
    assert isinstance(schedule, TimelineSchedule)
    
    start_a, end_a = schedule.process_times["p_a"]
    start_b, end_b = schedule.process_times["p_b"]
    
    # In ALAP scheduling, they should be scheduled at the exact same time
    assert end_a == end_b

def test_unsupervised_process_outside_hours():
    # 3c. Schedule an unsupervised process that takes 10 hours overnight.
    # Why: Verifies unsupervised processes do not snap to calendar blocks.
    from resource_flow.models import ExecutionType
    res_a = Resource("A")
    
    p_a = Process("p_a", inp=set(), out={(Quantity(1, "kg"), res_a)}, time=10.0, time_unit="h", execution_type=ExecutionType.UNSUPERVISED)
    
    q = Query({(Quantity(1, "kg"), res_a)}, deadline=datetime(2023, 1, 1, 8, 0))
    
    # Work window is only 4 hours, which would normally reject a 10h process
    win = WorkWindow(start_time=datetime.strptime("08:00", "%H:%M").time(), end_time=datetime.strptime("12:00", "%H:%M").time())
    cal = CalendarBlock([win])
    ctx = _make_ctx([p_a], [q], calendar_block=cal)
    
    solver = Solver(ctx)
    schedule = solver.solve()
    assert isinstance(schedule, TimelineSchedule)
    
    start_a, end_a = schedule.process_times["p_a"]
    
    # Process should end exactly at the deadline (ALAP) outside of working hours
    assert end_a == q.deadline
    assert (end_a - start_a).total_seconds() == 10 * 3600

def test_tool_constrained_processes():
    # 4. Schedule two processes that both require `1 knife`.
    # Why: Verifies the solver strictly sequentializes them even if independent.
    from resource_flow.models import Tool
    knife = Tool("knife", Quantity(1, "piece"))
    
    res_a = Resource("A")
    res_b = Resource("B")
    res_out = Resource("Out")
    
    p_a = Process("p_a", inp=set(), out={(Quantity(1, "kg"), res_a)}, time=1.0, time_unit="h", tools={knife})
    p_b = Process("p_b", inp=set(), out={(Quantity(1, "kg"), res_b)}, time=1.0, time_unit="h", tools={knife})
    p_c = Process("p_c", inp={(Quantity(1, "kg"), res_a), (Quantity(1, "kg"), res_b)}, out={(Quantity(1, "kg"), res_out)}, time=1.0, time_unit="h")
    
    q = Query({(Quantity(1, "kg"), res_out)}, deadline=datetime(2023, 1, 1, 12, 0), tools={knife})
    ctx = _make_ctx([p_a, p_b, p_c], [q])
    
    solver = Solver(ctx)
    schedule = solver.solve()
    assert isinstance(schedule, TimelineSchedule)
    
    start_a, end_a = schedule.process_times["p_a"]
    start_b, end_b = schedule.process_times["p_b"]
    
    # They cannot overlap
    assert end_a <= start_b or end_b <= start_a

def test_hold_constraint():
    # 5. Process B requires `[hold <= 30 min]` from Process A.
    # Why: Verifies tighter chronological bounding is enforced.
    res_a = Resource("A", tags={"hold <= 30 min"})
    res_b = Resource("B")
    
    p_a = Process("p_a", inp=set(), out={(Quantity(1, "kg"), res_a)}, time=1.0, time_unit="h")
    p_b = Process("p_b", inp={(Quantity(1, "kg"), res_a)}, out={(Quantity(1, "kg"), res_b)}, time=1.0, time_unit="h")
    
    q = Query({(Quantity(1, "kg"), res_b)}, deadline=datetime(2023, 1, 1, 12, 0))
    ctx = _make_ctx([p_a, p_b], [q])
    
    solver = Solver(ctx)
    schedule = solver.solve()
    assert isinstance(schedule, TimelineSchedule)
    
    start_a, end_a = schedule.process_times["p_a"]
    start_b, end_b = schedule.process_times["p_b"]
    
    delay = (start_b - end_a).total_seconds() / 60.0
    assert delay <= 30.0

def test_travel_time_calculation():
    # 6. Process happens `at Lidl` then `at Home`.
    # Why: Verifies the travel edges are correctly computed and inserted as transit blocks.
    res_a = Resource("A")
    res_b = Resource("B")
    
    p_a = Process("p_a", inp=set(), out={(Quantity(1, "kg"), res_a)}, time=1.0, time_unit="h")
    # p_a happens at Lidl, p_b at Home. (Assigned via query location in ALAP).
    # Wait, the rule is "the location of a query is also the location of all processes downstream of the end result".
    # Since p_a output isn't directly the query, we can test travel time by forcing a query at Home for p_b,
    # and a query at Lidl for p_a ? No, we can just assign the location on the Process directly if we want.
    # But wait, Process location propagation is from query.
    # Let's explicitly set location on process.
    p_a.location = "Lidl"
    
    p_b = Process("p_b", inp={(Quantity(1, "kg"), res_a)}, out={(Quantity(1, "kg"), res_b)}, time=1.0, time_unit="h")
    
    q = Query({(Quantity(1, "kg"), res_b)}, location="Home", deadline=datetime(2023, 1, 1, 12, 0))
    
    # 1 hour travel time between Home and Lidl
    edge = TravelEdge("Home", "Lidl", time=Quantity(60, "min"))
    map_block = MapBlock(edges=[edge], heuristics=[])
    
    ctx = _make_ctx([p_a, p_b], [q], map_block=map_block)
    
    solver = Solver(ctx)
    schedule = solver.solve()
    assert isinstance(schedule, TimelineSchedule)
    
    start_a, end_a = schedule.process_times["p_a"]
    start_b, end_b = schedule.process_times["p_b"]
    
    # p_b is at Home. p_a is at Lidl. end_a + 60 mins <= start_b
    assert end_a + timedelta(minutes=60) <= start_b

def test_shopping_heuristic():
    # 7. Buy 10 items at Lidl.
    # Why: Verifies the `base time + N * item time` formula is correctly added to duration.
    res_a = Resource("A")
    res_b = Resource("B")
    
    p_a = Process("p_buy", inp=set(), out={(Quantity(10, "piece"), res_a), (Quantity(5, "piece"), res_b)}, time=0.0, time_unit="min")
    p_a.location = "Lidl"
    
    q = Query({(Quantity(10, "piece"), res_a), (Quantity(5, "piece"), res_b)}, deadline=datetime(2023, 1, 1, 12, 0))
    
    # 5 mins base + 2 mins per item. N = 15 different pieces?
    # Wait, the artifact comment said "n is the number of different products" !
    # So N = 2 (res_a and res_b).
    # Duration should be 5 + 2 * 2 = 9 minutes.
    heur = ShoppingHeuristic("Lidl", Quantity(5, "min"), Quantity(2, "min"))
    map_block = MapBlock(edges=[], heuristics=[heur])
    
    ctx = _make_ctx([p_a], [q], map_block=map_block)
    
    solver = Solver(ctx)
    schedule = solver.solve()
    assert isinstance(schedule, TimelineSchedule)
    
    start, end = schedule.process_times["p_buy"]
    assert (end - start).total_seconds() == 9 * 60

def test_shelf_life_constraint():
    # 8. Buy carrots `[shelf_life: 2 days]` and use them 3 days later.
    # Why: Verifies this forces the purchase event to occur closer to usage.
    carrots = Resource("Carrots", tags={"shelf_life: 48 h"})
    soup = Resource("Soup")
    
    p_buy = Process("buy", inp=set(), out={(Quantity(1, "kg"), carrots)}, time=1.0, time_unit="h")
    p_cook = Process("cook", inp={(Quantity(1, "kg"), carrots)}, out={(Quantity(1, "kg"), soup)}, time=1.0, time_unit="h")
    
    q = Query({(Quantity(1, "kg"), soup)}, deadline=datetime(2023, 1, 5, 12, 0))
    
    # Thursday cook window is exactly 1h (11:00-12:00), so only cook fits there.
    # Buy must go to Sunday's window, creating a 4-day gap > 48h shelf life.
    win_buy = WorkWindow(start_time=datetime.strptime("08:00", "%H:%M").time(), end_time=datetime.strptime("12:00", "%H:%M").time(), day_of_week="Sunday")
    win_cook = WorkWindow(start_time=datetime.strptime("11:00", "%H:%M").time(), end_time=datetime.strptime("12:00", "%H:%M").time(), day_of_week="Thursday")
    cal = CalendarBlock([win_buy, win_cook])
    
    ctx = _make_ctx([p_buy, p_cook], [q], calendar_block=cal)
    solver = Solver(ctx)
    
    with pytest.raises(InfeasibleScheduleError, match="Shelf life violated"):
        solver.solve()

def test_exceeding_calendar_bounds():
    # 9. Exceeding Calendar bounds: Schedule a 4-hour process when `calendar` blocks are only 3 hours.
    # Why: Verifies it strictly throws `InfeasibleScheduleError` without attempting to pause the process.
    res = Resource("out")
    p = Process("p1", inp=set(), out={(Quantity(1, "kg"), res)}, time=4.0, time_unit="h")
    q = Query({(Quantity(1, "kg"), res)}, deadline=datetime(2023, 1, 1, 12, 0))
    
    win = WorkWindow(start_time=datetime.strptime("09:00", "%H:%M").time(), end_time=datetime.strptime("12:00", "%H:%M").time())
    cal = CalendarBlock([win])
    ctx = _make_ctx([p], [q], calendar_block=cal)
    
    solver = Solver(ctx)
    with pytest.raises(InfeasibleScheduleError, match="exceeds all available contiguous calendar blocks"):
        solver.solve()

def test_impossible_travel_deadline():
    # 10. Impossible travel deadline: Require shopping at a store 1 hour away, with a deadline in 30 minutes.
    # Why: Ensures solver fails correctly on physical impossibilities.
    res_b = Resource("B")
    
    p_a = Process("p_a", inp=set(), out={(Quantity(1, "kg"), res_b)}, time=0.0, time_unit="h")
    p_a.location = "Lidl"
    
    # Fixed reference: 30-min window, but 60-min travel time makes it impossible.
    # start_time prevents the solver from escaping to an earlier date.
    base = datetime(2023, 6, 15, 12, 0)
    deadline = datetime(2023, 6, 15, 12, 30)
    q = Query({(Quantity(1, "kg"), res_b)}, location="Home", deadline=deadline, start_time=base)
    
    edge = TravelEdge("Home", "Lidl", time=Quantity(60, "min"))
    map_block = MapBlock(edges=[edge], heuristics=[])
    
    win = WorkWindow(start_time=base.time(), end_time=deadline.time(), day_of_week="Thursday")
    cal = CalendarBlock([win])
    
    ctx = _make_ctx([p_a], [q], map_block=map_block, calendar_block=cal)
    
    solver = Solver(ctx)
    with pytest.raises(InfeasibleScheduleError, match="travel time"):
        solver.solve()

def test_impossible_hold_constraint():
    # 11. Impossible hold constraint: resource A has hold <= 5 min, but a third
    # process using the same tool forces a 10-min gap between producer and consumer.
    # Why: Ensures solver throws an error when constraints mutually exclude each other.
    from resource_flow.models import Tool
    knife = Tool("knife", Quantity(1, "piece"))
    
    res_a = Resource("A", tags={"hold <= 5 min"})
    res_b = Resource("B")
    res_c = Resource("C")
    
    # p_a produces A (hold <= 5 min), p_c is independent but uses knife for 10 min,
    # p_b consumes A and also uses knife. Because p_c must use the knife between
    # p_a and p_b (all three share the knife and p_c feeds into p_b too),
    # the gap between p_a's end and p_b's start is >= 10 min > 5 min hold.
    p_a = Process("p_a", inp=set(), out={(Quantity(1, "kg"), res_a)}, time=10.0, time_unit="min", tools={knife})
    p_c = Process("p_c", inp=set(), out={(Quantity(1, "kg"), res_c)}, time=10.0, time_unit="min", tools={knife})
    p_b = Process("p_b", inp={(Quantity(1, "kg"), res_a), (Quantity(1, "kg"), res_c)}, out={(Quantity(1, "kg"), res_b)}, time=10.0, time_unit="min", tools={knife})
    
    q = Query({(Quantity(1, "kg"), res_b)}, deadline=datetime(2023, 1, 1, 12, 0), tools={knife})
    ctx = _make_ctx([p_a, p_b, p_c], [q])
    
    solver = Solver(ctx)
    with pytest.raises(InfeasibleScheduleError, match="hold constraint"):
        solver.solve()
