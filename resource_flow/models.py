from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .dag import DAG


class Resource:
    """Represents a tangible resource, either required or produced in the system."""
    def __init__(
        self,
        name: str,
        basic: bool = False,
        tags: set[str] | frozenset[str] | None = None,
        negated_tags: set[str] | frozenset[str] | None = None,
        cost: float = 0.0,
        cost_unit: str | None = None,
    ) -> None:
        self.name = name
        initial_tags = set(tags) if tags else set()
        if basic:
            initial_tags.add("basic")
        self.tags = frozenset(initial_tags)
        self.negated_tags = frozenset(negated_tags) if negated_tags else frozenset()
        self.cost = float(cost)
        self.cost_unit = cost_unit

        if self.cost > 0 and not self.basic:
            raise ValueError(
                f"Cost can only be specified on basic resources, but '{self.name}' is not basic"
            )

    @property
    def basic(self) -> bool:
        """Return True if this resource is basic (externally supplied)."""
        return "basic" in self.tags

    def calculate_cost(self, qty: "Quantity") -> float:
        """Calculate the total cost of this resource for a given quantity."""
        if self.cost <= 0:
            return 0.0
        if self.cost_unit:
            return qty.convert_to(self.cost_unit).val * self.cost
        return qty.val * self.cost

    def __repr__(self) -> str:
        parts = [self.name]
        if self.basic:
            parts.append("(basic)")
        other_tags = [t for t in sorted(self.tags) if t != "basic"]
        tag_strs = list(other_tags)
        tag_strs.extend(f"!{t}" for t in sorted(self.negated_tags))
        if self.cost > 0:
            if self.cost_unit:
                tag_strs.append(f"cost: {self.cost:.4f}/{self.cost_unit}")
            else:
                tag_strs.append(f"cost: {self.cost:.2f}")
        if tag_strs:
            parts.append(f"[{', '.join(tag_strs)}]")
        return " ".join(parts)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Resource):
            return False
        return (
            self.name == other.name
            and self.tags == other.tags
            and self.negated_tags == other.negated_tags
            and self.cost == other.cost
            and self.cost_unit == other.cost_unit
        )

    def __hash__(self) -> int:
        return hash(
            (self.name, self.tags, self.negated_tags, self.cost, self.cost_unit)
        )


class Quantity:
    """Represents a numeric value associated with a unit of measurement."""
    def __init__(self, val: float, unit: str) -> None:
        self.val = val
        self.unit = unit

    def __repr__(self) -> str:
        return f"{self.val} {self.unit}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Quantity):
            return False
        return self.val == other.val and self.unit == other.unit

    def __hash__(self) -> int:
        return hash((self.val, self.unit))

    def convert_to(self, target_unit: str) -> "Quantity":
        """Convert this quantity to a target unit, raising ValueError if units are incompatible."""
        if self.unit == target_unit:
            return Quantity(self.val, target_unit)

        weight_units = {"mg": 0.001, "g": 1.0, "kg": 1000.0}
        if self.unit in weight_units and target_unit in weight_units:
            val_in_g = self.val * weight_units[self.unit]
            return Quantity(val_in_g / weight_units[target_unit], target_unit)

        volume_units = {"ml": 1.0, "l": 1000.0}
        if self.unit in volume_units and target_unit in volume_units:
            val_in_ml = self.val * volume_units[self.unit]
            return Quantity(val_in_ml / volume_units[target_unit], target_unit)

        time_units = {"s": 1.0, "min": 60.0, "h": 3600.0}
        if self.unit in time_units and target_unit in time_units:
            val_in_s = self.val * time_units[self.unit]
            return Quantity(val_in_s / time_units[target_unit], target_unit)

        energy_units = {"kJ": 1.0, "kWh": 3600.0}
        if self.unit in energy_units and target_unit in energy_units:
            val_in_kj = self.val * energy_units[self.unit]
            return Quantity(val_in_kj / energy_units[target_unit], target_unit)

        raise ValueError(f"Cannot convert unit '{self.unit}' to '{target_unit}'")

    def to_base_unit(self) -> "Quantity":
        """Convert this quantity to its canonical base unit (e.g., kg -> g)."""
        weight_units = {"mg": "g", "g": "g", "kg": "g"}
        if self.unit in weight_units:
            return self.convert_to("g")

        volume_units = {"ml": "ml", "l": "ml"}
        if self.unit in volume_units:
            return self.convert_to("ml")

        time_units = {"s": "s", "min": "s", "h": "s"}
        if self.unit in time_units:
            return self.convert_to("s")

        energy_units = {"kJ": "kJ", "kWh": "kJ"}
        if self.unit in energy_units:
            return self.convert_to("kJ")

        return Quantity(self.val, self.unit)

    def __add__(self, other: "Quantity") -> "Quantity":
        try:
            converted = other.convert_to(self.unit)
            return Quantity(self.val + converted.val, self.unit)
        except ValueError:
            raise ValueError(
                f"Incompatible units: '{self.unit}' and '{other.unit}'"
            )

    def __sub__(self, other: "Quantity") -> "Quantity":
        try:
            converted = other.convert_to(self.unit)
            return Quantity(self.val - converted.val, self.unit)
        except ValueError:
            raise ValueError(
                f"Incompatible units: '{self.unit}' and '{other.unit}'"
            )

    def __mul__(self, factor: float) -> "Quantity":
        return Quantity(self.val * factor, self.unit)

    def __rmul__(self, factor: float) -> "Quantity":
        return self.__mul__(factor)


