from pathlib import Path
from lark import Lark, Transformer
from .models import AggregateGoal, Process, Query, Quantity, RelationalGoal, Resource, Tool, Module, Import


class RecipeTransformer(Transformer):
    """Transforms the parsed syntax tree into domain models."""
    def min_goal(self, items):
        """Parse a minimize goal."""
        return ("min_goal", str(items[0]))

    def max_goal(self, items):
        """Parse a maximize goal."""
        return ("max_goal", str(items[0]))

    def rel_goal(self, items):
        """Parse a relational constraint goal."""
        tag = str(items[0])
        op = str(items[1])
        val = float(items[2])
        unit = str(items[3]) if len(items) > 3 and items[3] is not None else None
        return ("rel_goal", tag, op, val, unit)

    def negated_tag(self, items):
        """Parse a negated tag."""
        return ("negated", str(items[0]))

    def flag_tag(self, items):
        """Parse a boolean flag tag."""
        return ("flag", str(items[0]))

    def kv_tag(self, items):
        """Parse a key-value tag."""
        key = str(items[0])
        val = float(items[1])
        unit = str(items[2]) if len(items) == 3 and items[2] is not None else None
        return ("kv", key, val, unit)

    def tags(self, items):
        """Return a list of parsed tags."""
        return list(items)

    def resource(self, items):
        """Parse a resource and its quantity."""
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

        qty = Quantity(val, unit)
        base_resource_qty = qty.to_base_unit()

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
                    tag_val = Quantity(val_num, unit_str).to_base_unit().val if unit_str else val_num
                    if is_basic and qty.val > 0:
                        tag_val = tag_val / qty.val
                    tags.add(f"{key}:{tag_val}")

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
        """Parse a multiset of resources."""
        return set(items)

    def label(self, items):
        """Parse a label."""
        return str(items[0])

    def proc_header(self, items):
        """Parse a process header including name and tags."""
        if len(items) == 2:
            return str(items[0]), items[1]
        elif isinstance(items[0], list):
            return "", items[0]
        else:
            return str(items[0]), []

    def name(self, items):
        """Parse a multi-word name."""
        return " ".join(str(i) for i in items)

    def tool(self, items):
        """Parse a tool requirement."""
        if len(items) == 1:
            qty_val = 1.0
            unit = "piece"
            name = items[0]
        elif len(items) == 2:
            try:
                qty_val = float(items[0])
                unit = "piece"
            except ValueError:
                qty_val = 1.0
                unit = str(items[0])
            name = items[1]
        else:
            qty_val = float(items[0])
            unit = str(items[1])
            name = items[2]
        return Tool(str(name), Quantity(qty_val, unit))

    def tool_clause(self, items):
        """Parse a 'with tools' clause for processes."""
        return set(items)

    def using_clause(self, items):
        """Parse a 'using tools' clause for queries."""
        return set(items)

    def transition(self, items):
        """Parse a process transition (inputs -> outputs)."""
        name = ""
        parsed_tags = []
        inp = None
        out = None
        tools = set()

        for item in items:
            if item is None:
                continue
            if isinstance(item, tuple):
                name, parsed_tags = item
            elif isinstance(item, set):
                if len(item) > 0 and type(list(item)[0]).__name__ == "Tool":
                    tools = item
                elif inp is None:
                    inp = item
                else:
                    out = item

        if inp is None:
            inp = set()
        if out is None:
            out = set()

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
                        if unit_str:
                            base_qty = Quantity(val_num, unit_str).to_base_unit()
                            proc_tags.add(f"{key}:{base_qty.val}")
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
            tools=tools,
        )

    def query(self, items):
        """Parse a query instruction."""
        multiset = set()
        parsed_tags = []
        using = set()
        
        for item in items:
            if item is None:
                continue
            if isinstance(item, list):
                parsed_tags = item
            elif isinstance(item, set):
                if len(item) > 0 and type(list(item)[0]).__name__ == "Tool":
                    using = item
                else:
                    multiset = item

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

        return Query(multiset, goals=goals if goals else ("any",), tools=using)


    def program_item(self, items):
        return items[0]

    def module_item(self, items):
        return items[0]

    def module(self, items):
        name = str(items[0])
        return Module(name, list(items[1:]))

    def import_stmt(self, items):
        module_name_raw = str(items[0])
        is_file = False
        if module_name_raw.startswith('"') and module_name_raw.endswith('"'):
            module_name = module_name_raw[1:-1]
            is_file = True
        else:
            module_name = module_name_raw

        if len(items) > 1:
            import_path = items[1]
            if isinstance(import_path, str):
                return Import(module_name, [import_path], is_file=is_file)
            return Import(module_name, import_path, is_file=is_file)
        return Import(module_name, is_file=is_file)

    def import_path(self, items):
        if len(items) == 1:
            return str(items[0])
        return [str(i) for i in items]

    def program(self, items):
        """Parse a complete resource flow program."""
        return list(items)



