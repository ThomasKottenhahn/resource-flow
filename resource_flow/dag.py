from typing import Any
from .models import Process, Quantity, Resource


class DAGNode:
    def __init__(self, process: Process, scale: float = 1.0) -> None:
        self.process = process
        self.scale = float(scale)

    def __repr__(self) -> str:
        return f"DAGNode({self.process.name}, scale={self.scale:.4f})"


class DAGEdge:
    def __init__(
        self,
        source: Process | str | None,
        target: Process | str | None,
        resource: Resource,
        quantity: Quantity,
    ) -> None:
        self.source = source
        self.target = target
        self.resource = resource
        self.quantity = quantity

    def __repr__(self) -> str:
        src_name = self.source.name if isinstance(self.source, Process) else str(self.source)
        tgt_name = self.target.name if isinstance(self.target, Process) else str(self.target)
        return f"DAGEdge({src_name} -> {tgt_name}: {self.quantity} {self.resource.name})"


class DAG:
    def __init__(
        self,
        nodes: list[DAGNode] | None = None,
        edges: list[DAGEdge] | None = None,
    ) -> None:
        self.nodes: list[DAGNode] = nodes if nodes is not None else []
        self.edges: list[DAGEdge] = edges if edges is not None else []

    @property
    def processes(self) -> list[Process]:
        return [n.process for n in self.nodes]

    @property
    def process_scales(self) -> dict[str, float]:
        return {n.process.name: n.scale for n in self.nodes}

    # Backward-compat dict-like interface so existing code using solve() result
    # as a dict[str, float] continues to work.
    def __getitem__(self, key: str) -> float:
        return self.process_scales[key]

    def __contains__(self, key: object) -> bool:
        return key in self.process_scales

    def __iter__(self):
        return iter(self.process_scales)

    def _is_basic_edge(self, edge: DAGEdge) -> bool:
        return edge.source is None or isinstance(edge.source, str) or edge.resource.basic

    def calculate_metric(self, tag: str, unit: str | None = None) -> float:
        if tag == "cost":
            res_cost = 0.0
            for edge in self.edges:
                if self._is_basic_edge(edge):
                    res_cost += edge.resource.calculate_cost(edge.quantity)
            proc_cost = 0.0
            for node in self.nodes:
                proc_cost += node.process.cost * node.scale
            return res_cost + proc_cost

        elif tag == "time":
            target_unit = unit if unit is not None else "min"
            total_time = 0.0
            for node in self.nodes:
                proc = node.process
                if proc.time > 0:
                    scaled_time = proc.time * node.scale
                    q_time = Quantity(scaled_time, proc.time_unit)
                    converted = q_time.convert_to(target_unit)
                    total_time += converted.val
            return total_time

        else:
            val = 0.0
            prefix = tag + ":"

            for node in self.nodes:
                proc = node.process
                if tag in proc.tags:
                    val += 1.0
                for t in proc.tags:
                    if t.startswith(prefix):
                        kv_val = float(t.split(":")[1].strip())
                        val += kv_val * node.scale

            for edge in self.edges:
                if self._is_basic_edge(edge):
                    res = edge.resource
                    if tag in res.tags:
                        val += 1.0
                    for t in res.tags:
                        if t.startswith(prefix):
                            kv_val = float(t.split(":")[1].strip())
                            val += kv_val * edge.quantity.val

            if unit:
                try:
                    base_unit = Quantity(1.0, unit).to_base_unit().unit
                    q_val = Quantity(val, base_unit).convert_to(unit)
                    return q_val.val
                except ValueError:
                    pass

            return val

