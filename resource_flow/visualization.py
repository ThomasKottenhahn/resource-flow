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
        queries: "list[Query] | Query | None" = None,
    ) -> None:
        self.dag = dag
        self.demands = demands
        self.surplus = surplus
        self.basic_resources = basic_resources
        if isinstance(queries, Query):
            self.queries = [queries]
        else:
            self.queries = queries or []

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
        supplier_groups: dict[str, list[tuple[str, Quantity, Resource | None]]] = {}
        for name, qty in sorted(self.demands.items()):
            edge = next((e for e in self.dag.edges if self.dag._is_basic_edge(e) and e.resource.name == name), None)
            basic_res = edge.resource if edge else None
            supplier = edge.source if edge and isinstance(edge.source, str) else None
            if not basic_res and self.basic_resources.get(name):
                basic_res = self.basic_resources[name][0]
            
            group_name = supplier if supplier else "Global"
            if group_name not in supplier_groups:
                supplier_groups[group_name] = []
            supplier_groups[group_name].append((name, qty, basic_res))
            
        for supplier_name in sorted(supplier_groups.keys()):
            print(f"{supplier_name}:")
            for name, qty, basic_res in supplier_groups[supplier_name]:
                res_tags_str = self._format_resource_tags(basic_res)
                cost_str = ""
                if basic_res and basic_res.cost > 0:
                    cost_val = basic_res.calculate_cost(qty)
                    cost_str = f" (Cost: {cost_val:.2f})"
                print(f" - {qty.val:.2f} {qty.unit} {name}{res_tags_str}{cost_str}")
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

        supplier_nodes: set[str] = set()

        for name in sorted(basic_reqs):
            edge = next((e for e in self.dag.edges if self.dag._is_basic_edge(e) and e.resource.name == name), None)
            res = edge.resource if edge else None
            supplier = edge.source if edge and isinstance(edge.source, str) else None

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
                
            if supplier:
                supplier_id = supplier.replace(" ", "_")
                if supplier not in supplier_nodes:
                    supplier_nodes.add(supplier)
                    lines.append(f'    {supplier_id}["{supplier}"]')
                lines.append(f'    {supplier_id} --> basic_{name}')

        query_targets = []
        for q in self.queries:
            for qty, res in sorted(q.query, key=lambda item: item[1].name):
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
                if any(res_out.name == q_res.name and self._matches_tags(q_res, res_out) for q in self.queries for _, q_res in q.query):
                    scaled_qty = qty_out * scale
                    res_tags_str = self._format_resource_tags(res_out)
                    lines.append(
                        f'    {proc.name} -->|"{scaled_qty.val:.2f} {scaled_qty.unit} {res_out.name}{res_tags_str}"| Query'
                    )

        all_query_items: list = []
        for q in self.queries:
            all_query_items.extend(q.query)
            
        for q_qty, q_res in sorted(all_query_items, key=lambda item: item[1].name):
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

    def generate_gantt(self, timeline, time_unit: str = "min") -> str:
        """Generate a Mermaid Gantt chart for a given TimelineSchedule."""
        min_time = None
        max_time = None
        for task in timeline.tasks:
            if min_time is None or task.start_time < min_time:
                min_time = task.start_time
            if max_time is None or task.end_time > max_time:
                max_time = task.end_time

        if min_time and max_time:
            span = max_time - min_time
            same_day = min_time.date() == max_time.date()
            if same_day:
                date_format = "HH:mm:ss"
                axis_format = "%H:%M"
                time_fmt = "%H:%M:%S"
            elif span.days < 7:
                date_format = "YYYY-MM-DD HH:mm:ss"
                axis_format = "%a %H:%M"
                time_fmt = "%Y-%m-%d %H:%M:%S"
            else:
                date_format = "YYYY-MM-DD HH:mm:ss"
                axis_format = "%Y-%m-%d"
                time_fmt = "%Y-%m-%d %H:%M:%S"
        else:
            date_format = "YYYY-MM-DD HH:mm:ss"
            axis_format = "%H:%M"
            time_fmt = "%Y-%m-%d %H:%M:%S"

        lines = ["```mermaid", "gantt", "    title Resource Flow Schedule", f"    dateFormat {date_format}"]
        lines.append(f"    axisFormat {axis_format}")
        
        # Group tasks by location/actor
        # Since actors aren't explicit, we can group by location
        location_tasks: dict = {}
        for task in timeline.tasks:
            loc = getattr(task, "location", "Unknown")
            if not loc:
                loc = "Global"
            if loc not in location_tasks:
                location_tasks[loc] = []
            location_tasks[loc].append(task)
            
        for loc, tasks in location_tasks.items():
            lines.append(f"    section {loc}")
            for task in tasks:
                name = getattr(task, "name", None)
                if not name and hasattr(task, "process"):
                    name = task.process.name
                if name:
                    name = name.replace(":", "-")
                
                start_t = task.start_time
                end_t = task.end_time
                if start_t == end_t:
                    import datetime
                    end_t = start_t + datetime.timedelta(seconds=1)

                # Format start and end times for mermaid
                start_str = start_t.strftime(time_fmt)
                end_str = end_t.strftime(time_fmt)
                
                lines.append(f"    {name} : {start_str}, {end_str}")
                
        lines.append("```")
        return "\n".join(lines)

    def generate_json(self, timeline=None, time_unit: str = "min") -> str:
        """Generate a JSON representation of the plan and graph."""
        import json
        
        result = {}
        
        # 1. Plan
        processes = self.dag.processes
        process_scales = self.dag.process_scales
        plan = []
        for i, proc in enumerate(processes, 1):
            scale = process_scales[proc.name]
            step = {
                "step": i,
                "process": proc.name,
                "scale": scale,
                "cost": proc.cost,
                "time": proc.time,
                "time_unit": proc.time_unit,
                "tags": sorted(list(proc.tags)) if proc.tags else [],
                "tools": [{"name": t.name, "quantity": t.quantity.val, "unit": t.quantity.unit} for t in sorted(proc.tools, key=lambda x: x.name)],
                "inputs": [],
                "outputs": []
            }
            for qty, res in proc.inp:
                scaled_qty = qty * scale
                source = self._find_source_process(res, proc)
                is_basic = res.basic or source is None
                step["inputs"].append({
                    "name": res.name,
                    "quantity": scaled_qty.val,
                    "unit": scaled_qty.unit,
                    "is_basic": is_basic,
                    "tags": sorted(list(res.tags - {"basic"})) + [f"!{t}" for t in sorted(res.negated_tags)]
                })
            for qty, res in proc.out:
                scaled_qty = qty * scale
                surplus_val = 0.0
                if res.name in self.surplus and self.surplus[res.name].val > 0.001:
                    surplus_qty = self.surplus[res.name]
                    try:
                        surplus_val = surplus_qty.convert_to(qty.unit).val
                    except ValueError:
                        pass
                step["outputs"].append({
                    "name": res.name,
                    "quantity": scaled_qty.val,
                    "unit": scaled_qty.unit,
                    "tags": sorted(list(res.tags - {"basic"})) + [f"!{t}" for t in sorted(res.negated_tags)],
                    "surplus": surplus_val
                })
            plan.append(step)
        result["plan"] = plan
        
        # 2. Basic Resources
        supplier_groups = {}
        for name, qty in sorted(self.demands.items()):
            edge = next((e for e in self.dag.edges if self.dag._is_basic_edge(e) and e.resource.name == name), None)
            basic_res = edge.resource if edge else None
            supplier = edge.source if edge and isinstance(edge.source, str) else None
            if not basic_res and self.basic_resources.get(name):
                basic_res = self.basic_resources[name][0]
            
            group_name = supplier if supplier else "Global"
            if group_name not in supplier_groups:
                supplier_groups[group_name] = []
                
            cost_val = basic_res.calculate_cost(qty) if basic_res and basic_res.cost > 0 else 0.0
            supplier_groups[group_name].append({
                "name": name,
                "quantity": qty.val,
                "unit": qty.unit,
                "cost": cost_val,
                "tags": sorted(list(basic_res.tags - {"basic"})) + [f"!{t}" for t in sorted(basic_res.negated_tags)] if basic_res else []
            })
        result["basic_resources"] = supplier_groups
        
        # 3. Metrics
        result["metrics"] = self.get_metrics(time_unit=time_unit)
        
        # 4. Gantt (Timeline)
        if timeline:
            gantt = {}
            location_tasks = {}
            for task in timeline.tasks:
                loc = getattr(task, "location", "Unknown")
                if not loc:
                    loc = "Global"
                if loc not in location_tasks:
                    location_tasks[loc] = []
                location_tasks[loc].append(task)
                
            time_fmt = "%Y-%m-%d %H:%M:%S"
            for loc, tasks in location_tasks.items():
                gantt[loc] = []
                for task in tasks:
                    name = getattr(task, "name", None)
                    if not name and hasattr(task, "process"):
                        name = task.process.name
                    
                    start_t = task.start_time
                    end_t = task.end_time
                    if start_t == end_t:
                        import datetime
                        end_t = start_t + datetime.timedelta(seconds=1)
                        
                    gantt[loc].append({
                        "name": name,
                        "start": start_t.strftime(time_fmt),
                        "end": end_t.strftime(time_fmt)
                    })
            result["gantt"] = gantt
            
        # 5. Graph
        nodes = []
        edges = []
        
        for proc in processes:
            scale = process_scales[proc.name]
            nodes.append({
                "id": proc.name,
                "type": "process",
                "name": proc.original_label,
                "scale": scale,
                "cost": proc.cost,
                "time": proc.time,
                "time_unit": proc.time_unit,
                "tags": sorted(list(proc.tags)) if proc.tags else [],
                "tools": [{"name": t.name, "quantity": t.quantity.val, "unit": t.quantity.unit} for t in sorted(proc.tools, key=lambda x: x.name)]
            })
            
        basic_reqs = self._basic_resource_names()
        supplier_nodes = set()
        
        for name in sorted(basic_reqs):
            edge = next((e for e in self.dag.edges if self.dag._is_basic_edge(e) and e.resource.name == name), None)
            res = edge.resource if edge else None
            supplier = edge.source if edge and isinstance(edge.source, str) else None
            if not res and self.basic_resources.get(name):
                res = self.basic_resources[name][0]
                
            if name in self.demands:
                qty = self.demands[name]
                cost_val = res.calculate_cost(qty) if res and res.cost > 0 else 0.0
                nodes.append({
                    "id": f"basic_{name}",
                    "type": "basic_resource",
                    "name": name,
                    "quantity": qty.val,
                    "unit": qty.unit,
                    "cost": cost_val,
                    "tags": sorted(list(res.tags - {"basic"})) + [f"!{t}" for t in sorted(res.negated_tags)] if res else []
                })
            else:
                nodes.append({
                    "id": f"basic_{name}",
                    "type": "basic_resource",
                    "name": name,
                    "quantity": 0.0,
                    "unit": "piece",
                    "cost": 0.0,
                    "tags": sorted(list(res.tags - {"basic"})) + [f"!{t}" for t in sorted(res.negated_tags)] if res else []
                })
                
            if supplier:
                supplier_id = supplier.replace(" ", "_")
                if supplier not in supplier_nodes:
                    supplier_nodes.add(supplier)
                    nodes.append({
                        "id": supplier_id,
                        "type": "supplier",
                        "name": supplier
                    })
                edges.append({
                    "source": supplier_id,
                    "target": f"basic_{name}",
                    "resource": name,
                    "quantity": 0.0,
                    "unit": "piece",
                    "tags": []
                })
                
        query_targets = []
        for q in self.queries:
            for qty, res in sorted(q.query, key=lambda item: item[1].name):
                query_targets.append({
                    "name": res.name,
                    "quantity": qty.val,
                    "unit": qty.unit,
                    "tags": sorted(list(res.tags - {"basic"})) + [f"!{t}" for t in sorted(res.negated_tags)]
                })
        nodes.append({
            "id": "Query",
            "type": "query",
            "targets": query_targets
        })
        
        for proc in processes:
            scale = process_scales[proc.name]
            for qty_in, res_in in proc.inp:
                scaled_qty = qty_in * scale
                source = self._find_source_process(res_in, proc)
                source_id = source.name if source is not None else f"basic_{res_in.name}"
                edges.append({
                    "source": source_id,
                    "target": proc.name,
                    "resource": res_in.name,
                    "quantity": scaled_qty.val,
                    "unit": scaled_qty.unit,
                    "tags": sorted(list(res_in.tags - {"basic"})) + [f"!{t}" for t in sorted(res_in.negated_tags)]
                })
                
            for qty_out, res_out in proc.out:
                if any(res_out.name == q_res.name and self._matches_tags(q_res, res_out) for q in self.queries for _, q_res in q.query):
                    scaled_qty = qty_out * scale
                    edges.append({
                        "source": proc.name,
                        "target": "Query",
                        "resource": res_out.name,
                        "quantity": scaled_qty.val,
                        "unit": scaled_qty.unit,
                        "tags": sorted(list(res_out.tags - {"basic"})) + [f"!{t}" for t in sorted(res_out.negated_tags)]
                    })
                    
        all_query_items = []
        for q in self.queries:
            all_query_items.extend(q.query)
            
        for q_qty, q_res in sorted(all_query_items, key=lambda item: item[1].name):
            source = self._find_source_process(q_res, "Query")
            if q_res.basic or source is None:
                produced_by_dag = any(
                    any(res_out.name == q_res.name and self._matches_tags(q_res, res_out)
                        for _, res_out in proc.out)
                    for proc in processes
                )
                if not produced_by_dag:
                    edges.append({
                        "source": f"basic_{q_res.name}",
                        "target": "Query",
                        "resource": q_res.name,
                        "quantity": q_qty.val,
                        "unit": q_qty.unit,
                        "tags": sorted(list(q_res.tags - {"basic"})) + [f"!{t}" for t in sorted(q_res.negated_tags)]
                    })
                    
        result["graph"] = {
            "nodes": nodes,
            "edges": edges
        }
        
        return json.dumps(result, indent=2)