class Tool:
    """Represents a non-consumable tool or equipment required by a process."""
    def __init__(self, name: str, quantity: Quantity) -> None:
        self.name = name
        self.quantity = quantity

    def __repr__(self) -> str:
        return f"{self.quantity} {self.name}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Tool):
            return False
        return self.name == other.name and self.quantity == other.quantity

    def __hash__(self) -> int:
        return hash((self.name, self.quantity))


class Process:
    """Represents a production process transforming input resources into output resources."""
    def __init__(
        self,
        original_label: str,
        inp: set[tuple[Quantity, Resource]],
        out: set[tuple[Quantity, Resource]],
        cost: float = 0.0,
        time: float = 0.0,
        time_unit: str = "min",
        tags: set[str] | frozenset[str] | None = None,
        tools: set["Tool"] | frozenset["Tool"] | None = None,
        fully_qualified_label: str | None = None,
    ) -> None:
        self.original_label = original_label
        self.fully_qualified_label = fully_qualified_label or original_label
        self.name = self.fully_qualified_label
        self.inp = inp
        self.out = out
        self.cost = float(cost)
        self.time = float(time)
        self.time_unit = time_unit
        self.tags = frozenset(tags) if tags else frozenset()
        self.tools = frozenset(tools) if tools else frozenset()

    def __repr__(self) -> str:
        tag_strs = [t for t in sorted(self.tags)]
        if self.cost > 0:
            tag_strs.append(f"cost: {self.cost:.2f}")
        if self.time > 0:
            tag_strs.append(f"time: {self.time:.2f} {self.time_unit}")
        metrics_str = f" [{', '.join(tag_strs)}]" if tag_strs else ""
        return f"{self.name}{metrics_str}: {self.inp} -> {self.out}"

    def has_required_tools(self, available_tools: frozenset["Tool"] | set["Tool"]) -> bool:
        """Check if the given available tools satisfy this process's tool requirements."""
        for required_tool in self.tools:
            tool_found = False
            for avail_tool in available_tools:
                if avail_tool.name == required_tool.name:
                    try:
                        converted_avail = avail_tool.quantity.convert_to(required_tool.quantity.unit)
                        if converted_avail.val >= required_tool.quantity.val:
                            tool_found = True
                            break
                    except ValueError:
                        pass
            if not tool_found:
                return False
        return True


class Import:
    """Represents a use statement for bringing module contents into scope."""
    def __init__(self, module_name: str, items: list[str] | None = None) -> None:
        self.module_name = module_name
        self.items = items

    def __repr__(self) -> str:
        if self.items:
            return f"use {self.module_name}::{{{', '.join(self.items)}}}"
        return f"use {self.module_name}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Import):
            return False
        return self.module_name == other.module_name and self.items == other.items


class Module:
    """Represents an inline module containing processes and other modules."""
    def __init__(self, name: str, items: list[Any]) -> None:
        self.name = name
        self.items = items

    def __repr__(self) -> str:
        return f"mod {self.name} {{ {len(self.items)} items }}"


class Goal:
    """Abstract base class for optimization or constraint goals."""
    def evaluate(self, dag: Any) -> float | bool:
        """Evaluate the goal against a resolved DAG."""
        raise NotImplementedError


class AggregateGoal(Goal):
    """Represents an optimization goal (e.g., minimize cost)."""
    def __init__(self, op: str, tag: str) -> None:
        self.op = op.lower()
        self.tag = tag

    def evaluate(self, dag: Any) -> float:
        val = float(dag.calculate_metric(self.tag))
        return -val if self.op == "max" else val

    def __repr__(self) -> str:
        return f"{self.op} {self.tag}"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            if self.tag == "cost" and self.op == "min" and other in ("cheapest", "min cost"):
                return True
            if self.tag == "time" and self.op == "min" and other in ("fastest", "min time"):
                return True
            return f"{self.op} {self.tag}" == other
        if not isinstance(other, AggregateGoal):
            return False
        return self.op == other.op and self.tag == other.tag

    def __hash__(self) -> int:
        return hash((self.op, self.tag))


