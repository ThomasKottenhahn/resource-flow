from .dag import DAG, DAGEdge, DAGNode
from .models import AggregateGoal, AnyGoal, Process, Query, Quantity, RelationalGoal, Resource


class RecipeSolver:
    def __init__(self, processes: set[Process], query: Query) -> None:
        self.query = query
        
        filtered_processes = []
        for p in processes:
            available = True
            for required_tool in p.tools:
                tool_found = False
                for avail_tool in self.query.tools:
                    if avail_tool.name == required_tool.name:
                        try:
                            converted_avail = avail_tool.quantity.convert_to(required_tool.quantity.unit)
                            if converted_avail.val >= required_tool.quantity.val:
                                tool_found = True
                                break
                        except ValueError:
                            pass
                if not tool_found:
                    available = False
                    break
            if available:
                filtered_processes.append(p)
                
        self._all_processes = sorted(processes, key=lambda p: p.name)
        self.processes = sorted(filtered_processes, key=lambda p: p.name)
        self.basic_resources: dict[str, Resource] = {}
        self.basic_resource_names = self._identify_basic_resources()
        self.final_demands: dict[str, Quantity] = {}
        self.final_surplus: dict[str, Quantity] = {}
        self.processes_in_dag: list[Process] = []
        self.basic_requirements: set[str] = set()
        self._result_dag: DAG | None = None

    def _identify_basic_resources(self) -> set[str]:
        basics = set()
        for p in self.processes:
            for _, r in p.inp:
                if r.basic:
                    basics.add(r.name)
                    if r.name not in self.basic_resources or r.cost > 0:
                        self.basic_resources[r.name] = r
            for _, r in p.out:
                if r.basic:
                    basics.add(r.name)
                    if r.name not in self.basic_resources or r.cost > 0:
                        self.basic_resources[r.name] = r
        for _, r in self.query.query:
            if r.basic:
                basics.add(r.name)
                if r.name not in self.basic_resources or r.cost > 0:
                    self.basic_resources[r.name] = r
        return basics

    def is_basic(self, resource_name: str) -> bool:
        return resource_name in self.basic_resource_names

    def _matches_tags(self, required: Resource, provided: Resource) -> bool:
        req_tags = required.tags - {"basic"}
        prov_tags = provided.tags - {"basic"}
        if not req_tags.issubset(prov_tags):
            return False
        if not required.negated_tags.isdisjoint(prov_tags):
            return False
        return True

    def _can_be_basic(self, res: Resource) -> bool:
        if res.basic:
            return True
        if res.name in self.basic_resources:
            basic_res = self.basic_resources[res.name]
            if self._matches_tags(res, basic_res):
                return True
        return False

    def find_producer(self, target: Resource | str) -> Process | None:
        producers = self.find_all_producers(target)
        return producers[0] if producers else None

    def find_all_producers(self, target: Resource | str) -> list[Process]:
        if isinstance(target, str):
            target_name = target
            target_res = None
        else:
            target_name = target.name
            target_res = target

        producers = []
        for p in self.processes:
            for _, out_res in p.out:
                if out_res.name == target_name:
                    if target_res is None or self._matches_tags(target_res, out_res):
                        producers.append(p)
                        break
        return producers

    def _topological_sort(self, procs: list[Process]) -> list[Process] | None:
        if not procs:
            return []

        proc_map = {p.name: p for p in procs}
        in_degree = {p.name: 0 for p in procs}
        adj: dict[str, set[str]] = {p.name: set() for p in procs}

        for p2 in procs:
            for _, ingr in p2.inp:
                for p1 in procs:
                    if p1.name != p2.name:
                        for _, out_res in p1.out:
                            if out_res.name == ingr.name and self._matches_tags(ingr, out_res):
                                if p2.name not in adj[p1.name]:
                                    adj[p1.name].add(p2.name)
                                    in_degree[p2.name] += 1

        queue = sorted([p.name for p in procs if in_degree[p.name] == 0])
        sorted_names = []

        while queue:
            node = queue.pop(0)
            sorted_names.append(node)
            for neighbor in sorted(adj[node]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    queue.sort()

        if len(sorted_names) == len(procs):
            return [proc_map[name] for name in sorted_names]
        return None

    def _find_all_candidate_dags(self) -> tuple[list[tuple[list[Process], set[str]]], set[str], set[str]]:
        results: list[tuple[list[Process], set[str]]] = []
        seen_keys: set[tuple[str, ...]] = set()
        missing_resources: set[str] = set()
        cycle_procs: set[str] = set()

        def search(
            needed: list[tuple[Process | None, Resource]],
            chosen_procs: list[Process],
            chosen_proc_names: set[str],
            active_stack: set[str],
            basic_reqs: set[str],
        ) -> None:
            unresolved = []
            for consumer, res in needed:
                is_produced = any(
                    proc != consumer
                    and any(out_res.name == res.name and self._matches_tags(res, out_res) for _, out_res in proc.out)
                    for proc in chosen_procs
                )
                if not is_produced:
                    unresolved.append((consumer, res))

            if not unresolved:
                dag_key = tuple(sorted(chosen_proc_names))
                if dag_key not in seen_keys:
                    seen_keys.add(dag_key)
                    results.append((list(chosen_procs), set(basic_reqs)))
                return

            consumer, res = unresolved[0]
            producers = [p for p in self.find_all_producers(res) if p != consumer]
            can_basic = self._can_be_basic(res)

            if not producers and not can_basic:
                missing_resources.add(res.name)
                return

            # Option A: res satisfied as basic if it can be basic
            if can_basic:
                search(
                    unresolved[1:],
                    chosen_procs,
                    chosen_proc_names,
                    active_stack,
                    basic_reqs | {res.name},
                )

            # Option B: candidate producers
            for proc in producers:
                if proc.name in active_stack:
                    cycle_procs.add(proc.name)
                    continue

                if proc.name in chosen_proc_names:
                    search(
                        unresolved[1:],
                        chosen_procs,
                        chosen_proc_names,
                        active_stack,
                        basic_reqs,
                    )
                else:
                    new_inputs = [(proc, r) for _, r in proc.inp]
                    chosen_procs.append(proc)
                    chosen_proc_names.add(proc.name)
                    active_stack.add(proc.name)

                    search(
                        new_inputs + unresolved[1:],
                        chosen_procs,
                        chosen_proc_names,
                        active_stack,
                        basic_reqs,
                    )

                    active_stack.remove(proc.name)
                    chosen_proc_names.remove(proc.name)
                    chosen_procs.pop()

        initial_needed: list[tuple[Process | None, Resource]] = [(None, res) for _, res in self.query.query]
        search(initial_needed, [], set(), set(), set())

        valid_candidates = []
        for procs, basics in results:
            topo_procs = self._topological_sort(procs)
            if topo_procs is not None:
                valid_candidates.append((topo_procs, basics))
            else:
                cycle_procs.update(p.name for p in procs)

        return valid_candidates, cycle_procs, missing_resources

    def _calculate_missing_tools(self, procs: list[Process]) -> dict[str, Quantity]:
        req_tools: dict[str, Quantity] = {}
        for p in procs:
            for t in p.tools:
                if t.name not in req_tools:
                    req_tools[t.name] = t.quantity
                else:
                    try:
                        converted = t.quantity.convert_to(req_tools[t.name].unit)
                        if converted.val > req_tools[t.name].val:
                            req_tools[t.name] = converted
                    except ValueError:
                        pass
                        
        missing: dict[str, Quantity] = {}
        for name, req_qty in req_tools.items():
            avail_val = 0.0
            for avail_t in self.query.tools:
                if avail_t.name == name:
                    try:
                        avail_val = avail_t.quantity.convert_to(req_qty.unit).val
                        break
                    except ValueError:
                        pass
            if avail_val < req_qty.val:
                missing[name] = Quantity(req_qty.val - avail_val, req_qty.unit)
        return missing

    def _find_producer_in(self, res: Resource, procs: list[Process]) -> Process | None:
        """Find a process in a given list that produces the resource (tag-matched)."""
        for p in procs:
            for _, out_res in p.out:
                if out_res.name == res.name and self._matches_tags(res, out_res):
                    return p
        return None

    def _build_dag_from_solution(
        self,
        processes_in_dag: list[Process],
        process_scales: dict[str, float],
        demands: dict[str, Quantity],
        surplus: dict[str, Quantity],
        dag_basic_resources: dict[str, Resource],
    ) -> DAG:
        """Construct a DAG with nodes (process + scale) and edges (resource flows)."""
        nodes = [DAGNode(process=p, scale=process_scales[p.name]) for p in processes_in_dag]
        edges: list[DAGEdge] = []

        # Process-to-process edges
        for proc in processes_in_dag:
            scale = process_scales[proc.name]
            for qty_in, res_in in proc.inp:
                source = self._find_producer_in(res_in, processes_in_dag)
                if source is not None and source != proc:
                    scaled_qty = qty_in * scale
                    edges.append(DAGEdge(
                        source=source,
                        target=proc,
                        resource=res_in,
                        quantity=scaled_qty,
                    ))

        # One basic edge per unique basic resource using final accumulated demands
        for name, qty in demands.items():
            dag_res = dag_basic_resources.get(name)
            global_res = self.basic_resources.get(name)
            if dag_res and dag_res.cost > 0:
                basic_res: Resource | None = dag_res
            elif global_res and global_res.cost > 0:
                basic_res = global_res
            else:
                basic_res = dag_res or global_res
            if basic_res:
                edges.append(DAGEdge(
                    source=None,
                    target=None,
                    resource=basic_res,
                    quantity=qty,
                ))

        # Query output edges
        for proc in processes_in_dag:
            scale = process_scales[proc.name]
            for qty_out, res_out in proc.out:
                if any(
                    res_out.name == q_res.name and self._matches_tags(q_res, res_out)
                    for _, q_res in self.query.query
                ):
                    scaled_qty = qty_out * scale
                    edges.append(DAGEdge(
                        source=proc,
                        target="Query",
                        resource=res_out,
                        quantity=scaled_qty,
                    ))

        return DAG(nodes=nodes, edges=edges)


    def _solve_dag(
        self, processes_in_dag: list[Process]
    ) -> tuple[dict[str, float], dict[str, Quantity], dict[str, Quantity], dict[str, Resource]]:
        demands: dict[str, Quantity] = {}
        for qty, res in self.query.query:
            if res.name in demands:
                demands[res.name] += qty
            else:
                demands[res.name] = qty

        surplus: dict[str, Quantity] = {}
        process_scales: dict[str, float] = {}

        for proc in reversed(processes_in_dag):
            scale_factor = 0.0
            for qty_out, res_out in proc.out:
                if res_out.name in demands:
                    demand_qty = demands[res_out.name]
                    converted_demand = demand_qty.convert_to(qty_out.unit)
                    scale = converted_demand.val / qty_out.val
                    if scale > scale_factor:
                        scale_factor = scale

            process_scales[proc.name] = scale_factor

            for qty_out, res_out in proc.out:
                produced = qty_out * scale_factor
                demanded = Quantity(0.0, qty_out.unit)
                if res_out.name in demands:
                    demanded = demands[res_out.name].convert_to(qty_out.unit)
                    del demands[res_out.name]

                if produced.val > demanded.val:
                    excess = produced - demanded
                    if res_out.name in surplus:
                        surplus[res_out.name] += excess
                    else:
                        surplus[res_out.name] = excess

            for qty_in, res_in in proc.inp:
                needed = qty_in * scale_factor

                if res_in.name in surplus and surplus[res_in.name].val > 0:
                    available = surplus[res_in.name].convert_to(qty_in.unit)
                    if available.val >= needed.val:
                        surplus[res_in.name] = (available - needed).convert_to(
                            surplus[res_in.name].unit
                        )
                        needed = Quantity(0.0, qty_in.unit)
                    else:
                        needed -= available
                        surplus[res_in.name] = Quantity(
                            0.0, surplus[res_in.name].unit
                        )

                if needed.val > 0:
                    if res_in.name in demands:
                        demands[res_in.name] += needed
                    else:
                        demands[res_in.name] = needed

        dag_basic_resources = {}
        for proc in processes_in_dag:
            for _, r in proc.inp:
                if r.basic or r.name in demands:
                    if r.name not in dag_basic_resources or r.cost > 0:
                        dag_basic_resources[r.name] = r
        for _, r in self.query.query:
            if r.basic or r.name in demands:
                if r.name not in dag_basic_resources or r.cost > 0:
                    dag_basic_resources[r.name] = r

        return process_scales, demands, surplus, dag_basic_resources

    def build_dag(self) -> tuple[list[Process], set[str]]:
        """Build and cache the optimal process DAG. Returns (processes, basic_requirements)."""
        if self.processes_in_dag:
            return self.processes_in_dag, self.basic_requirements

        self.solve()
        return self.processes_in_dag, self.basic_requirements

    def solve(self) -> DAG:
        """Search candidate DAGs, evaluate goals, return the optimal result DAG."""
        self.processes_in_dag = []  # reset to re-solve if needed
        self._result_dag = None

        candidates, cycle_procs, missing_resources = self._find_all_candidate_dags()

        relational_goals = [g for g in self.query.goals if isinstance(g, RelationalGoal)]
        aggregate_goals = [g for g in self.query.goals if not isinstance(g, RelationalGoal)]

        valid_candidates = []
        closest_diff = float("inf")
        closest_info = None

        for procs, basic_reqs in candidates:
            proc_scales, demands, surplus, dag_basics = self._solve_dag(procs)
            candidate_dag = self._build_dag_from_solution(procs, proc_scales, demands, surplus, dag_basics)

            passed_all = True
            for g in relational_goals:
                passed = g.evaluate(candidate_dag)
                if not passed:
                    passed_all = False
                    # track closest for error reporting
                    target_val = g.val
                    if g.unit:
                        target_val = Quantity(g.val, g.unit).to_base_unit().val
                    metric_val = candidate_dag.calculate_metric(g.tag, unit="s" if g.unit in {"s", "min", "h"} else g.unit)
                    diff = abs(metric_val - target_val)
                    if diff < closest_diff:
                        closest_diff = diff
                        display_val = candidate_dag.calculate_metric(g.tag, unit=g.unit) if g.unit else candidate_dag.calculate_metric(g.tag)
                        closest_info = (g, display_val)
                    break

            if passed_all:
                scores = tuple(g.evaluate(candidate_dag) for g in aggregate_goals)
                tie_breaker = tuple(sorted(p.name for p in procs))
                valid_candidates.append(
                    (scores, tie_breaker, procs, basic_reqs, proc_scales, demands, surplus, dag_basics, candidate_dag)
                )

        if not valid_candidates:
            if not candidates and len(self.processes) < len(self._all_processes):
                # Phase 2: Try with all processes to give a better error message about missing tools
                original_processes = self.processes
                original_basics = self.basic_resources
                original_basic_names = self.basic_resource_names
                
                self.processes = self._all_processes
                self.basic_resources = {}
                self.basic_resource_names = self._identify_basic_resources()
                
                p2_candidates, _, _ = self._find_all_candidate_dags()
                
                p2_valid = []
                for procs, basic_reqs in p2_candidates:
                    proc_scales, demands, surplus, dag_basics = self._solve_dag(procs)
                    candidate_dag = self._build_dag_from_solution(procs, proc_scales, demands, surplus, dag_basics)
                    passed_all = True
                    for g in relational_goals:
                        if not g.evaluate(candidate_dag):
                            passed_all = False
                            break
                    if passed_all:
                        missing_tools = self._calculate_missing_tools(procs)
                        p2_valid.append((missing_tools, procs))
                        
                if p2_valid:
                    # Select candidate needing minimal additional tools (by number of distinct tools)
                    p2_valid.sort(key=lambda item: len(item[0]))
                    best_missing = p2_valid[0][0]
                    tool_names = ", ".join(sorted(best_missing.keys()))
                    
                    self.processes = original_processes
                    self.basic_resources = original_basics
                    self.basic_resource_names = original_basic_names
                    
                    raise ValueError(f"No solution found with available tools. Closest solution requires additional tools: {tool_names}")
                    
                # Restore Phase 1 state if Phase 2 yields nothing useful
                self.processes = original_processes
                self.basic_resources = original_basics
                self.basic_resource_names = original_basic_names
                
            if not candidates:
                if cycle_procs:
                    proc_name = sorted(list(cycle_procs))[0]
                    raise ValueError(f"Cycle detected involving process '{proc_name}'")
                if missing_resources:
                    res_name = sorted(list(missing_resources))[0]
                    raise ValueError(f"No process found to produce non-basic resource '{res_name}'")
            if closest_info:
                g, val = closest_info
                raise ValueError(f"No solution found for {g}. Closest solution found: {g.tag} = {val}")
            raise ValueError("No valid processes found to satisfy the request.")

        valid_candidates.sort(key=lambda item: (item[0], item[1]))
        best = valid_candidates[0]

        self.processes_in_dag = best[2]
        self.basic_requirements = best[3]
        self.final_demands = best[5]
        self.final_surplus = best[6]
        self._result_dag = best[8]

        return self._result_dag

    # ------------------------------------------------------------------
    # Backward-compatible metrics / visualization helpers
    # ------------------------------------------------------------------

    def _get_visualizer(self, dag: DAG | None = None):
        from .visualization import Visualizer
        d = dag or self._result_dag
        if d is None:
            raise RuntimeError("Call solve() before using visualization methods.")
        dag_basics = {
            edge.resource.name: edge.resource
            for edge in d.edges
            if d._is_basic_edge(edge)
        }
        return Visualizer(
            dag=d,
            demands=self.final_demands,
            surplus=self.final_surplus,
            basic_resources=dag_basics or self.basic_resources,
            query=self.query,
        )

    def _format_resource_tags(self, res: Resource | None) -> str:
        if res is None:
            return ""
        other_tags = sorted([t for t in res.tags if t != "basic"])
        neg_tags = sorted([f"!{t}" for t in res.negated_tags])
        all_tags = other_tags + neg_tags
        if all_tags:
            return f" [{', '.join(all_tags)}]"
        return ""

    def print_plan(self, process_scales: dict[str, float], time_unit: str = "min") -> None:
        self._get_visualizer().print_plan(time_unit=time_unit)

    def generate_mermaid(self, process_scales: dict[str, float], time_unit: str = "min") -> str:
        return self._get_visualizer().generate_mermaid(time_unit=time_unit)

    def calculate_resource_costs(self) -> float:
        return self._get_visualizer().get_metrics()["resource_cost"]

    def calculate_process_costs(self, process_scales: dict[str, float]) -> float:
        return self._get_visualizer().get_metrics()["process_cost"]

    def calculate_process_time(self, process_scales: dict[str, float], target_unit: str = "min") -> float:
        return self._get_visualizer().get_metrics(time_unit=target_unit)["total_time"]

    def get_metrics(self, process_scales: dict[str, float], time_unit: str = "min") -> dict:
        return self._get_visualizer().get_metrics(time_unit=time_unit)

    # ------------------------------------------------------------------
    # Legacy: evaluate_goal / _calculate_metric kept for backward compat
    # ------------------------------------------------------------------

    def evaluate_goal(
        self,
        process_scales: dict[str, float],
        final_demands: dict[str, Quantity],
        dag_basic_resources: dict[str, Resource],
        processes_in_dag: list[Process],
        goal,
        time_unit: str = "min",
    ) -> float:
        if isinstance(goal, (AggregateGoal, RelationalGoal, AnyGoal)):
            if self._result_dag:
                val = goal.evaluate(self._result_dag)
                return float(val) if isinstance(val, bool) else val
        if goal == "cheapest" or goal == "min cost":
            return self._calculate_metric(process_scales, final_demands, dag_basic_resources, processes_in_dag, "cost", time_unit)
        elif goal == "fastest" or goal == "min time":
            return self._calculate_metric(process_scales, final_demands, dag_basic_resources, processes_in_dag, "time", time_unit)
        elif isinstance(goal, AggregateGoal):
            val = self._calculate_metric(process_scales, final_demands, dag_basic_resources, processes_in_dag, goal.tag, time_unit)
            return -val if goal.op == "max" else val
        return 0.0

    def _calculate_metric(
        self,
        process_scales: dict[str, float],
        final_demands: dict[str, Quantity],
        dag_basic_resources: dict[str, Resource],
        processes_in_dag: list[Process],
        tag_name: str,
        time_unit: str = "min",
    ) -> float:
        if tag_name == "cost":
            res_cost = 0.0
            for name, qty in final_demands.items():
                res = self.basic_resources.get(name) or dag_basic_resources.get(name)
                if res:
                    res_cost += res.calculate_cost(qty)
            proc_cost = 0.0
            for proc in processes_in_dag:
                scale = process_scales.get(proc.name, 0.0)
                proc_cost += proc.cost * scale
            return res_cost + proc_cost

        elif tag_name == "time":
            total_time = 0.0
            for proc in processes_in_dag:
                if proc.time > 0:
                    scale = process_scales.get(proc.name, 0.0)
                    scaled_time = proc.time * scale
                    q_time = Quantity(scaled_time, proc.time_unit)
                    converted = q_time.convert_to(time_unit)
                    total_time += converted.val
            return total_time

        else:
            val = 0.0
            prefix = tag_name + ":"

            for proc in processes_in_dag:
                if tag_name in proc.tags:
                    val += 1.0

                scale = process_scales.get(proc.name, 0.0)
                for t in proc.tags:
                    if t.startswith(prefix):
                        kv_val = float(t.split(":")[1].strip())
                        val += kv_val * scale

            for name, qty in final_demands.items():
                res = self.basic_resources.get(name) or dag_basic_resources.get(name)
                if res:
                    if tag_name in res.tags:
                        val += 1.0
                    for t in res.tags:
                        if t.startswith(prefix):
                            kv_val = float(t.split(":")[1].strip())
                            val += kv_val * qty.val

            return val
