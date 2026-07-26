class Resource:
    def __init__(
        self,
        name: str,
        basic: bool = False,
        tags: set[str] | frozenset[str] | None = None,
        negated_tags: set[str] | frozenset[str] | None = None,
        cost: float = 0.0,
    ) -> None:
        self.name = name
        initial_tags = set(tags) if tags else set()
        if basic:
            initial_tags.add("basic")
        self.tags = frozenset(initial_tags)
        self.negated_tags = frozenset(negated_tags) if negated_tags else frozenset()
        self.cost = float(cost)

    @property
    def basic(self) -> bool:
        return "basic" in self.tags

    def __repr__(self) -> str:
        parts = [self.name]
        if self.basic:
            parts.append("(basic)")
        other_tags = [t for t in sorted(self.tags) if t != "basic"]
        tag_strs = list(other_tags)
        tag_strs.extend(f"!{t}" for t in sorted(self.negated_tags))
        if self.cost > 0:
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
        )

    def __hash__(self) -> int:
        return hash((self.name, self.tags, self.negated_tags, self.cost))



class Quantity:
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
        if self.unit == target_unit:
            return Quantity(self.val, target_unit)

        weight_units = {"g": 1.0, "kg": 1000.0}
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

        raise ValueError(f"Cannot convert unit '{self.unit}' to '{target_unit}'")

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


class Process:
    def __init__(
        self,
        name: str,
        inp: set[tuple[Quantity, Resource]],
        out: set[tuple[Quantity, Resource]],
        cost: float = 0.0,
        time: float = 0.0,
        time_unit: str = "min",
        tags: set[str] | frozenset[str] | None = None,
    ) -> None:
        self.name = name
        self.inp = inp
        self.out = out
        self.cost = float(cost)
        self.time = float(time)
        self.time_unit = time_unit
        self.tags = frozenset(tags) if tags else frozenset()

    def __repr__(self) -> str:
        tag_strs = [t for t in sorted(self.tags)]
        if self.cost > 0:
            tag_strs.append(f"cost: {self.cost:.2f}")
        if self.time > 0:
            tag_strs.append(f"time: {self.time:.2f} {self.time_unit}")
        metrics_str = f" [{', '.join(tag_strs)}]" if tag_strs else ""
        return f"{self.name}{metrics_str}: {self.inp} -> {self.out}"




class Query:
    def __init__(self, query: set[tuple[Quantity, Resource]]) -> None:
        self.query = query

    def __repr__(self) -> str:
        return f"Query for: {self.query}"

    def add(self, other: "Query") -> None:
        self.query = self.query | other.query