class RelationalGoal(Goal):
    """Represents a hard constraint goal (e.g., time <= 30 min)."""
    def __init__(self, tag: str, op: str, val: float, unit: str | None = None) -> None:
        self.tag = tag
        self.op = op
        self.val = float(val)
        self.unit = unit

    def evaluate(self, dag: Any) -> bool:
        target_val = self.val
        if self.unit:
            try:
                target_val = Quantity(self.val, self.unit).to_base_unit().val
                metric_val = float(dag.calculate_metric(self.tag, unit="s" if self.unit in {"s", "min", "h"} else self.unit))
            except ValueError:
                metric_val = float(dag.calculate_metric(self.tag, unit=self.unit))
        else:
            metric_val = float(dag.calculate_metric(self.tag))

        if self.op == "<=": return metric_val <= target_val
        if self.op == "<": return metric_val < target_val
        if self.op == ">=": return metric_val >= target_val
        if self.op == ">": return metric_val > target_val
        if self.op == "==": return metric_val == target_val
        if self.op == "!=": return metric_val != target_val
        return False

    def __repr__(self) -> str:
        unit_str = f" {self.unit}" if self.unit else ""
        return f"{self.tag} {self.op} {self.val}{unit_str}"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return str(self) == other
        if not isinstance(other, RelationalGoal):
            return False
        return (
            self.tag == other.tag
            and self.op == other.op
            and self.val == other.val
            and self.unit == other.unit
        )

    def __hash__(self) -> int:
        return hash((self.tag, self.op, self.val, self.unit))


class AnyGoal(Goal):
    """Represents a wildcard goal that accepts any valid solution."""
    def evaluate(self, dag: Any) -> float:
        return 0.0

    def __repr__(self) -> str:
        return "any"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return other == "any"
        return isinstance(other, AnyGoal)

    def __hash__(self) -> int:
        return hash("any")


GoalType = Goal | str


class Query:
    """Represents the end goal or target of a resource flow solver query."""
    def __init__(
        self,
        query: set[tuple[Quantity, Resource]],
        goals: tuple[GoalType, ...] | list[GoalType] | None = None,
        tools: set["Tool"] | frozenset["Tool"] | None = None,
    ) -> None:
        self.query = query
        self.tools = frozenset(tools) if tools else frozenset()
        normalized: list[Goal] = []
        if goals:
            for g in goals:
                if isinstance(g, Goal):
                    normalized.append(g)
                elif g == "cheapest" or g == "min cost":
                    normalized.append(AggregateGoal("min", "cost"))
                elif g == "fastest" or g == "min time":
                    normalized.append(AggregateGoal("min", "time"))
                elif g == "any":
                    normalized.append(AnyGoal())
                elif isinstance(g, str):
                    normalized.append(AggregateGoal("min", g))
                else:
                    normalized.append(g)
        self.goals: tuple[Goal, ...] = tuple(normalized) if normalized else (AnyGoal(),)

    def __repr__(self) -> str:
        goal_str = f" [{', '.join(str(g) for g in self.goals)}]" if self.goals != (AnyGoal(),) else ""
        return f"Query{goal_str} for: {self.query}"

    def add(self, other: "Query") -> None:
        """Merge another query's requirements and tools into this one."""
        self.query = self.query | other.query
        self.tools = self.tools | other.tools
        if other.goals != (AnyGoal(),):
            self.goals = other.goals

    def calculate_missing_tools(self, processes: list["Process"]) -> dict[str, Quantity]:
        """Determine which tools required by the given processes are missing from this query's available tools."""
        req_tools: dict[str, Quantity] = {}
        for p in processes:
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
            for avail_t in self.tools:
                if avail_t.name == name:
                    try:
                        avail_val = avail_t.quantity.convert_to(req_qty.unit).val
                        break
                    except ValueError:
                        pass
            if avail_val < req_qty.val:
                missing[name] = Quantity(req_qty.val - avail_val, req_qty.unit)
        return missing


@dataclass
class SolutionCandidate:
    """Encapsulates the state of a potential graph solution during the solving pipeline."""
    processes: list[Process]
    basic_requirements: set[str]
    scales: dict[str, float] = field(default_factory=dict)
    demands: dict[str, Quantity] = field(default_factory=dict)
    surplus: dict[str, Quantity] = field(default_factory=dict)
    dag_basic_resources: dict[str, Resource] = field(default_factory=dict)
    dag: "DAG | None" = None
    scores: tuple[Any, ...] = ()
    tie_breaker: tuple[str, ...] = ()
