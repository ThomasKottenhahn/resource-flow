from pathlib import Path
from lark import Lark, Transformer
from .models import AggregateGoal, Process, Query, Quantity, RelationalGoal, Resource


class RecipeTransformer(Transformer):
    def min_goal(self, items):
        return ("min_goal", str(items[0]))

    def max_goal(self, items):
        return ("max_goal", str(items[0]))

    def rel_goal(self, items):
        tag = str(items[0])
        op = str(items[1])
        val = float(items[2])
        unit = str(items[3]) if len(items) > 3 and items[3] is not None else None
        return ("rel_goal", tag, op, val, unit)

    def negated_tag(self, items):
        return ("negated", str(items[0]))

    def flag_tag(self, items):
        return ("flag", str(items[0]))

    def kv_tag(self, items):
        key = str(items[0])
        val = float(items[1])
        unit = str(items[2]) if len(items) == 3 and items[2] is not None else None
        return ("kv", key, val, unit)

    def tags(self, items):
        return list(items)

    def resource(self, items):
        val = float(items[0])
        unit = str(items[1])
        name = str(items[2])
        is_basic = False
        parsed_tags = []

        for item in items[3:]:
            if item is None:
                continue
            if isinstance(item, list):
                parsed_tags = item
            elif str(item) == "*":
                is_basic = True

        tags = set()
        negated_tags = set()
        cost = 0.0

        for t in parsed_tags:
            tag_type = t[0]
            if tag_type == "flag":
                tags.add(t[1])
            elif tag_type == "negated":
                negated_tags.add(t[1])
            elif tag_type == "kv":
                key, val_num, unit_str = t[1], t[2], t[3]
                if key == "cost":
                    cost = val_num
                elif key == "time":
                    raise ValueError("Resources cannot have a time tag")
                else:
                    tags.add(f"{key}:{val_num}")

        if is_basic:
            tags.add("basic")

        qty = Quantity(val, unit)
        unit_cost = 0.0
        cost_unit = None

        if cost > 0:
            if not is_basic:
                raise ValueError(
                    f"Cost can only be specified on basic resources, but '{name}' is not basic"
                )
            base_qty = qty.to_base_unit()
            unit_cost = cost / base_qty.val
            cost_unit = base_qty.unit

        return qty, Resource(
            name,
            basic=is_basic,
            tags=tags,
            negated_tags=negated_tags,
            cost=unit_cost,
            cost_unit=cost_unit,
        )

    def multiset(self, items):
        return set(items)

    def label(self, items):
        return str(items[0])

    def proc_header(self, items):
        if len(items) == 2:
            return str(items[0]), items[1]
        elif isinstance(items[0], list):
            return "", items[0]
        else:
            return str(items[0]), []

    def transition(self, items):
        name = ""
        parsed_tags = []
        inp = set()
        out = set()

        if len(items) == 3:
            header, inp, out = items
            if header is not None:
                name, parsed_tags = header
        else:
            inp, out = items[0], items[1]

        proc_tags = set()
        cost = 0.0
        proc_time = 0.0
        time_unit = "min"

        if parsed_tags:
            for t in parsed_tags:
                tag_type = t[0]
                if tag_type == "flag":
                    proc_tags.add(t[1])
                elif tag_type == "kv":
                    key, val_num, unit_str = t[1], t[2], t[3]
                    if key == "cost":
                        cost = val_num
                    elif key == "time":
                        proc_time = val_num
                        if unit_str:
                            time_unit = unit_str
                    else:
                        proc_tags.add(f"{key}:{val_num}")

        return Process(
            name,
            inp,
            out,
            cost=cost,
            time=proc_time,
            time_unit=time_unit,
            tags=proc_tags,
        )

    def query(self, items):
        multiset = items[-1]
        parsed_tags = []
        for item in items[:-1]:
            if isinstance(item, list):
                parsed_tags = item

        goals = []
        if parsed_tags:
            for t in parsed_tags:
                tag_type = t[0]
                if tag_type == "min_goal":
                    goals.append(AggregateGoal("min", t[1]))
                elif tag_type == "max_goal":
                    goals.append(AggregateGoal("max", t[1]))
                elif tag_type == "rel_goal":
                    goals.append(RelationalGoal(t[1], t[2], t[3], t[4]))
                elif tag_type == "flag":
                    flag_name = t[1]
                    if flag_name == "cheapest":
                        goals.append(AggregateGoal("min", "cost"))
                    elif flag_name == "fastest":
                        goals.append(AggregateGoal("min", "time"))
                    elif flag_name == "any":
                        goals.append("any")
                    else:
                        goals.append(AggregateGoal("min", flag_name))
                elif tag_type == "kv":
                    key, val_num = t[1], t[2]
                    unit_str = t[3] if len(t) > 3 else None
                    goals.append(RelationalGoal(key, "<=", val_num, unit_str))

        return Query(multiset, goals=goals if goals else ("any",))


    def program(self, items):
        processes = set()
        queries = []
        resources = set()

        for item in items:
            if isinstance(item, Process):
                processes.add(item)
                resources.update(r for _, r in item.inp)
                resources.update(r for _, r in item.out)
            elif isinstance(item, Query):
                queries.append(item)
                resources.update(r for _, r in item.query)

        combined_query = Query(set())
        for q in queries:
            combined_query.add(q)

        return resources, processes, combined_query



class RecipeParser:
    def __init__(self, grammar_path: str | None = None) -> None:
        if grammar_path is None:
            grammar_path = str(Path(__file__).parent / "lang.lark")
        grammar = Path(grammar_path).read_text(encoding="utf-8")
        self.lark = Lark(grammar, start="program")

    def parse_file(self, file_path: str) -> tuple[set[Resource], set[Process], Query]:
        content = Path(file_path).read_text(encoding="utf-8")
        tree = self.lark.parse(content)
        return RecipeTransformer().transform(tree)
