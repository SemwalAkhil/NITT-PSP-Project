"""
Herbal Almanac — Packaging Integrity & Hermetic CI Guard Regression Suite.

Verifies:
1. Built wheel archive contains all required non-Python runtime assets (SQL scripts, templates, CSS).
2. All test references to the uncommitted local database (data/inspection.db) contain strict skip guards.
3. Package metadata and package-data configurations in pyproject.toml are consistent.
"""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_wheel_archive_contains_all_runtime_assets(tmp_path: Path):
    """Proves that a standard wheel build bundles all SQL DDL, Jinja2 templates, and CSS files."""
    out_dir = tmp_path / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "build",
        "--wheel",
        "--no-isolation",
        "--outdir",
        str(out_dir),
        str(REPO_ROOT),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Wheel build failed:\nstdout: {res.stdout}\nstderr: {res.stderr}"

    wheel_files = list(out_dir.glob("*.whl"))
    assert len(wheel_files) == 1, f"Expected 1 wheel, found: {wheel_files}"
    wheel_path = wheel_files[0]

    expected_assets = [
        "herbal_almanac/data/herb_names.csv",
        "herbal_almanac/data/illness_glossary.csv",
        "herbal_almanac/herb_view.py",
        "herbal_almanac/migrations/stage_c_ddl_and_triggers.sql",
        "herbal_almanac/migrations/virya_reconciliation.sql",
        "herbal_almanac/static/favicon.svg",
        "herbal_almanac/static/placeholder-herb.svg",
        "herbal_almanac/static/styles.css",
        "herbal_almanac/templates/attributes.html",
        "herbal_almanac/templates/base.html",
        "herbal_almanac/templates/dashboard.html",
        "herbal_almanac/templates/guide.html",
        "herbal_almanac/templates/herb_detail.html",
        "herbal_almanac/templates/herb_detail_semantic.html",
        "herbal_almanac/templates/herb_form.html",
        "herbal_almanac/templates/herbs.html",
        "herbal_almanac/templates/illness_detail.html",
        "herbal_almanac/templates/illness_form.html",
        "herbal_almanac/templates/illnesses.html",
        "herbal_almanac/templates/records.html",
        "herbal_almanac/templates/_icons.html",
        "herbal_almanac/templates/_language_bar.html",
        "herbal_almanac/templates/treatment_form.html",
        "herbal_almanac/templates/treatments.html",
        "herbal_almanac/templates/virya_reconciliation.html",
    ]

    with zipfile.ZipFile(wheel_path, "r") as zf:
        namelist = zf.namelist()
        for asset in expected_assets:
            assert asset in namelist, f"Asset '{asset}' missing from built wheel archive!"

        # Verify CSV content readability
        csv_content = zf.read("herbal_almanac/data/illness_glossary.csv").decode("utf-8")
        assert "Original_Term,English," in csv_content

        # Verify SQL content readability
        ddl_content = zf.read("herbal_almanac/migrations/stage_c_ddl_and_triggers.sql").decode("utf-8")
        assert "CREATE TABLE IF NOT EXISTS dravyaguna_concepts" in ddl_content

        virya_content = zf.read("herbal_almanac/migrations/virya_reconciliation.sql").decode("utf-8")
        assert "SELECT" in virya_content


def check_test_function_for_unguarded_inspection_db(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef, full_code: str
) -> tuple[bool, bool]:
    """Inspects a test function AST for executable references to inspection.db and skip guards.

    Returns (has_executable_reference, has_skip_guard).
    Docstrings and comments are strictly ignored.
    """
    docstring_node = None
    if func_node.body and isinstance(func_node.body[0], ast.Expr) and isinstance(func_node.body[0].value, ast.Constant):
        docstring_node = func_node.body[0].value

    # Collect string constants in executable code (strictly excluding docstring)
    code_strings: list[str] = [
        c.value
        for c in ast.walk(func_node)
        if isinstance(c, ast.Constant) and isinstance(c.value, str) and c is not docstring_node
    ]

    has_ref = any("inspection.db" in s for s in code_strings)
    if not has_ref:
        return False, False

    # Check for skip guard via decorator or pytest.skip call
    has_skip = False
    for dec in func_node.decorator_list:
        dec_seg = ast.get_source_segment(full_code, dec) or ""
        if "skip" in dec_seg:
            has_skip = True
            break

    if not has_skip:
        for c in ast.walk(func_node):
            if isinstance(c, ast.Call):
                if isinstance(c.func, ast.Attribute) and c.func.attr == "skip":
                    has_skip = True
                    break
                elif isinstance(c.func, ast.Name) and c.func.id == "skip":
                    has_skip = True
                    break

    if not has_skip:
        func_seg = ast.get_source_segment(full_code, func_node) or ""
        if "pytest.skip" in func_seg or "skipif" in func_seg:
            has_skip = True

    return has_ref, has_skip


