from pathlib import Path
from lark import Lark, Transformer
from .models import Process, Query, Quantity, Resource


class RecipeTransformer(Transformer):
    def resource(self, items):
        val = float(items[0])
        unit = str(items[1])
        name = str(items[2])
        is_basic = len(items) == 4 and items[3] is not None
        return Quantity(val, unit), Resource(name, is_basic)

    def multiset(self, items):
        return set(items)

    def label(self, items):
        return str(items[0])

    def transition(self, items):
        if len(items) == 3:
            name, inp, out = items
        else:
            name, inp, out = "", items[0], items[1]
        return Process(name, inp, out)

    def query(self, items):
        multiset = items[-1]
        return Query(multiset)

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
