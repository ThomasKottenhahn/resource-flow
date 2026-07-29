from .models import Process, Query, Quantity, Resource


class RecipeSolver:
    def __init__(self, processes: set[Process], query: Query) -> None:
        self.processes = sorted(list(processes), key=lambda p: p.name)
        self.query = query
        self.basic_resources: dict[str, Resource] = {}
        self.basic_resource_names = self._identify_basic_resources()
        self.final_demands: dict[str, Quantity] = {}
        self.final_surplus: dict[str, Quantity] = {}
        self.processes_in_dag: list[Process] = []
        self.basic_requirements: set[str] = set()

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
        adj = {p.name: set() for p in procs}

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

    def _find_all_candidate_dags(self) -> list[tuple[list[Process], set[str]]]:
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

        initial_needed = [(None, res) for _, res in self.query.query]
        search(initial_needed, [], set(), set(), set())

        valid_candidates = []
        for procs, basics in results:
            topo_procs = self._topological_sort(procs)
            if topo_procs is not None:
                valid_candidates.append((topo_procs, basics))
            else:
                cycle_procs.update(p.name for p in procs)

        if not valid_candidates:
            if cycle_procs:
                proc_name = sorted(list(cycle_procs))[0]
                raise ValueError(f"Cycle detected involving process '{proc_name}'")
            if missing_resources:
                res_name = sorted(list(missing_resources))[0]
                raise ValueError(f"No process found to produce non-basic resource '{res_name}'")
            raise ValueError("No valid recipe graph found for query")

        return valid_candidates

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

    def evaluate_goal(
        self,
        process_scales: dict[str, float],
        final_demands: dict[str, Quantity],
        dag_basic_resources: dict[str, Resource],
        processes_in_dag: list[Process],
        goal: str,
        time_unit: str = "min",
    ) -> float:
        if goal == "cheapest":
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

        elif goal == "fastest":
            total_time = 0.0
            for proc in processes_in_dag:
                if proc.time > 0:
                    scale = process_scales.get(proc.name, 0.0)
                    scaled_time = proc.time * scale
                    q_time = Quantity(scaled_time, proc.time_unit)
                    converted = q_time.convert_to(time_unit)
                    total_time += converted.val
            return total_time

        elif goal == "any":
            return 0.0

        return 0.0

    def build_dag(self) -> tuple[list[Process], set[str]]:
        if self.processes_in_dag:
            return self.processes_in_dag, self.basic_requirements

        candidates = self._find_all_candidate_dags()

        ranked_candidates = []
        for procs, basic_reqs in candidates:
            proc_scales, demands, surplus, dag_basics = self._solve_dag(procs)
            scores = tuple(
                self.evaluate_goal(proc_scales, demands, dag_basics, procs, goal)
                for goal in self.query.goals
            )
            tie_breaker = tuple(sorted(p.name for p in procs))
            ranked_candidates.append(
                (scores, tie_breaker, procs, basic_reqs, proc_scales, demands, surplus, dag_basics)
            )

        ranked_candidates.sort(key=lambda item: (item[0], item[1]))
        best = ranked_candidates[0]

        self.processes_in_dag = best[2]
        self.basic_requirements = best[3]
        self.final_demands = best[5]
        self.final_surplus = best[6]

        return self.processes_in_dag, self.basic_requirements

    def solve(self) -> dict[str, float]:
        self.processes_in_dag = []  # reset to re-solve if needed
        processes_in_dag, _ = self.build_dag()
        proc_scales, demands, surplus, _ = self._solve_dag(processes_in_dag)
        self.final_demands = demands
        self.final_surplus = surplus
        return proc_scales

    def _format_resource_tags(self, res: Resource | None) -> str:
        if res is None:
            return ""
        other_tags = sorted([t for t in res.tags if t != "basic"])
        neg_tags = sorted([f"!{t}" for t in res.negated_tags])
        all_tags = other_tags + neg_tags
        if all_tags:
            return f" [{', '.join(all_tags)}]"
        return ""

    def print_plan(
        self, process_scales: dict[str, float], time_unit: str = "min"
    ) -> None:
        processes_in_dag, _ = self.build_dag()
        print("=== RECIPE EXECUTION PLAN ===")

        for i, proc in enumerate(processes_in_dag, 1):
            scale = process_scales[proc.name]
            details = [f"Scale: {scale:.4f}"]
            if proc.cost > 0:
                details.append(f"Cost: {proc.cost * scale:.2f}")
            if proc.time > 0:
                details.append(f"Time: {proc.time * scale:.2f} {proc.time_unit}")
            header_params = f"({', '.join(details)})"
            tag_str = f" [{', '.join(sorted(proc.tags))}]" if proc.tags else ""
            print(f"\nStep {i}: {proc.name} {header_params}{tag_str}")
            print("  Inputs:")
            for qty, res in proc.inp:
                scaled_qty = qty * scale
                producer = self.find_producer(res) if not res.basic else None
                is_basic_str = (
                    " *"
                    if (res.basic or producer is None or producer not in processes_in_dag)
                    else ""
                )
                res_tags_str = self._format_resource_tags(res)
                print(
                    f"    - {scaled_qty.val:.2f} {scaled_qty.unit} {res.name}{is_basic_str}{res_tags_str}"
                )
            print("  Outputs:")
            for qty, res in proc.out:
                scaled_qty = qty * scale
                res_tags_str = self._format_resource_tags(res)
                surplus_str = ""
                if (
                    res.name in self.final_surplus
                    and self.final_surplus[res.name].val > 0.001
                ):
                    surplus_qty = self.final_surplus[res.name]
                    try:
                        surplus_converted = surplus_qty.convert_to(qty.unit)
                        surplus_str = f" (Surplus: {surplus_converted.val:.2f} {qty.unit})"
                    except ValueError:
                        surplus_str = (
                            f" (Surplus: {surplus_qty.val:.2f} {surplus_qty.unit})"
                        )
                print(
                    f"    - {scaled_qty.val:.2f} {scaled_qty.unit} {res.name}{res_tags_str}{surplus_str}"
                )

        print("\n=== TOTAL BASIC RESOURCES REQUIRED ===")
        for name, qty in sorted(self.final_demands.items()):
            res = self.basic_resources.get(name)
            res_tags_str = self._format_resource_tags(res)
            cost_str = ""
            if res and res.cost > 0:
                cost_val = res.calculate_cost(qty)
                cost_str = f" (Cost: {cost_val:.2f})"
            print(f"- {qty.val:.2f} {qty.unit} {name}{res_tags_str}{cost_str}")
        print("======================================\n")

        metrics = self.get_metrics(process_scales, time_unit=time_unit)
        print("=== METRICS SUMMARY ===")
        print(f"Resource Cost: {metrics['resource_cost']:.2f}")
        print(f"Process Cost:  {metrics['process_cost']:.2f}")
        print(f"Total Cost:    {metrics['total_cost']:.2f}")
        print(f"Total Time:    {metrics['total_time']:.2f} {metrics['time_unit']}")
        print("=======================\n")

    def generate_mermaid(
        self, process_scales: dict[str, float], time_unit: str = "min"
    ) -> str:
        processes_in_dag, basic_reqs = self.build_dag()
        lines = ["```mermaid", "graph TD"]

        for proc in processes_in_dag:
            scale = process_scales[proc.name]
            node_parts = [f"{proc.name} (x{scale:.2f})"]
            proc_metrics = []
            if proc.cost > 0:
                proc_metrics.append(f"Cost: {proc.cost * scale:.2f}")
            if proc.time > 0:
                proc_metrics.append(f"Time: {proc.time * scale:.2f} {proc.time_unit}")
            if proc_metrics:
                node_parts.append(", ".join(proc_metrics))
            if proc.tags:
                node_parts.append(f"[{', '.join(sorted(proc.tags))}]")
            label = "\\n".join(node_parts)
            lines.append(f'    {proc.name}["{label}"]')

        for name in sorted(basic_reqs):
            res = self.basic_resources.get(name)
            res_tags_str = self._format_resource_tags(res)
            if name in self.final_demands:
                qty = self.final_demands[name]
                cost_str = ""
                if res and res.cost > 0:
                    cost_val = res.calculate_cost(qty)
                    cost_str = f", Cost: {cost_val:.2f}"
                lines.append(
                    f'    basic_{name}["{name}*{res_tags_str} ({qty.val:.2f} {qty.unit}{cost_str})"]'
                )
            else:
                lines.append(f'    basic_{name}["{name}*{res_tags_str}"]')

        query_targets = []
        for qty, res in sorted(self.query.query, key=lambda item: item[1].name):
            res_tags_str = self._format_resource_tags(res)
            query_targets.append(f"{qty.val:.2f} {qty.unit} {res.name}{res_tags_str}")
        lines.append(f'    Query["Query: {", ".join(query_targets)}"]')

        for proc in processes_in_dag:
            scale = process_scales[proc.name]
            for qty_in, res_in in proc.inp:
                scaled_qty = qty_in * scale
                res_tags_str = self._format_resource_tags(res_in)
                producer = self.find_producer(res_in) if not res_in.basic else None
                if producer is not None and producer in processes_in_dag:
                    lines.append(
                        f'    {producer.name} -->|"{scaled_qty.val:.2f} {scaled_qty.unit} {res_in.name}{res_tags_str}"| {proc.name}'
                    )
                else:
                    lines.append(
                        f'    basic_{res_in.name} -->|"{scaled_qty.val:.2f} {scaled_qty.unit} {res_in.name}{res_tags_str}"| {proc.name}'
                    )

            for qty_out, res_out in proc.out:
                if any(
                    res_out.name == q_res.name and self._matches_tags(q_res, res_out)
                    for _, q_res in self.query.query
                ):
                    scaled_qty = qty_out * scale
                    res_tags_str = self._format_resource_tags(res_out)
                    lines.append(
                        f'    {proc.name} -->|"{scaled_qty.val:.2f} {scaled_qty.unit} {res_out.name}{res_tags_str}"| Query'
                    )

        for q_qty, q_res in sorted(self.query.query, key=lambda item: item[1].name):
            producer = self.find_producer(q_res) if not q_res.basic else None
            if producer is None or producer not in processes_in_dag:
                res_tags_str = self._format_resource_tags(q_res)
                lines.append(
                    f'    basic_{q_res.name} -->|"{q_qty.val:.2f} {q_qty.unit} {q_res.name}{res_tags_str}"| Query'
                )

        metrics = self.get_metrics(process_scales, time_unit=time_unit)
        metrics_label = (
            f"Metrics Summary\\n"
            f"Resource Cost: {metrics['resource_cost']:.2f}\\n"
            f"Process Cost: {metrics['process_cost']:.2f}\\n"
            f"Total Cost: {metrics['total_cost']:.2f}\\n"
            f"Total Time: {metrics['total_time']:.2f} {metrics['time_unit']}"
        )
        lines.append(f'    Metrics["{metrics_label}"]')

        lines.append("```")
        return "\n".join(lines)

    def calculate_resource_costs(self) -> float:
        total = 0.0
        for name, qty in self.final_demands.items():
            res = self.basic_resources.get(name)
            if res:
                total += res.calculate_cost(qty)
        return total

    def calculate_process_costs(self, process_scales: dict[str, float]) -> float:
        total = 0.0
        processes_in_dag, _ = self.build_dag()
        for proc in processes_in_dag:
            scale = process_scales.get(proc.name, 0.0)
            total += proc.cost * scale
        return total

    def calculate_process_time(
        self, process_scales: dict[str, float], target_unit: str = "min"
    ) -> float:
        total = 0.0
        processes_in_dag, _ = self.build_dag()
        for proc in processes_in_dag:
            if proc.time > 0:
                scale = process_scales.get(proc.name, 0.0)
                scaled_time = proc.time * scale
                q_time = Quantity(scaled_time, proc.time_unit)
                converted = q_time.convert_to(target_unit)
                total += converted.val
        return total

    def get_metrics(
        self, process_scales: dict[str, float], time_unit: str = "min"
    ) -> dict[str, float]:
        res_cost = self.calculate_resource_costs()
        proc_cost = self.calculate_process_costs(process_scales)
        proc_time = self.calculate_process_time(process_scales, target_unit=time_unit)
        return {
            "resource_cost": res_cost,
            "process_cost": proc_cost,
            "total_cost": res_cost + proc_cost,
            "total_time": proc_time,
            "time_unit": time_unit,
        }
