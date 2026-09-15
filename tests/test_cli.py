"""CLI behavior that needs no database: exit codes for declaration/usage errors
(always 2 — never confused with check findings, which exit 1), and ontology
loading from a module path.
"""

from pathlib import Path

import pytest

from tank.cli import load_ontology, main

FIXTURES = Path(__file__).parent / "fixtures"


def exit_code(argv: list[str]) -> int:
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    return excinfo.value.code


def test_missing_ontology_file_exits_2():
    code = exit_code(["check", "--ontology", "nope.py", "--ns", "n", "--db", "d"])
    assert code == 2


def test_statically_broken_ontology_exits_2():
    code = exit_code(
        [
            "check",
            "--ontology",
            str(FIXTURES / "minimal" / "sabotage_static.py"),
            "--ns",
            "n",
            "--db",
            "d",
        ]
    )
    assert code == 2


def test_pydantic_shape_error_exits_2(tmp_path):
    bad = tmp_path / "ontology.py"
    bad.write_text(
        "from tank import Ontology, UnitType, Vector\n"
        'ontology = Ontology(types=[UnitType("a", table="a", vector=Vector("emb", 0))])\n'
    )
    code = exit_code(["check", "--ontology", str(bad), "--ns", "n", "--db", "d"])
    assert code == 2


def test_import_error_in_user_module_exits_2(tmp_path):
    bad = tmp_path / "ontology.py"
    bad.write_text("import module_that_does_not_exist\n")
    code = exit_code(["check", "--ontology", str(bad), "--ns", "n", "--db", "d"])
    assert code == 2


def test_missing_ns_db_is_usage_error(monkeypatch):
    monkeypatch.delenv("SURREAL_NS", raising=False)
    monkeypatch.delenv("SURREAL_DB", raising=False)
    code = exit_code(["check", "--ontology", str(FIXTURES / "minimal" / "ontology.py")])
    assert code == 2


def test_load_ontology_by_attribute_name():
    ontology = load_ontology(f"{FIXTURES / 'minimal' / 'ontology.py'}:ontology")
    assert ontology.type_named("report").table == "technical_assessment"


def test_load_ontology_sibling_import(tmp_path):
    (tmp_path / "helper.py").write_text("TABLE = 'technical_assessment'\n")
    (tmp_path / "ontology.py").write_text(
        "from helper import TABLE\n"
        "from tank import Ontology, UnitType\n"
        'ontology = Ontology(types=[UnitType("report", table=TABLE)])\n'
    )
    ontology = load_ontology(str(tmp_path / "ontology.py"))
    assert ontology.type_named("report").table == "technical_assessment"