def test_all_inspection_db_references_have_skip_guards():
    """Guarantees that no test references data/inspection.db in executable code without an explicit pytest.skip guard."""
    tests_dir = REPO_ROOT / "tests"
    violating_tests: list[str] = []

    for py_path in sorted(tests_dir.glob("test_*.py")):
        if py_path.name == "test_packaging_and_guards.py":
            continue
        code = py_path.read_text(encoding="utf-8")
        if "inspection.db" not in code:
            continue

        tree = ast.parse(code, filename=str(py_path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                has_ref, has_skip = check_test_function_for_unguarded_inspection_db(node, code)
                if has_ref and not has_skip:
                    violating_tests.append(f"{py_path.name}::{node.name}")

    assert not violating_tests, (
        f"The following tests reference 'inspection.db' in executable code without an explicit pytest.skip guard: {violating_tests}. "
        "In CI environments without data/inspection.db, tests must skip cleanly rather than failing."
    )


def test_inspection_db_guard_detects_unguarded_and_ignores_docstring_only():
    """Unit test proving the guard accurately catches executable references while ignoring docstrings/comments."""
    sample_code = '''
def test_docstring_and_comment_only():
    """This test mentions data/inspection.db in its docstring."""
    # A comment mentioning inspection.db should be ignored by the AST
    val = 1 + 1
    assert val == 2

def test_unguarded_code_reference():
    """Docstring without mention."""
    from pathlib import Path
    db_path = Path("data") / "inspection.db"
    assert db_path.name == "inspection.db"

def test_guarded_code_reference():
    """Guarded test."""
    import pytest
    from pathlib import Path
    db_path = Path("data") / "inspection.db"
    if not db_path.exists():
        pytest.skip("DB absent")
    assert db_path.name == "inspection.db"
'''
    tree = ast.parse(sample_code)
    results: dict[str, tuple[bool, bool]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            has_ref, has_skip = check_test_function_for_unguarded_inspection_db(node, sample_code)
            results[node.name] = (has_ref, has_skip)

    # 1. Docstring and comment only -> no executable reference
    assert results["test_docstring_and_comment_only"] == (False, False)

    # 2. Unguarded code reference -> detected and flagged as missing skip
    assert results["test_unguarded_code_reference"] == (True, False)

    # 3. Guarded code reference -> detected and recognized as guarded
    assert results["test_guarded_code_reference"] == (True, True)


def test_pyproject_extras_and_base_dependencies_guard():
    """Guarantees pyproject.toml has no deprecated web or translate extras, no deep-translator,
    and includes essential web packages in base dependencies."""
    import re

    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib
        except ModuleNotFoundError:
            try:
                from pip._vendor import tomli as tomllib
            except ModuleNotFoundError:
                tomllib = None

    pyproject_path = REPO_ROOT / "pyproject.toml"

    if tomllib is not None:
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)
        project = pyproject.get("project", {})
        opt_deps = project.get("optional-dependencies", {})
        deps = project.get("dependencies", [])
        dev_deps = opt_deps.get("dev", [])
    else:
        text = pyproject_path.read_text(encoding="utf-8")
        opt_deps = {}
        if "[project.optional-dependencies]" in text:
            section = text.split("[project.optional-dependencies]")[1].split("[")[0]
            for line in section.strip().splitlines():
                if "=" in line:
                    opt_deps[line.split("=")[0].strip()] = []
        deps_match = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
        deps = [s.strip().strip('"\'') for s in deps_match.group(1).split(",") if s.strip().strip('"\'')] if deps_match else []
        dev_match = re.search(r"dev\s*=\s*\[(.*?)\]", text, re.DOTALL)
        dev_deps = [s.strip().strip('"\'') for s in dev_match.group(1).split(",") if s.strip().strip('"\'')] if dev_match else []
        opt_deps["dev"] = dev_deps

    # 1. "web" NOT in [project.optional-dependencies]
    assert "web" not in opt_deps, "'web' extra must not exist in optional-dependencies"

    # 2. "translate" NOT in [project.optional-dependencies]
    assert "translate" not in opt_deps, "'translate' extra must not exist in optional-dependencies"

    # 3. "deep-translator" not mentioned anywhere in dependencies or dev
    all_deps_text = " ".join(deps + dev_deps)
    assert "deep-translator" not in all_deps_text.lower(), "deep-translator should not be in dependencies"
    assert "deep_translator" not in all_deps_text.lower(), "deep_translator should not be in dependencies"

    # 4. dependencies contains fastapi, uvicorn, jinja2, python-multipart
    base_names = [d.split(";")[0].split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip().lower() for d in deps]
    for required in ["fastapi", "uvicorn", "jinja2", "python-multipart"]:
        assert required in base_names, f"Base dependencies must contain '{required}'"

    # 5. dev contains pytest, httpx
    dev_names = [d.split(";")[0].split(">")[0].split("<")[0].split("=")[0].split("[")[0].strip().lower() for d in dev_deps]
    for required in ["pytest", "httpx"]:
        assert required in dev_names, f"Dev dependencies must contain '{required}'"


