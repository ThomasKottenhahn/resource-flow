"""Verify that all .rf code examples embedded in docs/*.md files parse and solve successfully.

Each ```text fenced code block that looks like .rf syntax is extracted, written to a temp file,
parsed with RecipeParser, and — if it contains a make query — solved with RecipeSolver.
Snippets using file imports (use "...") are skipped since they depend on external files.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest

from resource_flow.parser import RecipeParser
from resource_flow.solvers import RecipeSolver

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"

# Regex to extract fenced code blocks tagged as ```text (the .rf convention)
_CODE_BLOCK_RE = re.compile(
    r"^```text\s*\n(.*?)^```",
    re.MULTILINE | re.DOTALL,
)


def _is_rf_snippet(code: str) -> bool:
    """Heuristic: an .rf snippet contains either '->' (process) or 'make' (query)."""
    return "->" in code or "make " in code


def _uses_external_import(code: str) -> bool:
    """Check if a snippet uses imports that resolve to external files.

    Quoted imports (``use "file";``) always reference external files.
    Bare imports (``use name;``) reference external files unless the
    module is defined inline in the same snippet via ``mod name { ... }``.
    """
    # Quoted imports are always external
    if re.search(r'use\s+"', code):
        return True
    # Bare imports: external unless the module is defined inline
    for match in re.finditer(r'\buse\s+(\w+)', code):
        module_name = match.group(1)
        if not re.search(rf'\bmod\s+{re.escape(module_name)}\s*\{{', code):
            return True
    return False


def _collect_snippets() -> list[tuple[str, int, str]]:
    """Walk docs/ and return (relative_path, line_number, code) for each .rf snippet."""
    snippets = []
    for md_file in sorted(DOCS_DIR.rglob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        rel = str(md_file.relative_to(DOCS_DIR))
        for match in _CODE_BLOCK_RE.finditer(content):
            code = match.group(1)
            if not _is_rf_snippet(code):
                continue
            line_no = content[: match.start()].count("\n") + 1
            snippets.append((rel, line_no, code))
    return snippets


_SNIPPETS = _collect_snippets()


@pytest.mark.parametrize(
    "rel_path, line_no, code",
    _SNIPPETS,
    ids=[f"{s[0]}:{s[1]}" for s in _SNIPPETS],
)
def test_doc_example_parses_and_solves(rel_path: str, line_no: int, code: str) -> None:
    if _uses_external_import(code):
        pytest.skip("snippet uses external imports")

    parser = RecipeParser()

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".rf", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        ctx = parser.parse_file(tmp_path)
        _resources, processes, query = ctx.resources, ctx.processes, ctx.query

        # If the snippet defines a query, also verify the solver runs
        if query.query:
            solver = RecipeSolver(processes, query)
            solver.solve()
    finally:
        Path(tmp_path).unlink(missing_ok=True)
