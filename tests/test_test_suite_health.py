import ast
import re
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTS_ROOT = PROJECT_ROOT / "tests"


def _is_module_docstring(node: ast.AST, index: int) -> bool:
    return (
        index == 0
        and isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def test_pytest_modules_are_collected_style_not_print_scripts():
    offenders: list[str] = []

    for path in sorted(TESTS_ROOT.glob("test*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        has_pytest_symbol = any(
            (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"))
            or (isinstance(node, ast.ClassDef) and node.name.startswith("Test"))
            for node in tree.body
        )
        if not has_pytest_symbol:
            offenders.append(f"{path.name}: no collected test function/class")

        for index, node in enumerate(tree.body):
            if _is_module_docstring(node, index):
                continue
            if isinstance(node, ast.Assert):
                offenders.append(f"{path.name}:{node.lineno}: top-level assert")
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                offenders.append(f"{path.name}:{node.lineno}: top-level call")

    assert offenders == []


def test_non_collected_test_support_files_do_not_hide_tests():
    offenders: list[str] = []

    for path in sorted(TESTS_ROOT.glob("*.py")):
        if path.name == "__init__.py" or path.name.startswith("test"):
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hidden_tests = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
        ]
        if hidden_tests:
            offenders.append(f"{path.name}: {', '.join(hidden_tests)}")

    assert offenders == []


def test_acceptance_matrix_references_existing_test_files():
    matrix = PROJECT_ROOT / "docs" / "acceptance-matrix.md"
    names = set(re.findall(r"\btest_[A-Za-z0-9_]+\.py\b", matrix.read_text(encoding="utf-8")))
    missing = sorted(name for name in names if not (TESTS_ROOT / name).exists())

    assert missing == []


def test_generated_test_artifacts_are_not_tracked():
    result = subprocess.run(
        ["git", "ls-files", "tests"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0

    tracked_generated = sorted(
        path
        for path in result.stdout.splitlines()
        if "__pycache__" in path or path.endswith((".pyc", ".pyo"))
    )
    assert tracked_generated == []
