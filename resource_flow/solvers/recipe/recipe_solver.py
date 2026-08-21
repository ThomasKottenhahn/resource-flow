from __future__ import annotations
from ...dag import DAG, DAGEdge, DAGNode
from ...models import AggregateGoal, AnyGoal, Process, Query, Quantity, RelationalGoal, Resource, ProgramContext
from typing import Any
from ..base import Solver

class RecipeSolver(Solver):
    """Orchestrates the resolution of queries by searching topologies, scaling processes, and evaluating goals."""
    def __init__(
        self,
        ctx: ProgramContext | set[Process] | None = None,
        processes: set[Process] | Query | None = None,
        query: Query | list[Resource] | None = None,
        defs: list[Resource] | None = None,
    ) -> None:
        if isinstance(ctx, ProgramContext):
            actual_processes = ctx.processes
            actual_query = ctx.query
            actual_defs = ctx.defs
        elif ctx is not None:
            # Called as RecipeSolver(processes, query)
            actual_defs = query if isinstance(query, list) else defs
            actual_query = processes
            actual_processes = ctx
        else:
            actual_processes = set()
            actual_query = Query(set())
            actual_defs = defs

        super().__init__(actual_processes, actual_query, actual_defs)
        
        filtered_processes = []
        for p in actual_processes:
            if p.has_required_tools(self.query.tools):
                filtered_processes.append(p)
                
        self._all_processes = sorted(actual_processes, key=lambda p: p.name)
        self.processes = sorted(filtered_processes, key=lambda p: p.name)
        self.basic_resource_names = self._identify_basic_resources()
        self.processes_in_dag: list[Process] = []
        self.basic_requirements: set[str] = set()
        self._result_dag: DAG | None = None

    def _add_basic(self, r: Resource) -> None:
        """Register a resource as a basic resource."""
        if r.name not in self.basic_resources:
            self.basic_resources[r.name] = [r]
        elif r.cost > 0 and not any(br.cost == r.cost and br.tags == r.tags for br in self.basic_resources[r.name]):
            self.basic_resources[r.name].append(r)

    def _identify_basic_resources(self) -> set[str]:
        """Discover all resources marked as basic across processes, queries, and explicit defs."""
        basics = set()

        # Populate from explicit defs
        for d in self.defs:
            basics.add(d.name)
            self._add_basic(d)

        for p in self.processes:
            for _, r in p.inp:
                if r.basic:
                    basics.add(r.name)
                    self._add_basic(r)
            for _, r in p.out:
                if r.basic:
                    basics.add(r.name)
                    self._add_basic(r)
        for _, r in self.query.query:
            if r.basic:
                basics.add(r.name)
                self._add_basic(r)
        return basics

    def is_basic(self, resource_name: str) -> bool:
        """Check if a resource name is known to be a basic resource."""
        return resource_name in self.basic_resource_names

    def _matches_tags(self, required: Resource, provided: Resource) -> bool:
        """Check if a provided resource satisfies the required resource\'s tags."""
        req_tags = required.tags - {"basic"}
        prov_tags = provided.tags - {"basic"}
        if not req_tags.issubset(prov_tags):
            return False
        if not required.negated_tags.isdisjoint(prov_tags):
            return False
        return True

    def _can_be_basic(self, res: Resource) -> bool:
        """Check if a resource can be satisfied as a basic (externally supplied) resource."""
        if res.basic:
            return True
        if res.name in self.basic_resources:
            for basic_res in self.basic_resources[res.name]:
                if self._matches_tags(res, basic_res):
                    return True
        return False

    def find_producer(self, target: Resource | str) -> Process | None:
        """Find the first process capable of producing the target resource."""
        producers = self._find_all_producers(target)
        return producers[0] if producers else None

    def _find_all_producers(self, target: Resource | str) -> list[Process]:
        """Find all processes that can produce the target resource."""
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
        """Sort processes topologically based on resource dependencies. Returns None if a cycle exists."""
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

    def _find_candidate_topologies(self) -> tuple[list[tuple[list[Process], set[str]]], set[str], set[str]]:
        """Search the graph and return all valid candidate topological orderings of processes."""
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
            producers = [p for p in self._find_all_producers(res) if p != consumer]
            can_basic = self._can_be_basic(res)

            if not producers and not can_basic:
                missing_resources.add(res.name)
                return

            if can_basic:
                search(
                    unresolved[1:],
                    chosen_procs,
                    chosen_proc_names,
                    active_stack,
                    basic_reqs | {res.name},
                )

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

        valid_topologies = []
        for procs, basic_reqs in results:
            topo_procs = self._topological_sort(procs)
            if topo_procs is not None:
                valid_topologies.append((topo_procs, basic_reqs))
            else:
                cycle_procs.update(p.name for p in procs)

        return valid_topologies, cycle_procs, missing_resources


    def _find_producer_in(self, res: Resource, procs: list[Process]) -> Process | None:
        """Find a process in a given list that produces the resource (tag-matched)."""
        for p in procs:
            for _, out_res in p.out:
                if out_res.name == res.name and self._matches_tags(res, out_res):
                    return p
        return None

    def _build_dag_from_solution(self, processes: list[Process], process_scales: dict[str, float], demands: dict[str, Quantity], dag_basic_resources: dict[str, Resource]) -> DAG:
        """Construct a DAG with nodes (process + scale) and edges (resource flows)."""
        nodes = [DAGNode(process=p, scale=process_scales[p.name]) for p in processes]
        edges: list[DAGEdge] = []

        for proc in processes:
            scale = process_scales[proc.name]
            for qty_in, res_in in proc.inp:
                source = self._find_producer_in(res_in, processes)
                if source is not None and source != proc:
                    scaled_qty = qty_in * scale
                    edges.append(DAGEdge(
                        source=source,
                        target=proc,
                        resource=res_in,
                        quantity=scaled_qty,
                    ))

        for name, qty in demands.items():
            dag_res = dag_basic_resources.get(name)
            global_res_list = self.basic_resources.get(name, [])
            # Pick the best global basic resource (prefer one with cost > 0)
            global_res = next((r for r in global_res_list if r.cost > 0), global_res_list[0] if global_res_list else None)
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

        for proc in processes:
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

    def _scale_topology(self, processes: list[Process], basic_reqs: set[str]) -> tuple[DAG, dict[str, float], dict[str, Quantity], dict[str, Quantity]]:
        """Calculate scale factors for all processes in the topology and construct its fully scaled DAG."""
        demands: dict[str, Quantity] = {}
        for qty, res in self.query.query:
            if res.name in demands:
                demands[res.name] += qty
            else:
                demands[res.name] = qty

        surplus: dict[str, Quantity] = {}
        process_scales: dict[str, float] = {}

        for proc in reversed(processes):
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
        for proc in processes:
            for _, r in proc.inp:
                if r.basic or r.name in demands:
                    if r.name not in dag_basic_resources or r.cost > 0:
                        dag_basic_resources[r.name] = r
        for _, r in self.query.query:
            if r.basic or r.name in demands:
                if r.name not in dag_basic_resources or r.cost > 0:
                    dag_basic_resources[r.name] = r

        dag = self._build_dag_from_solution(processes, process_scales, demands, dag_basic_resources)
        return dag, process_scales, demands, surplus

    def _evaluate_dags(self, scaled_candidates: list[tuple[DAG, list[Process], set[str], dict[str, float], dict[str, Quantity], dict[str, Quantity]]], relational_goals: list[Any], aggregate_goals: list[Any]) -> tuple[list[dict[str, Any]], tuple[Any, float] | None]:
        """Filter candidates by relational goals and compute scores for aggregate goals to rank them."""
        valid_candidates = []
        closest_diff = float("inf")
        closest_info = None

        for dag, procs, basic_reqs, scales, demands, surplus in scaled_candidates:
            passed_all = True
            for g in relational_goals:
                passed = g.evaluate(dag)
                if not passed:
                    passed_all = False
                    target_val = g.val
                    if g.unit:
                        target_val = Quantity(g.val, g.unit).to_base_unit().val
                    metric_val = dag.calculate_metric(g.tag, unit="s" if g.unit in {"s", "min", "h"} else g.unit)
                    diff = abs(metric_val - target_val)
                    if diff < closest_diff:
                        closest_diff = diff
                        display_val = dag.calculate_metric(g.tag, unit=g.unit) if g.unit else dag.calculate_metric(g.tag)
                        closest_info = (g, display_val)
                    break

            if passed_all:
                scores = tuple(g.evaluate(dag) for g in aggregate_goals)
                tie_breaker = tuple(sorted(p.name for p in procs))
                valid_candidates.append({
                    "dag": dag,
                    "processes": procs,
                    "basic_requirements": basic_reqs,
                    "demands": demands,
                    "surplus": surplus,
                    "scores": scores,
                    "tie_breaker": tie_breaker
                })

        return valid_candidates, closest_info

    def build_dag(self) -> tuple[list[Process], set[str]]:
        """Build and cache the optimal process DAG. Returns (processes, basic_requirements)."""
        if self.processes_in_dag:
            return self.processes_in_dag, self.basic_requirements
        self.solve()
        return self.processes_in_dag, self.basic_requirements

    def _run_phase2_fallback(self, relational_goals: list[Any]) -> None:
        """Phase 2: Try solving with all processes to give a better error message about missing tools."""
        original_processes = self.processes
        original_basics = self.basic_resources
        original_basic_names = self.basic_resource_names
        
        self.processes = self._all_processes
        self.basic_resources = {}
        self.basic_resource_names = self._identify_basic_resources()
        
        try:
            topologies, _, _ = self._find_candidate_topologies()
            scaled_candidates = []
            for procs, basic_reqs in topologies:
                dag, scales, demands, surplus = self._scale_topology(procs, basic_reqs)
                scaled_candidates.append((dag, procs, basic_reqs, scales, demands, surplus))
                
            p2_valid, _ = self._evaluate_dags(scaled_candidates, relational_goals, [])
            
            if p2_valid:
                valid_missing = []
                for cand in p2_valid:
                    procs = cand["processes"]
                    missing_tools = self.query.calculate_missing_tools(procs)
                    valid_missing.append((missing_tools, procs))
                
                valid_missing.sort(key=lambda item: len(item[0]))
                best_missing = valid_missing[0][0]
                tool_names = ", ".join(sorted(best_missing.keys()))
                
                raise ValueError(f"No solution found with available tools. Closest solution requires additional tools: {tool_names}")
        finally:
            self.processes = original_processes
            self.basic_resources = original_basics
            self.basic_resource_names = original_basic_names

    def solve(self) -> DAG:
        """Search candidate topologies, evaluate goals, and return the optimal result DAG."""
        self.processes_in_dag = []
        self._result_dag = None

        topologies, cycle_procs, missing_resources = self._find_candidate_topologies()

        scaled_candidates = []
        for procs, basic_reqs in topologies:
            dag, scales, demands, surplus = self._scale_topology(procs, basic_reqs)
            scaled_candidates.append((dag, procs, basic_reqs, scales, demands, surplus))

        relational_goals = [g for g in self.query.goals if isinstance(g, RelationalGoal)]
        aggregate_goals = [g for g in self.query.goals if not isinstance(g, RelationalGoal)]

        valid_candidates, closest_info = self._evaluate_dags(scaled_candidates, relational_goals, aggregate_goals)

        if not valid_candidates:
            if not topologies and len(self.processes) < len(self._all_processes):
                self._run_phase2_fallback(relational_goals)
                
            if not topologies:
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

        valid_candidates.sort(key=lambda item: (item["scores"], item["tie_breaker"]))
        best = valid_candidates[0]

        self.processes_in_dag = best["processes"]
        self.basic_requirements = best["basic_requirements"]
        self.final_demands = best["demands"]
        self.final_surplus = best["surplus"]
        self._result_dag = best["dag"]

        return self._result_dag