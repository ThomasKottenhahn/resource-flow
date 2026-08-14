import pytest
from pathlib import Path
from resource_flow.parser import RecipeParser

def test_external_import_basic(tmp_path):
    sub_file = tmp_path / "sub.rf"
    sub_file.write_text("peel: 100 g A * -> 100 g B;", encoding="utf-8")

    main_file = tmp_path / "main.rf"
    main_file.write_text("""
    use "sub.rf";
    make 100 g B;
    """, encoding="utf-8")

    parser = RecipeParser()
    resources, processes, query = parser.parse_file(str(main_file))

    assert len(processes) == 1
    assert list(processes)[0].name == "sub.rf::peel"
    assert list(query.query)[0][1].name == "B"

def test_external_import_specific(tmp_path):
    sub_file = tmp_path / "sub.rf"
    sub_file.write_text("""
    p1: 100 g A * -> 100 g B;
    p2: 100 g B -> 100 g C;
    """, encoding="utf-8")

    main_file = tmp_path / "main.rf"
    main_file.write_text("""
    use "sub.rf"::{p2};
    make 100 g C;
    """, encoding="utf-8")

    parser = RecipeParser()
    resources, processes, query = parser.parse_file(str(main_file))

    assert len(processes) == 1
    assert list(processes)[0].name == "sub.rf::p2"

def test_external_import_nested(tmp_path):
    sub_sub_file = tmp_path / "subsub.rf"
    sub_sub_file.write_text("p1: 100 g A * -> 100 g B;", encoding="utf-8")

    sub_file = tmp_path / "sub.rf"
    sub_file.write_text("""
    use "subsub.rf";
    p2: 100 g B -> 100 g C;
    """, encoding="utf-8")

    main_file = tmp_path / "main.rf"
    main_file.write_text("""
    use "sub.rf";
    make 100 g C;
    """, encoding="utf-8")

    parser = RecipeParser()
    resources, processes, query = parser.parse_file(str(main_file))

    assert len(processes) == 2
    names = {p.name for p in processes}
    assert "subsub.rf::p1" in names
    assert "sub.rf::p2" in names
