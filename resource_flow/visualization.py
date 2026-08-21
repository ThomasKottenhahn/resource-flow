from .dag import DAG, DAGEdge
from .models import Process, Quantity, Query, Resource


class Visualizer:
    """Renders a solved result DAG as text or Mermaid diagram.

    Accepts pre-computed solver context (demands, surplus, basic_resources, query)
    so that no graph search or scale computation happens here.
    """

    def __init__(
        self,
        dag: DAG,
        demands: dict[str, Quantity],
        surplus: dict[str, Quantity],
        basic_resources: dict[str, list[Resource]],
        query: Query,
    ) -> None:
        self.dag = dag
        self.demands = demands
        self.surplus = surplus
        self.basic_resources = basic_resources
        self.query = query

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _format_resource_tags(self, res: Resource | None) -> str:
        """Format a resource's tags into a string representation for display."""
        if res is None:
            return ""
        other_tags = sorted([t for t in res.tags if t != "basic"])
        neg_tags = sorted([f"!{t}" for t in res.negated_tags])
        all_tags = other_tags + neg_tags
        if all_tags:
            return f" [{', '.join(all_tags)}]"
        return ""

    def _find_source_process(self, res: Resource, consumer: Process | str) -> Process | None:
        """Return the process node in the DAG that produces the given resource for the consumer."""
        for edge in self.dag.edges:
            if (
                edge.target == consumer
                and edge.resource.name == res.name
                and isinstance(edge.source, Process)
            ):
                return edge.source
        return None

    def _basic_resource_names(self) -> set[str]:
        """Extract the names of all basic resources utilized in the DAG."""
        return {
            edge.resource.name
            for edge in self.dag.edges
            if self.dag._is_basic_edge(edge)
        }

    def _matches_tags(self, required: Resource, provided: Resource) -> bool:
        """Check if a provided resource satisfies the required resource's tags."""
        req_tags = required.tags - {"basic"}
        prov_tags = provided.tags - {"basic"}
        if not req_tags.issubset(prov_tags):
            return False
        if not required.negated_tags.isdisjoint(prov_tags):
            return False
        return True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_metrics(self, time_unit: str = "min") -> dict[str, float | str]:
        """Calculate and return a summary of cost and time metrics for the resolved DAG."""
        res_cost = 0.0
        for name, qty in self.demands.items():
            # In the DAG, basic edges track the chosen resource variant.
            # We can grab it from the DAG edges!
            edge = next((e for e in self.dag.edges if self.dag._is_basic_edge(e) and e.resource.name == name), None)
            res = edge.resource if edge else None
            if not res and self.basic_resources.get(name):
                res = self.basic_resources[name][0]
            if res:
                res_cost += res.calculate_cost(qty)
        proc_cost = sum(node.process.cost * node.scale for node in self.dag.nodes)
        proc_time = self.dag.calculate_metric("time", unit=time_unit)
        return {
            "resource_cost": res_cost,
            "process_cost": proc_cost,
            "total_cost": res_cost + proc_cost,
            "total_time": proc_time,
            "time_unit": time_unit,
        }

    def print_plan(self, time_unit: str = "min") -> None:
        """Print the complete step-by-step execution plan to the console."""
        processes = self.dag.processes
        process_scales = self.dag.process_scales

        print("=== RECIPE EXECUTION PLAN ===")

        for i, proc in enumerate(processes, 1):
            scale = process_scales[proc.name]
            details = [f"Scale: {scale:.4f}"]
            if proc.cost > 0:
                details.append(f"Cost: {proc.cost * scale:.2f}")
            if proc.time > 0:
                details.append(f"Time: {proc.time * scale:.2f} {proc.time_unit}")
            header_params = f"({', '.join(details)})"
            tag_str = f" [{', '.join(sorted(proc.tags))}]" if proc.tags else ""
            print(f"\nStep {i}: {proc.original_label} {header_params}{tag_str}")
            if proc.tools:
                tools_str = ", ".join(str(t) for t in sorted(proc.tools, key=lambda x: x.name))
                print(f"  Tools: {tools_str}")
            print("  Inputs:")
            for qty, res in proc.inp:
                scaled_qty = qty * scale
                source = self._find_source_process(res, proc)
                is_basic_str = " *" if (res.basic or source is None) else ""
                res_tags_str = self._format_resource_tags(res)
                print(
                    f"    - {scaled_qty.val:.2f} {scaled_qty.unit} {res.name}{is_basic_str}{res_tags_str}"
                )
            print("  Outputs:")
            for qty, res in proc.out:
                scaled_qty = qty * scale
                res_tags_str = self._format_resource_tags(res)
                surplus_str = ""
                if res.name in self.surplus and self.surplus[res.name].val > 0.001:
                    surplus_qty = self.surplus[res.name]
                    try:
                        surplus_converted = surplus_qty.convert_to(qty.unit)
                        surplus_str = f" (Surplus: {surplus_converted.val:.2f} {qty.unit})"
                    except ValueError:
                        surplus_str = f" (Surplus: {surplus_qty.val:.2f} {surplus_qty.unit})"
                print(
                    f"    - {scaled_qty.val:.2f} {scaled_qty.unit} {res.name}{res_tags_str}{surplus_str}"
                )

        print("\n=== TOTAL BASIC RESOURCES REQUIRED ===")
        for name, qty in sorted(self.demands.items()):
            edge = next((e for e in self.dag.edges if self.dag._is_basic_edge(e) and e.resource.name == name), None)
            basic_res = edge.resource if edge else None
            if not basic_res and self.basic_resources.get(name):
                basic_res = self.basic_resources[name][0]
            res_tags_str = self._format_resource_tags(basic_res)
            cost_str = ""
            if basic_res and basic_res.cost > 0:
                cost_val = basic_res.calculate_cost(qty)
                cost_str = f" (Cost: {cost_val:.2f})"
            print(f"- {qty.val:.2f} {qty.unit} {name}{res_tags_str}{cost_str}")
        print("======================================\n")

        metrics = self.get_metrics(time_unit=time_unit)
        print("=== METRICS SUMMARY ===")
        print(f"Resource Cost: {metrics['resource_cost']:.2f}")
        print(f"Process Cost:  {metrics['process_cost']:.2f}")
        print(f"Total Cost:    {metrics['total_cost']:.2f}")
        print(f"Total Time:    {metrics['total_time']:.2f} {metrics['time_unit']}")
        print("=======================\n")

    def generate_mermaid(self, time_unit: str = "min") -> str:
        """Generate a Mermaid flowchart visualizing the solved resource flow."""
        processes = self.dag.processes
        process_scales = self.dag.process_scales
        basic_reqs = self._basic_resource_names()

        lines = ["```mermaid", "graph TD"]

        for proc in processes:
            scale = process_scales[proc.name]
            node_parts = [f"{proc.original_label} (x{scale:.2f})"]
            proc_metrics = []
            if proc.cost > 0:
                proc_metrics.append(f"Cost: {proc.cost * scale:.2f}")
            if proc.time > 0:
                proc_metrics.append(f"Time: {proc.time * scale:.2f} {proc.time_unit}")
            if proc_metrics:
                node_parts.append(", ".join(proc_metrics))
            if proc.tags:
                node_parts.append(f"[{', '.join(sorted(proc.tags))}]")
            if proc.tools:
                tools_str = "using " + ", ".join(str(t) for t in sorted(proc.tools, key=lambda x: x.name))
                node_parts.append(tools_str)
            label = "\\n".join(node_parts)
            lines.append(f'    {proc.name}["{label}"]')

        for name in sorted(basic_reqs):
            edge = next((e for e in self.dag.edges if self.dag._is_basic_edge(e) and e.resource.name == name), None)
            res = edge.resource if edge else None
            if not res and self.basic_resources.get(name):
                res = self.basic_resources[name][0]
            res_tags_str = self._format_resource_tags(res)
            if name in self.demands:
                qty = self.demands[name]
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

        for proc in processes:
            scale = process_scales[proc.name]
            for qty_in, res_in in proc.inp:
                scaled_qty = qty_in * scale
                res_tags_str = self._format_resource_tags(res_in)
                source = self._find_source_process(res_in, proc)
                if source is not None:
                    lines.append(
                        f'    {source.name} -->|"{scaled_qty.val:.2f} {scaled_qty.unit} {res_in.name}{res_tags_str}"| {proc.name}'
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
            source = self._find_source_process(q_res, "Query")  # no consumer for query targets
            if q_res.basic or source is None:
                # check if any process in dag produces this
                produced_by_dag = any(
                    any(res_out.name == q_res.name and self._matches_tags(q_res, res_out)
                        for _, res_out in proc.out)
                    for proc in processes
                )
                if not produced_by_dag:
                    res_tags_str = self._format_resource_tags(q_res)
                    lines.append(
                        f'    basic_{q_res.name} -->|"{q_qty.val:.2f} {q_qty.unit} {q_res.name}{res_tags_str}"| Query'
                    )

        metrics = self.get_metrics(time_unit=time_unit)
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
