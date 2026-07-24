class Resource:
    def __init__(self, name: str, basic: bool) -> None:
        self.name = name
        self.basic = basic

    def __repr__(self) -> str:
        return f"{self.name} (basic)" if self.basic else self.name

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Resource):
            return False
        return self.name == other.name and self.basic == other.basic

    def __hash__(self) -> int:
        return hash((self.name, self.basic))


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
    def __init__(self, name: str, inp: set[tuple[Quantity, Resource]], out: set[tuple[Quantity, Resource]]) -> None:
        self.name = name
        self.inp = inp
        self.out = out

    def __repr__(self) -> str:
        return f"{self.name}: {self.inp} -> {self.out}"


class Query:
    def __init__(self, query: set[tuple[Quantity, Resource]]) -> None:
        self.query = query

    def __repr__(self) -> str:
        return f"Query for: {self.query}"

    def add(self, other: "Query") -> None:
        self.query = self.query | other.query
