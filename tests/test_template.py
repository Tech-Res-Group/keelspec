"""The scaffold has to work, and its README has to be telling the truth.

`template/` is the front door: someone's first ten minutes with FastPDLC are a
`copier copy` and a `validate`. Its README promises a specific demo — rename a test,
get PAC-902 — and a promise about a diagnostic code with nothing gating it is the
exact drift this project exists to catch. So the demo is a test.

Rendering here is a plain substitution rather than a copier run. The templates use
no control flow (asserted below), so the two agree, and the suite stays free of a
dependency on copier.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "template"
ANSWERS = {
    "project_name": "Acme Payments",
    "product_dir": "product",
    "output_bundle": "build/product.generated.json",
    "fastpdlc_version": "0.4.0",
}


def _render(dest: pathlib.Path) -> None:
    for path in TEMPLATE.rglob("*"):
        if path.is_dir():
            continue
        rel = path.relative_to(TEMPLATE)
        out = dest / (str(rel)[: -len(".jinja")] if rel.suffix == ".jinja" else str(rel))
        out.parent.mkdir(parents=True, exist_ok=True)
        text = path.read_text(encoding="utf-8")
        for key, value in ANSWERS.items():
            text = re.sub(r"\{\{\s*" + key + r"\s*\}\}", value, text)
        assert "{{" not in text, f"unrendered variable left in {rel}"
        out.write_text(text, encoding="utf-8")


def _run(root: pathlib.Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "fastpdlc.cli", "-C", str(root),
         "-p", str(root / "product_hooks.py"), *args],
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout + result.stderr


@pytest.fixture
def scaffold(tmp_path_factory) -> pathlib.Path:
    root = tmp_path_factory.mktemp("scaffold")
    _render(root)
    assert _run(root, "build")[0] == 0
    return root


def _edit(path: pathlib.Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{path.name} no longer contains {old!r}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_the_templates_use_no_control_flow():
    """What makes the substitution above a faithful stand-in for copier."""
    for path in TEMPLATE.rglob("*.jinja"):
        assert "{%" not in path.read_text(encoding="utf-8"), path


def test_a_fresh_scaffold_validates(scaffold):
    """The first command after `copier copy` must not fail."""
    code, out = _run(scaffold, "validate")
    assert code == 0, out
    assert "0 error(s)" in out


def test_renaming_a_test_fails_the_build(scaffold):
    """The README's headline demo, quoted error code and all."""
    _edit(scaffold / "tests" / "test_example.py",
          "def test_the_example_holds_for_empty_input", "def test_renamed")
    code, out = _run(scaffold, "validate")
    assert code == 1
    assert "PAC-902" in out
    assert "is not declared in tests/test_example.py" in out


def test_deleting_the_test_file_fails_the_build(scaffold):
    (scaffold / "tests" / "test_example.py").unlink()
    code, out = _run(scaffold, "validate")
    assert code == 1 and "PAC-901" in out


def test_shipping_an_unproven_criterion_fails(scaffold):
    """Drafting without a test is allowed; shipping without one is not."""
    _edit(scaffold / "product" / "features" / "FEAT-example.md",
          "status: building", "status: shipped")
    assert _run(scaffold, "build")[0] == 0
    code, out = _run(scaffold, "validate")
    assert code == 1 and "PAC-900" in out


def test_the_core_graph_checks_still_run_under_the_plugin(scaffold):
    """A plugin adds checks; it must not quietly replace the engine's."""
    _edit(scaffold / "product" / "features" / "FEAT-example.md",
          "about: [TERM-example]", "about: [TERM-ghost]")
    assert _run(scaffold, "build")[0] == 0
    code, out = _run(scaffold, "validate")
    assert code == 1 and "PAC-020" in out


def test_the_readme_demo_names_a_code_the_plugin_registers(scaffold):
    """The README quotes PAC-900/901/902. If one were renumbered, this catches it."""
    readme = (scaffold / "README.md").read_text(encoding="utf-8")
    hooks = (scaffold / "product_hooks.py").read_text(encoding="utf-8")
    for code in re.findall(r"PAC-9\d\d", readme):
        assert f'register_code("{code}"' in hooks, f"{code} is quoted but never registered"