class RecipeParser:
    """Parses a Resource Flow DSL file into domain models using Lark."""
    def __init__(self, grammar_path: str | None = None) -> None:
        if grammar_path is None:
            grammar_path = str(Path(__file__).parent / "lang.lark")
        grammar = Path(grammar_path).read_text(encoding="utf-8")
        self.lark = Lark(grammar, start="program")

    def parse_file(self, file_path: str) -> tuple[set[Resource], set[Process], Query]:
        """Parse a DSL file and return all discovered resources, processes, and the combined query."""
        resources, global_scope_processes, combined_query, _ = self._parse_file_internal(file_path, {})
        return resources, global_scope_processes, combined_query

    def _parse_file_internal(self, file_path: str, _cache: dict[str, tuple[Query, list[Process]]]) -> tuple[set[Resource], set[Process], Query, list[Process]]:
        target_resolved = str(Path(file_path).resolve())
        if target_resolved in _cache:
            cached_query, cached_all_procs = _cache[target_resolved]
            return set(), set(), Query(set()), cached_all_procs

        # Add empty entry to break circular imports immediately
        _cache[target_resolved] = (Query(set()), [])

        content = Path(file_path).read_text(encoding="utf-8")
        tree = self.lark.parse(content)
        items = RecipeTransformer().transform(tree)

        all_processes: list[Process] = []
        queries: list[Query] = []
        imports: list[Import] = []
        
        def walk(item_list, current_path: list[str]) -> set[Process]:
            scope_processes = set()
            for item in item_list:
                if isinstance(item, Process):
                    prefix = "::".join(current_path)
                    if prefix:
                        item.fully_qualified_label = f"{prefix}::{item.original_label}"
                        item.name = item.fully_qualified_label
                    else:
                        item.fully_qualified_label = item.original_label
                        item.name = item.fully_qualified_label
                    
                    all_processes.append(item)
                    scope_processes.add(item)
                elif isinstance(item, Query):
                    queries.append(item)
                elif isinstance(item, Import):
                    if not current_path:
                        imports.append(item)
                elif isinstance(item, Module):
                    walk(item.items, current_path + [item.name])
            return scope_processes
            
        global_scope_processes = walk(items, [])
        
        # Resolve external files first
        for imp in list(imports):
            if imp.is_file:
                target_path = Path(file_path).parent / imp.module_name
                _, _, target_query, target_all_processes = self._parse_file_internal(str(target_path), _cache)
                
                queries.append(target_query)
                
                prefix = imp.module_name
                import copy
                for p in target_all_processes:
                    new_p = copy.copy(p)
                    new_p.fully_qualified_label = f"{prefix}::{new_p.fully_qualified_label}"
                    new_p.name = new_p.fully_qualified_label
                    all_processes.append(new_p)

        for imp in imports:
            prefix = imp.module_name
            for p in all_processes:
                if p.fully_qualified_label.startswith(f"{prefix}::"):
                    rest = p.fully_qualified_label[len(prefix)+2:]
                    if not imp.items:
                        global_scope_processes.add(p)
                    else:
                        first_part = rest.split("::")[0]
                        if first_part in imp.items:
                            global_scope_processes.add(p)
                            
        resources = set()
        for p in global_scope_processes:
            resources.update(r for _, r in p.inp)
            resources.update(r for _, r in p.out)
            
        combined_query = Query(set())
        for q in queries:
            combined_query.add(q)
            resources.update(r for _, r in q.query)
            
        _cache[target_resolved] = (combined_query, all_processes)
            
        return resources, global_scope_processes, combined_query, all_processes
