from .models import Process, Query, Quantity, Resource


class RecipeSolver:
    def __init__(self, processes: set[Process], query: Query) -> None:
        self.processes = sorted(list(processes), key=lambda p: p.name)
        self.query = query
        self.basic_resources: dict[str, Resource] = {}
        self.basic_resource_names = self._identify_basic_resources()
        self.final_demands: dict[str, Quantity] = {}
        self.final_surplus: dict[str, Quantity] = {}

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

    def find_producer(self, target: Resource | str) -> Process | None:
        if isinstance(target, str):
            target_name = target
            target_res = None
        else:
            target_name = target.name
            target_res = target

        for p in self.processes:
            for _, out_res in p.out:
                if out_res.name == target_name:
                    if target_res is None or self._matches_tags(target_res, out_res):
                        return p
        return None

    def build_dag(self) -> tuple[list[Process], set[str]]:
        visited_processes: set[str] = set()
        temp_visited: set[str] = set()
        processes_in_dag: list[Process] = []
        basic_requirements: set[str] = set()

        def visit_resource(res: Resource) -> None:
            if res.basic:
                basic_requirements.add(res.name)
                return

            producer = self.find_producer(res)
            if producer is not None:
                visit_process(producer)
            else:
                raise ValueError(
                    f"No process found to produce non-basic resource '{res.name}'"
                )

        def visit_process(proc: Process) -> None:
            if proc.name in temp_visited:
                raise ValueError(f"Cycle detected involving process '{proc.name}'")
            if proc.name in visited_processes:
                return

            temp_visited.add(proc.name)
            for _, ingr in proc.inp:
                visit_resource(ingr)
            temp_visited.remove(proc.name)
            visited_processes.add(proc.name)
            processes_in_dag.append(proc)

        for _, q_res in self.query.query:
            visit_resource(q_res)

        return processes_in_dag, basic_requirements

    def solve(self) -> dict[str, float]:
        processes_in_dag, _ = self.build_dag()
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
                    s = converted_demand.val / qty_out.val
                    if s > scale_factor:
                        scale_factor = s

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

        self.final_demands = demands
        self.final_surplus = surplus
        return process_scales

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
                is_basic_str = " *" if self.is_basic(res.name) or res.basic else ""
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
                if res.cost_unit:
                    cost_val = qty.convert_to(res.cost_unit).val * res.cost
                else:
                    cost_val = qty.val * res.cost
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
                    if res.cost_unit:
                        c_val = qty.convert_to(res.cost_unit).val * res.cost
                    else:
                        c_val = qty.val * res.cost
                    cost_str = f", Cost: {c_val:.2f}"
                lines.append(
                    f'    basic_{name}["{name}*{res_tags_str} ({qty.val:.2f} {qty.unit}{cost_str})"]'
                )
            else:
                lines.append(f'    basic_{name}["{name}*{res_tags_str}"]')

        query_targets = []
        for qty, res in self.query.query:
            res_tags_str = self._format_resource_tags(res)
            query_targets.append(f"{qty.val:.2f} {qty.unit} {res.name}{res_tags_str}")
        lines.append(f'    Query["Query: {", ".join(query_targets)}"]')

        for proc in processes_in_dag:
            scale = process_scales[proc.name]
            for qty_in, res_in in proc.inp:
                scaled_qty = qty_in * scale
                res_tags_str = self._format_resource_tags(res_in)
                if self.is_basic(res_in.name):
                    lines.append(
                        f'    basic_{res_in.name} -->|"{scaled_qty.val:.2f} {scaled_qty.unit}{res_tags_str}"| {proc.name}'
                    )
                else:
                    producer = self.find_producer(res_in) or self.find_producer(res_in.name)
                    if producer:
                        lines.append(
                            f'    {producer.name} -->|"{scaled_qty.val:.2f} {scaled_qty.unit} {res_in.name}{res_tags_str}"| {proc.name}'
                        )

            for qty_out, res_out in proc.out:
                if any(res_out.name == q_res.name for _, q_res in self.query.query):
                    scaled_qty = qty_out * scale
                    res_tags_str = self._format_resource_tags(res_out)
                    lines.append(
                        f'    {proc.name} -->|"{scaled_qty.val:.2f} {scaled_qty.unit} {res_out.name}{res_tags_str}"| Query'
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
            if res and res.cost > 0:
                if res.cost_unit:
                    converted_qty = qty.convert_to(res.cost_unit)
                    total += converted_qty.val * res.cost
                else:
                    total += qty.val * res.cost
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

