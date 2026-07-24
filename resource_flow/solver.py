from .models import Process, Query, Quantity, Resource


class RecipeSolver:
    def __init__(self, processes: set[Process], query: Query) -> None:
        self.processes = sorted(list(processes), key=lambda p: p.name)
        self.query = query
        self.basic_resource_names = self._identify_basic_resources()

    def _identify_basic_resources(self) -> set[str]:
        basics = set()
        for p in self.processes:
            basics.update(r.name for _, r in p.inp if r.basic)
            basics.update(r.name for _, r in p.out if r.basic)
        basics.update(r.name for _, r in self.query.query if r.basic)
        return basics

    def is_basic(self, resource_name: str) -> bool:
        return resource_name in self.basic_resource_names

    def find_producer(self, resource_name: str) -> Process | None:
        for p in self.processes:
            if any(r.name == resource_name for _, r in p.out):
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

            producer = self.find_producer(res.name)
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

    def print_plan(self, process_scales: dict[str, float]) -> None:
        processes_in_dag, _ = self.build_dag()
        print("=== RECIPE EXECUTION PLAN ===")

        for i, proc in enumerate(processes_in_dag, 1):
            scale = process_scales[proc.name]
            print(f"\nStep {i}: {proc.name} (Scale: {scale:.4f})")
            print("  Inputs:")
            for qty, res in proc.inp:
                scaled_qty = qty * scale
                is_basic_str = " *" if self.is_basic(res.name) else ""
                print(
                    f"    - {scaled_qty.val:.2f} {scaled_qty.unit} {res.name}{is_basic_str}"
                )
            print("  Outputs:")
            for qty, res in proc.out:
                scaled_qty = qty * scale
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
                    f"    - {scaled_qty.val:.2f} {scaled_qty.unit} {res.name}{surplus_str}"
                )

        print("\n=== TOTAL BASIC RESOURCES REQUIRED ===")
        for name, qty in sorted(self.final_demands.items()):
            print(f"- {qty.val:.2f} {qty.unit} {name}")
        print("======================================\n")

    def generate_mermaid(self, process_scales: dict[str, float]) -> str:
        processes_in_dag, basic_reqs = self.build_dag()
        lines = ["```mermaid", "graph TD"]

        for proc in processes_in_dag:
            scale = process_scales[proc.name]
            lines.append(f'    {proc.name}["{proc.name} (x{scale:.2f})"]')

        for name in sorted(basic_reqs):
            if name in self.final_demands:
                qty = self.final_demands[name]
                lines.append(
                    f'    basic_{name}["{name}* ({qty.val:.2f} {qty.unit})"]'
                )
            else:
                lines.append(f'    basic_{name}["{name}*"]')

        query_targets = [
            f"{qty.val:.2f} {qty.unit} {res.name}" for qty, res in self.query.query
        ]
        lines.append(f'    Query["Query: {", ".join(query_targets)}"]')

        for proc in processes_in_dag:
            scale = process_scales[proc.name]
            for qty_in, res_in in proc.inp:
                scaled_qty = qty_in * scale
                if self.is_basic(res_in.name):
                    lines.append(
                        f'    basic_{res_in.name} -->|"{scaled_qty.val:.2f} {scaled_qty.unit}"| {proc.name}'
                    )
                else:
                    producer = self.find_producer(res_in.name)
                    if producer:
                        lines.append(
                            f'    {producer.name} -->|"{scaled_qty.val:.2f} {scaled_qty.unit} {res_in.name}"| {proc.name}'
                        )

            for qty_out, res_out in proc.out:
                if any(res_out.name == q_res.name for _, q_res in self.query.query):
                    scaled_qty = qty_out * scale
                    lines.append(
                        f'    {proc.name} -->|"{scaled_qty.val:.2f} {scaled_qty.unit} {res_out.name}"| Query'
                    )

        lines.append("```")
        return "\n".join(lines)
