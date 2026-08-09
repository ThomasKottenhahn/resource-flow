from .models import Process, Query, Quantity, Resource, SolutionCandidate
from .dag import DAG, DAGNode, DAGEdge
from .search import CandidateSearch

class ScaleResolver:
    """Calculates scaling factors for processes and constructs the final resource graph."""
    
    def __init__(self, query: Query, basic_resources: dict[str, Resource], search: CandidateSearch):
        self.query = query
        self.basic_resources = basic_resources
        self.search = search

    def _find_producer_in(self, res: Resource, procs: list[Process]) -> Process | None:
        """Find a process in a given list that produces the resource (tag-matched)."""
        for p in procs:
            for _, out_res in p.out:
                if out_res.name == res.name and self.search._matches_tags(res, out_res):
                    return p
        return None

    def build_dag_from_solution(self, cand: SolutionCandidate) -> DAG:
        """Construct a DAG with nodes (process + scale) and edges (resource flows)."""
        nodes = [DAGNode(process=p, scale=cand.scales[p.name]) for p in cand.processes]
        edges: list[DAGEdge] = []

        # Process-to-process edges
        for proc in cand.processes:
            scale = cand.scales[proc.name]
            for qty_in, res_in in proc.inp:
                source = self._find_producer_in(res_in, cand.processes)
                if source is not None and source != proc:
                    scaled_qty = qty_in * scale
                    edges.append(DAGEdge(
                        source=source,
                        target=proc,
                        resource=res_in,
                        quantity=scaled_qty,
                    ))

        # One basic edge per unique basic resource using final accumulated demands
        for name, qty in cand.demands.items():
            dag_res = cand.dag_basic_resources.get(name)
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
        for proc in cand.processes:
            scale = cand.scales[proc.name]
            for qty_out, res_out in proc.out:
                if any(
                    res_out.name == q_res.name and self.search._matches_tags(q_res, res_out)
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

    def solve_dag(self, cand: SolutionCandidate) -> None:
        """Calculate scale factors for all processes in the candidate and resolve total demands and surpluses."""
        demands: dict[str, Quantity] = {}
        for qty, res in self.query.query:
            if res.name in demands:
                demands[res.name] += qty
            else:
                demands[res.name] = qty

        surplus: dict[str, Quantity] = {}
        process_scales: dict[str, float] = {}

        for proc in reversed(cand.processes):
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
        for proc in cand.processes:
            for _, r in proc.inp:
                if r.basic or r.name in demands:
                    if r.name not in dag_basic_resources or r.cost > 0:
                        dag_basic_resources[r.name] = r
        for _, r in self.query.query:
            if r.basic or r.name in demands:
                if r.name not in dag_basic_resources or r.cost > 0:
                    dag_basic_resources[r.name] = r

        cand.scales = process_scales
        cand.demands = demands
        cand.surplus = surplus
        cand.dag_basic_resources = dag_basic_resources
        cand.dag = self.build_dag_from_solution(cand)
