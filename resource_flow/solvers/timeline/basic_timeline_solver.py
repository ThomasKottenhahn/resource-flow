from datetime import datetime, timedelta, time as dt_time
from typing import Any
import re

from ...dag import DAG, DAGNode, DAGEdge
from ...models import Query, TimelineSchedule, ExecutionType
from ..interfaces import TimelineSolver
from ..exceptions import InfeasibleScheduleError
from .models import ScheduledTask, ScheduleEvent


class BasicTimelineSolver(TimelineSolver):
    """ALAP (As Late As Possible) constructive heuristic scheduler.

    Walks the dependency DAG in reverse topological order, placing each
    process as late as possible while respecting:
      - dependency ordering
      - calendar working-hour windows
      - travel times between locations
      - tool exclusivity (shared tools serialize processes)
      - hold constraints (max gap between producer and consumer)
      - shelf life constraints (max age of a resource before use)
      - shopping heuristics (base + per-item time at suppliers)
    """

    def __init__(self, dag: DAG, queries: list[Query] | Query, ctx=None) -> None:
        super().__init__(dag, queries, ctx)
        self.process_locations: dict[str, str] = {}
        self.shopping_heuristics = []
        if ctx and hasattr(ctx, "map_block"):
            self.shopping_heuristics = ctx.map_block.heuristics

    # ── public entry point ──────────────────────────────────────────────

    def solve(self) -> TimelineSchedule:
        self._propagate_locations()

        tasks = self._schedule_alap()
        
        # Local Search Optimizer
        tasks = self._optimize_local_search(tasks)

        process_times: dict[str, tuple[datetime, datetime]] = {}
        for task in tasks:
            if isinstance(task, ScheduledTask):
                process_times[task.process.name] = (task.start_time, task.end_time)

        # Enforce shelf_life constraints
        self._check_shelf_life(process_times)

        return TimelineSchedule(process_times=process_times, tasks=tasks, dag=self.dag)

    def _propagate_locations(self) -> None:
        """Assign locations to processes by walking the DAG backward from queries."""
        # Map resource names → query locations
        target_res_to_queries: dict[str, list[Query]] = {}
        for q in self.queries:
            for _qty, res in q.query:
                target_res_to_queries.setdefault(res.name, []).append(q)

        sorted_nodes = self._topological_sort()
        sorted_nodes.reverse()

        for node in sorted_nodes:
            # Explicit location on the process takes priority
            if node.process.location is not None:
                self.process_locations[node.process.name] = node.process.location
                continue

            inherited: set[str] = set()

            # From queries that consume this process's output
            for _qty, res in node.process.out:
                for q in target_res_to_queries.get(res.name, []):
                    loc = getattr(q, "location", None)
                    if loc:
                        inherited.add(loc)

            # From downstream DAG consumers already placed
            for edge in self.dag.edges:
                src = self._edge_name(edge.source)
                tgt = self._edge_name(edge.target)
                if src == node.process.name and tgt != "Query" and tgt in self.process_locations:
                    inherited.add(self.process_locations[tgt])

            if len(inherited) == 1:
                self.process_locations[node.process.name] = inherited.pop()
            elif len(inherited) > 1:
                self.process_locations[node.process.name] = sorted(inherited)[0]

    # ── topological sort ────────────────────────────────────────────────

    def _edge_name(self, endpoint: Any) -> str:
        """Normalize a DAG edge endpoint to a string name."""
        if endpoint is None:
            return ""
        if isinstance(endpoint, str):
            return endpoint
        return getattr(endpoint, "name", str(endpoint))

    def _topological_sort(self) -> list[DAGNode]:
        """Kahn's algorithm over DAG nodes. Edges to 'Query' / None are ignored."""
        node_map: dict[str, DAGNode] = {n.process.name: n for n in self.dag.nodes}
        in_degree: dict[str, int] = {name: 0 for name in node_map}

        for edge in self.dag.edges:
            src = self._edge_name(edge.source)
            tgt = self._edge_name(edge.target)
            if src in in_degree and tgt in in_degree:
                in_degree[tgt] += 1

        queue = [node_map[n] for n, deg in in_degree.items() if deg == 0]
        result: list[DAGNode] = []

        while queue:
            curr = queue.pop(0)
            result.append(curr)
            for edge in self.dag.edges:
                src = self._edge_name(edge.source)
                tgt = self._edge_name(edge.target)
                if src == curr.process.name and tgt in in_degree:
                    in_degree[tgt] -= 1
                    if in_degree[tgt] == 0:
                        queue.append(node_map[tgt])

        return result

    # ── travel time lookup ──────────────────────────────────────────────

    def _calculate_travel_time(self, from_loc: str, to_loc: str) -> timedelta:
        if from_loc == to_loc or not from_loc or not to_loc:
            return timedelta(0)

        if self.ctx and hasattr(self.ctx, "map_block"):
            for edge in self.ctx.map_block.edges:
                a, b = edge.loc_a, edge.loc_b
                if {a, b} == {from_loc, to_loc}:
                    return self._qty_to_timedelta(edge.time)

        return timedelta(0)

    # ── shopping heuristic ──────────────────────────────────────────────

    def _get_shopping_duration(self, location: str, num_products: int) -> timedelta:
        """Return the shopping duration from map heuristics, or zero."""
        for heur in self.shopping_heuristics:
            if heur.supplier == location:
                mins = heur.base_time.val + heur.per_item_time.val * num_products
                return timedelta(minutes=mins)
        return timedelta(0)

    # ── calendar helpers ────────────────────────────────────────────────

    def _has_calendar(self) -> bool:
        return bool(
            self.ctx
            and hasattr(self.ctx, "calendar_block")
            and self.ctx.calendar_block.windows
        )

    def _max_contiguous_block(self) -> timedelta:
        """Return the maximum contiguous block length across all calendar windows."""
        if not self._has_calendar():
            return timedelta(days=365)
        max_dur = timedelta(0)
        for w in self.ctx.calendar_block.windows:
            start_t = w.start_time if isinstance(w.start_time, dt_time) else w.start_time.time()
            end_t = w.end_time if isinstance(w.end_time, dt_time) else w.end_time.time()
            dur = datetime.combine(datetime.min, end_t) - datetime.combine(datetime.min, start_t)
            if dur > max_dur:
                max_dur = dur
        return max_dur

    def _window_matches_date(self, window, target_date) -> bool:
        """Check if a WorkWindow is valid for a given date."""
        if window.day_of_week is None:
            return True
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        try:
            target_dow = day_names[target_date.weekday()]
            return target_dow.lower() == window.day_of_week.lower()
        except (ValueError, IndexError):
            return False

    def _project_window(self, window, ref_date) -> tuple[datetime, datetime] | None:
        """Project a WorkWindow onto a concrete date, returning (start, end) or None if it doesn't match."""
        if not self._window_matches_date(window, ref_date):
            return None
        start_t = window.start_time if isinstance(window.start_time, dt_time) else window.start_time.time()
        end_t = window.end_time if isinstance(window.end_time, dt_time) else window.end_time.time()
        return (
            datetime.combine(ref_date, start_t),
            datetime.combine(ref_date, end_t),
        )

    def _find_calendar_slot(self, duration: timedelta, before: datetime) -> datetime | None:
        """Find the latest window end <= `before` that can contain `duration`.

        Returns the end-time of the slot, or None if nothing fits.
        Scans backward up to 365 days.
        """
        if not self._has_calendar():
            return before

        # Scan day by day backward from `before`
        current_date = before.date()
        min_date = current_date - timedelta(days=365)

        while current_date >= min_date:
            for window in self.ctx.calendar_block.windows:
                projected = self._project_window(window, current_date)
                if projected is None:
                    continue
                win_start, win_end = projected

                # Cap the window end to `before`
                effective_end = min(win_end, before)
                effective_start = effective_end - duration

                if effective_start >= win_start:
                    return effective_end

            current_date -= timedelta(days=1)

        return None

    # ── slot finding with resource conflicts ────────────────────────────

    def _find_latest_available_slot(
        self,
        duration: timedelta,
        candidate_end: datetime,
        occupied: list[list[tuple[datetime, datetime]]],
        execution_type: ExecutionType,
    ) -> datetime:
        """Find the latest end ≤ candidate_end where `duration` fits without
        overlapping any occupied block, and within a calendar window (unless unsupervised)."""
        current_end = candidate_end
        min_time = candidate_end - timedelta(days=365)

        for _ in range(10_000):  # safety cap
            if current_end < min_time:
                raise InfeasibleScheduleError(
                    f"Cannot find available slot for process of duration {duration}. "
                    "It exceeds all available contiguous calendar blocks or conflicts indefinitely."
                )

            # Snap to calendar first
            if self._has_calendar() and execution_type != ExecutionType.UNSUPERVISED:
                cal_end = self._find_calendar_slot(duration, current_end)
                if cal_end is None:
                    raise InfeasibleScheduleError(
                        f"Process of duration {duration} exceeds all available contiguous calendar blocks "
                        f"(max block: {self._max_contiguous_block()})."
                    )
                current_end = cal_end

            current_start = current_end - duration

            # Check for resource/tool conflicts
            conflict_start: datetime | None = None
            for schedule in occupied:
                for blk_start, blk_end in schedule:
                    if current_start < blk_end and current_end > blk_start:
                        # Overlap detected — record the earliest conflict start
                        if conflict_start is None or blk_start < conflict_start:
                            conflict_start = blk_start

            if conflict_start is not None:
                # Shift end to just before the conflict
                current_end = conflict_start
                continue

            return current_end

        raise InfeasibleScheduleError("Slot search exceeded iteration budget.")

    # ── tag parsing helpers ─────────────────────────────────────────────

    @staticmethod
    def _parse_duration_tag(tag_value: str) -> float:
        """Parse a duration string like '30 min', '48 h', '2 days' into minutes."""
        tag_value = tag_value.strip()
        match = re.match(r"([\d.]+)\s*(min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)", tag_value)
        if not match:
            try:
                return float(tag_value)
            except ValueError:
                return 0.0
        val = float(match.group(1))
        unit = match.group(2)
        if unit.startswith("h"):
            return val * 60
        if unit.startswith("d"):
            return val * 1440
        return val

    @staticmethod
    def _qty_to_timedelta(qty) -> timedelta:
        """Convert a Quantity with a time unit into a timedelta."""
        unit = (qty.unit or "min").lower()
        if unit.startswith("h"):
            return timedelta(hours=qty.val)
        if unit.startswith("d"):
            return timedelta(days=qty.val)
        return timedelta(minutes=qty.val)

    # ── ALAP scheduler ──────────────────────────────────────────────────

    def _schedule_alap(self) -> list[Any]:
        global_deadline = None
        global_start: datetime | None = None
        for q in self.queries:
            if q.deadline:
                if global_deadline is None or q.deadline < global_deadline:
                    global_deadline = q.deadline
            if getattr(q, 'start_time', None):
                if global_start is None or q.start_time > global_start:
                    global_start = q.start_time

        if global_deadline is None:
            global_deadline = datetime.now() + timedelta(days=7)

        sorted_nodes = self._topological_sort()
        sorted_nodes.reverse()  # consumers first for ALAP

        scheduled_starts: dict[str, datetime] = {}  # proc_name → scheduled start time
        tasks: list[Any] = []
        resource_schedules: dict[str, list[tuple[datetime, datetime]]] = {}

        def get_schedule(key: str) -> list[tuple[datetime, datetime]]:
            return resource_schedules.setdefault(key, [])

        def claim(key: str, start: datetime, end: datetime):
            get_schedule(key).append((start, end))

        for node in sorted_nodes:
            proc = node.process
            proc_name = proc.name
            proc_loc = self.process_locations.get(proc_name, "")

            # ── determine latest allowed end ────────────────────────
            end_bound = global_deadline
            hold_constraints: list[tuple[str, float, datetime]] = []  # (res_name, max_hold_min, consumer_start)

            # Query targets
            for q in self.queries:
                for _qty, res in q.query:
                    if any(r_out.name == res.name for _, r_out in proc.out):
                        target_loc = getattr(q, "location", None) or ""
                        travel = self._calculate_travel_time(proc_loc, target_loc)
                        cand = (q.deadline or global_deadline) - travel
                        if cand < end_bound:
                            end_bound = cand

            # DAG consumer edges
            for edge in self.dag.edges:
                src = self._edge_name(edge.source)
                tgt = self._edge_name(edge.target)
                if src != proc_name or tgt == "Query" or not tgt:
                    continue

                consumer_start = scheduled_starts.get(tgt)
                if consumer_start is None:
                    continue

                consumer_loc = self.process_locations.get(tgt, "")
                travel = self._calculate_travel_time(proc_loc, consumer_loc)
                cand = consumer_start - travel

                # Check hold constraint on the edge resource
                res = edge.resource
                if res and hasattr(res, "tags"):
                    hold_tag = next((t for t in res.tags if "hold <=" in t), None)
                    if hold_tag:
                        val_str = hold_tag.split("<=")[1].strip()
                        max_hold_mins = self._parse_duration_tag(val_str)
                        hold_constraints.append((res.name, max_hold_mins, consumer_start))

                if cand < end_bound:
                    end_bound = cand

            # ── compute process duration ────────────────────────────
            raw_time = proc.time * node.scale
            if proc.time_unit == "h":
                proc_duration = timedelta(hours=raw_time)
            elif proc.time_unit == "d":
                proc_duration = timedelta(days=raw_time)
            else:
                proc_duration = timedelta(minutes=raw_time)

            # Apply shopping heuristic
            shopping_extra = self._get_shopping_duration(proc_loc, len(proc.out))
            proc_duration += shopping_extra

            # ── check if duration fits in any calendar block ────────
            if self._has_calendar() and proc.execution_type != ExecutionType.UNSUPERVISED and proc_duration > self._max_contiguous_block():
                raise InfeasibleScheduleError(
                    f"Process '{proc_name}' duration {proc_duration} exceeds all "
                    f"available contiguous calendar blocks (max: {self._max_contiguous_block()})."
                )

            # ── find a conflict-free slot ───────────────────────────
            occupied = [get_schedule(f"loc:{proc_loc}")] if proc_loc else []
            for tool in proc.tools:
                occupied.append(get_schedule(f"tool:{tool.name}"))
            if proc.execution_type == ExecutionType.ACTIVE:
                occupied.append(get_schedule("actor:global"))

            end_time = self._find_latest_available_slot(proc_duration, end_bound, occupied, proc.execution_type)
            start_time = end_time - proc_duration

            # ── enforce hold constraints ────────────────────────────
            for res_name, max_hold_mins, consumer_start in hold_constraints:
                gap_mins = (consumer_start - end_time).total_seconds() / 60.0
                if gap_mins > max_hold_mins:
                    raise InfeasibleScheduleError(
                        f"hold constraint violated for '{res_name}': gap {gap_mins:.1f} min "
                        f"exceeds hold <= {max_hold_mins:.0f} min"
                    )

            # ── enforce start_time bound ─────────────────────────
            if global_start is not None and start_time < global_start:
                raise InfeasibleScheduleError(
                    f"Cannot schedule '{proc_name}' before start_time {global_start}: "
                    f"travel time or deadline impossible to satisfy."
                )

            # ── claim resources ─────────────────────────────────────
            if proc_loc:
                claim(f"loc:{proc_loc}", start_time, end_time)
            for tool in proc.tools:
                claim(f"tool:{tool.name}", start_time, end_time)
            if proc.execution_type == ExecutionType.ACTIVE:
                claim("actor:global", start_time, end_time)

            scheduled_starts[proc_name] = start_time

            tasks.append(ScheduledTask(
                process=proc,
                scale=node.scale,
                start_time=start_time,
                end_time=end_time,
                location=proc_loc,
            ))

        tasks.reverse()
        return tasks

    # ── shelf-life post-check ───────────────────────────────────────────

    def _check_shelf_life(self, process_times: dict[str, tuple[datetime, datetime]]) -> None:
        for edge in self.dag.edges:
            src = self._edge_name(edge.source)
            tgt = self._edge_name(edge.target)
            if tgt == "Query" or not src or not tgt:
                continue
            res = edge.resource
            if not res or not hasattr(res, "tags"):
                continue
            sl_tag = next((t for t in res.tags if t.startswith("shelf_life:")), None)
            if not sl_tag:
                continue

            val_str = sl_tag.split(":", 1)[1].strip()
            shelf_life_mins = self._parse_duration_tag(val_str)

            if src in process_times and tgt in process_times:
                producer_end = process_times[src][1]
                consumer_start = process_times[tgt][0]
                delay_mins = (consumer_start - producer_end).total_seconds() / 60.0
                if delay_mins > shelf_life_mins:
                    raise InfeasibleScheduleError(
                        f"Shelf life violated for {res.name}: delay {delay_mins:.0f} min "
                        f"exceeds shelf_life {shelf_life_mins:.0f} min"
                    )

    # ── local search optimizer ──────────────────────────────────────────

    def _evaluate_schedule(self, tasks: list[ScheduledTask]) -> float:
        """Score the schedule based on travel time and idle gaps between active tasks. Lower is better."""
        sorted_tasks = sorted(tasks, key=lambda t: t.start_time)
        score = 0.0
        last_loc = None
        last_end = None
        for t in sorted_tasks:
            if t.process.execution_type == ExecutionType.ACTIVE:
                if last_loc is not None and t.location and last_loc != t.location:
                    travel = self._calculate_travel_time(last_loc, t.location)
                    score += travel.total_seconds() * 10.0  # Weight travel heavily
                if last_end is not None and t.start_time > last_end:
                    gap = (t.start_time - last_end).total_seconds()
                    score += gap  # Penalty for idle time between active tasks
                last_loc = t.location
                last_end = max(last_end, t.end_time) if last_end else t.end_time
        return score

    def _is_valid_schedule(self, tasks: list[ScheduledTask], global_start: datetime) -> bool:
        occupied_tools = {}
        occupied_actor = []
        process_times = {t.process.name: (t.start_time, t.end_time) for t in tasks}
        for t in tasks:
            if self._has_calendar() and t.process.execution_type != ExecutionType.UNSUPERVISED:
                cal_end = self._find_calendar_slot(t.end_time - t.start_time, t.end_time)
                if cal_end != t.end_time:
                    return False
            if t.process.execution_type == ExecutionType.ACTIVE:
                for start, end in occupied_actor:
                    if max(t.start_time, start) < min(t.end_time, end):
                        return False
                occupied_actor.append((t.start_time, t.end_time))
            for tool in t.process.tools:
                tool_occ = occupied_tools.setdefault(tool.name, [])
                for start, end in tool_occ:
                    if max(t.start_time, start) < min(t.end_time, end):
                        return False
                tool_occ.append((t.start_time, t.end_time))
            if t.start_time < global_start:
                return False

        for edge in self.dag.edges:
            src = self._edge_name(edge.source)
            tgt = self._edge_name(edge.target)
            if src in process_times and tgt in process_times:
                producer_end = process_times[src][1]
                consumer_start = process_times[tgt][0]
                src_loc = self.process_locations.get(src, "")
                tgt_loc = self.process_locations.get(tgt, "")
                travel = self._calculate_travel_time(src_loc, tgt_loc)
                if consumer_start < producer_end + travel:
                    return False
                res = edge.resource
                if res and hasattr(res, "tags"):
                    hold_tag = next((tag for tag in res.tags if "hold <=" in tag), None)
                    if hold_tag:
                        max_hold_mins = self._parse_duration_tag(hold_tag.split("<=")[1].strip())
                        if (consumer_start - producer_end).total_seconds() / 60.0 > max_hold_mins:
                            return False
                    sl_tag = next((tag for tag in res.tags if tag.startswith("shelf_life:")), None)
                    if sl_tag:
                        sl_mins = self._parse_duration_tag(sl_tag.split(":", 1)[1].strip())
                        if (consumer_start - producer_end).total_seconds() / 60.0 > sl_mins:
                            return False

        for q in self.queries:
            for _qty, res in q.query:
                for t in tasks:
                    if any(r_out.name == res.name for _, r_out in t.process.out):
                        if q.deadline:
                            target_loc = getattr(q, "location", None) or ""
                            travel = self._calculate_travel_time(t.location, target_loc)
                            if t.end_time + travel > q.deadline:
                                return False
        return True

    def _optimize_local_search(self, tasks: list[ScheduledTask]) -> list[ScheduledTask]:
        import time, random, dataclasses
        if not tasks:
            return tasks

        global_deadline = None
        global_start = None
        for q in self.queries:
            if q.deadline:
                if global_deadline is None or q.deadline < global_deadline:
                    global_deadline = q.deadline
            if getattr(q, 'start_time', None):
                if global_start is None or q.start_time > global_start:
                    global_start = q.start_time

        if global_deadline is None:
            global_deadline = datetime.now() + timedelta(days=7)
        if global_start is None:
            global_start = min(t.start_time for t in tasks)

        best_tasks = tasks
        best_score = self._evaluate_schedule(best_tasks)
        no_improve = 0
        start_time_limit = time.time()

        for i in range(10000):
            if time.time() - start_time_limit > 1.0:
                break
            if no_improve >= 100:
                break

            candidate = [dataclasses.replace(t) for t in best_tasks]
            idx_a = random.randint(0, len(candidate) - 1)
            t_a = candidate[idx_a]
            dur_a = t_a.end_time - t_a.start_time

            mutation_type = random.choice(["before", "after", "swap", "earliest", "latest"])
            mutated_tasks = [t_a]

            if mutation_type in ("before", "after", "swap"):
                idx_b = random.randint(0, len(candidate) - 1)
                t_b = candidate[idx_b]
                dur_b = t_b.end_time - t_b.start_time

                if mutation_type == "before":
                    t_a.end_time = t_b.start_time
                    t_a.start_time = t_a.end_time - dur_a
                elif mutation_type == "after":
                    t_a.start_time = t_b.end_time
                    t_a.end_time = t_a.start_time + dur_a
                elif mutation_type == "swap":
                    start_a = t_a.start_time
                    start_b = t_b.start_time
                    t_a.start_time = start_b
                    t_a.end_time = start_b + dur_a
                    t_b.start_time = start_a
                    t_b.end_time = start_a + dur_b
                    mutated_tasks.append(t_b)
            elif mutation_type == "earliest":
                t_a.start_time = global_start
                t_a.end_time = global_start + dur_a
            elif mutation_type == "latest":
                t_a.end_time = global_deadline
                t_a.start_time = global_deadline - dur_a

            if self._has_calendar():
                for t in mutated_tasks:
                    if t.process.execution_type != ExecutionType.UNSUPERVISED:
                        dur = t.end_time - t.start_time
                        cal_end = self._find_calendar_slot(dur, t.end_time)
                        if cal_end:
                            t.end_time = cal_end
                            t.start_time = cal_end - dur

            if self._is_valid_schedule(candidate, global_start):
                score = self._evaluate_schedule(candidate)
                if score < best_score:
                    best_tasks = candidate
                    best_score = score
                    no_improve = 0
                else:
                    no_improve += 1
            else:
                no_improve += 1

        return best_tasks
