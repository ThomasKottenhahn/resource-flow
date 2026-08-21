import pytest
from resource_flow.parser import RecipeParser
from pathlib import Path

def test_inline_transitive_imports(tmp_path):
    main_file = tmp_path / "main.rf"
    main_file.write_text("""
    mod oven {
        bake: 100 g A * -> 100 g B;
    }
    mod kitchen {
        use oven;
        prep: 100 g B -> 100 g C;
    }
    use kitchen;
    make 100 g C;
    """, encoding="utf-8")
    parser = RecipeParser()
    ctx = parser.parse_file(str(main_file))
    resources, processes, query = ctx.resources, ctx.processes, ctx.query
    
    names = {p.name for p in processes}
    # Do we expect oven::bake or kitchen::oven::bake?
    assert "oven::bake" in names
    assert "kitchen::prep" in names
    assert len(processes) == 2


def test_diamond_pattern_transitive_file_imports(tmp_path):
    common_file = tmp_path / "common.rf"
    common_file.write_text("p_common: 10 g X * -> 10 g Y;", encoding="utf-8")

    left_file = tmp_path / "left.rf"
    left_file.write_text("""
    use "common.rf";
    p_left: 10 g Y -> 10 g Z;
    """, encoding="utf-8")

    right_file = tmp_path / "right.rf"
    right_file.write_text("""
    use "common.rf";
    p_right: 10 g Y -> 10 g W;
    """, encoding="utf-8")

    main_file = tmp_path / "main.rf"
    main_file.write_text("""
    use "left.rf";
    use "right.rf";
    make 10 g Z;
    """, encoding="utf-8")

    parser = RecipeParser()
    ctx = parser.parse_file(str(main_file))
    resources, processes, query = ctx.resources, ctx.processes, ctx.query
    
    names = {p.name for p in processes}
    assert "common.rf::p_common" in names
    assert "left.rf::p_left" in names
    assert "right.rf::p_right" in names
    assert len(processes) == 3 # Deduplicated common
