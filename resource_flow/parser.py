from pathlib import Path
from lark import Lark, Transformer
from .models import AggregateGoal, Process, Query, Quantity, RelationalGoal, Resource, Tool, Module, Import, ProgramContext
from dataclasses import dataclass, field

@dataclass
class ModuleScope:
    processes: list[Process] = field(default_factory=list)
    imports: list[Import] = field(default_factory=list)

@dataclass
class ParseResult:
    resources: set[Resource] = field(default_factory=set)
    global_processes: set[Process] = field(default_factory=set)
    query: Query = field(default_factory=lambda: Query(set()))
    owned_processes: list[Process] = field(default_factory=list)
    reexported_processes: list[Process] = field(default_factory=list)
    defs: list[Resource] = field(default_factory=list)


class RecipeTransformer(Transformer):
    """Transforms the parsed syntax tree into domain models."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.macros = {}

    def let_stmt(self, items):
        """Parse a let statement."""
        ident = str(items[0])
        if ident in self.macros:
            from lark.exceptions import VisitError
            raise ValueError(f"Macro '{ident}' is already defined.")
        self.macros[ident] = items[1]
        return ("let", ident, items[1])

    def macro_ref(self, items):
        """Resolve a macro reference."""
        ident = str(items[0])
        if ident not in self.macros:
            from lark.exceptions import VisitError
            raise ValueError(f"Macro '{ident}' is used before declaration or not defined.")
        return self.macros[ident]

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
        result = set()
        for item in items:
            if isinstance(item, set):
                result.update(item)
            else:
                result.add(item)
        return result

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

        # Ensure no non-basic resource has cost in the transition
        for qty, res in (inp | out):
            if res.cost > 0 and not res.basic:
                raise ValueError(
                    f"Cost can only be specified on basic resources, but '{res.name}' is not basic"
                )

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

        # Ensure no non-basic resource has cost in the query
        for qty, res in multiset:
            if res.cost > 0 and not res.basic:
                raise ValueError(
                    f"Cost can only be specified on basic resources, but '{res.name}' is not basic"
                )

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


    def def_stmt(self, items):
        """Parse a standalone basic resource definition."""
        qty, resource = items[0]
        # def enforces basic implicitly even without a * 
        tags = set(resource.tags)
        tags.add("basic")
        resource.tags = frozenset(tags)
        return resource

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

    @staticmethod
    def _should_import(p: Process, imp: Import, prefix: str | None = None) -> bool:
        if not imp.items:
            return True
        rest = p.fully_qualified_label
        if prefix and rest.startswith(f"{prefix}::"):
            rest = rest[len(f"{prefix}::"):]
        first_part = rest.split("::")[0]
        return first_part in imp.items

    def parse_file(self, file_path: str) -> ProgramContext:
        """Parse a DSL file and return the parsed program context."""
        res = self._parse_file_internal(file_path, {})
        return ProgramContext(
            resources=res.resources,
            processes=res.global_processes,
            query=res.query,
            defs=res.defs,
        )

    def _parse_file_internal(self, file_path: str, _cache: dict[str, ParseResult]) -> ParseResult:
        target_resolved = str(Path(file_path).resolve())
        if target_resolved in _cache:
            cached = _cache[target_resolved]
            return ParseResult(
                query=Query(set()),
                owned_processes=cached.owned_processes,
                reexported_processes=cached.reexported_processes
            )

        # Add empty entry to break circular imports immediately
        _cache[target_resolved] = ParseResult()

        content = Path(file_path).read_text(encoding="utf-8")
        tree = self.lark.parse(content)
        items = RecipeTransformer().transform(tree)

        all_owned_processes: list[Process] = []
        all_reexported_processes: list[Process] = []
        queries: list[Query] = []
        defs: list[Resource] = []
        
        # Map module paths to their direct contents
        modules_map: dict[str, ModuleScope] = {}
        
        def walk(item_list, current_path: list[str]):
            mod_key = "::".join(current_path)
            if mod_key not in modules_map:
                modules_map[mod_key] = ModuleScope()
                
            for item in item_list:
                if isinstance(item, Process):
                    prefix = mod_key
                    if prefix:
                        item.fully_qualified_label = f"{prefix}::{item.original_label}"
                        item.name = item.fully_qualified_label
                    else:
                        item.fully_qualified_label = item.original_label
                        item.name = item.fully_qualified_label
                    
                    modules_map[mod_key].processes.append(item)
                    all_owned_processes.append(item)
                elif isinstance(item, Query):
                    queries.append(item)
                elif isinstance(item, Import):
                    modules_map[mod_key].imports.append(item)
                elif isinstance(item, Module):
                    walk(item.items, current_path + [item.name])
                elif isinstance(item, Resource):
                    defs.append(item)
                elif isinstance(item, tuple) and item[0] == "let":
                    pass  # Macros are already resolved during parsing
        walk(items, [])
        
        exported_by_module: dict[str, set[Process]] = {}
        
        def get_exports(mod_key: str, visited: set) -> set[Process]:
            if mod_key in exported_by_module:
                return exported_by_module[mod_key]
            
            if mod_key in visited:
                return set()
            visited.add(mod_key)
            
            exports = set()
            if mod_key in modules_map:
                exports.update(modules_map[mod_key].processes)
                
                for imp in modules_map[mod_key].imports:
                    # 1. Try local module first if it's not explicitly a file (string literal)
                    is_local_module = not imp.is_file and imp.module_name in modules_map
                    if is_local_module:
                        target_mod_key = imp.module_name
                        target_exports = get_exports(target_mod_key, visited)
                        
                        for p in target_exports:
                            if self._should_import(p, imp, prefix=target_mod_key):
                                exports.add(p)
                    else:
                        # 2. File import or fallback for bare module that wasn't local
                        target_path = Path(file_path).parent / imp.module_name
                        
                        # Implicit .rf resolution
                        if not target_path.exists() and not target_path.name.endswith(".rf"):
                            target_path_with_ext = target_path.with_suffix(".rf")
                            if target_path_with_ext.exists():
                                target_path = target_path_with_ext
                            elif imp.is_file:
                                # Keep the original target_path if it's explicitly a string and we didn't find .rf
                                # Actually, if implicit .rf is requested for "path/to/mod", we should just append it
                                # wait, what if the user wrote use "path/to/mod"; and mod without .rf doesn't exist?
                                # The spec says: use "path/to/mod"; resolves to path/to/mod.rf
                                target_path = target_path_with_ext

                        if not target_path.exists() and not imp.is_file:
                            # if use mod; and neither mod nor mod.rf exists locally, we should probably append .rf anyway so the error message mentions the right file
                            target_path = target_path.with_suffix(".rf")
                            
                        target_resolved_path = str(target_path.resolve())
                        
                        if target_resolved_path not in _cache:
                            self._parse_file_internal(str(target_path), _cache)
                        
                        target_res = _cache[target_resolved_path]
                        queries.append(target_res.query)
                        
                        prefix = imp.module_name
                        import copy
                        for p in target_res.owned_processes:
                            new_p = copy.copy(p)
                            new_p.fully_qualified_label = f"{prefix}::{new_p.fully_qualified_label}"
                            new_p.name = new_p.fully_qualified_label
                            
                            if self._should_import(p, imp):
                                exports.add(new_p)
                                all_reexported_processes.append(new_p)
                            
                        for p in target_res.reexported_processes:
                            if self._should_import(p, imp):
                                exports.add(p)
                                all_reexported_processes.append(p)
                                    
            exported_by_module[mod_key] = exports
            visited.remove(mod_key)
            return exports

        global_scope_processes = get_exports("", set())
        resources: set[Resource] = set()
        for p in global_scope_processes:
            resources.update(r for _, r in p.inp)
            resources.update(r for _, r in p.out)
        for d in defs:
            resources.add(d)
            
        combined_query = Query(set())
        for q in queries:
            combined_query.add(q)
            resources.update(r for _, r in q.query)
            
        res = ParseResult(
            resources=resources,
            global_processes=global_scope_processes,
            query=combined_query,
            owned_processes=all_owned_processes,
            reexported_processes=all_reexported_processes,
            defs=defs,
        )
        _cache[target_resolved] = res
        return res
