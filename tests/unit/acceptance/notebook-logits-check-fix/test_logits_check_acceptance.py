"""notebook-logits-check-fix 驗收測試：只鎖與做法無關的不變條件（靜態檢查，不連網路）。"""

import ast
import json
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[4]
NOTEBOOK = ROOT / "notebooks" / "bert_finetune.ipynb"
SPEC = ROOT / "docs" / "development-spec.md"


@pytest.fixture(scope="module")
def nb() -> dict[str, Any]:
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tree(nb: dict[str, Any]) -> tuple[ast.Module, str]:
    cells = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
    lines = []
    for cell in cells:
        for ln in cell.splitlines():
            lines.append("" if ln.lstrip().startswith(("!", "%")) else ln)
        lines.append("")
    src = "\n".join(lines)
    return ast.parse(src), src


def _guards(module: ast.Module, src: str, pattern: str) -> list[ast.If]:
    """回傳條件含 pattern、且 body 會 raise 的 if。"""
    out = []
    for node in ast.walk(module):
        if not isinstance(node, ast.If):
            continue
        raises = any(isinstance(n, ast.Raise) for b in node.body for n in ast.walk(b))
        if raises and re.search(pattern, ast.get_source_segment(src, node.test) or "", re.I):
            out.append(node)
    return out


def _first_package_call_line(module: ast.Module) -> int:
    lines = [
        n.lineno
        for n in ast.walk(module)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "build_package"
    ]
    assert lines, "找不到 build_package(...) 呼叫"
    return min(lines)


def test_notebook_has_no_outputs(nb: dict[str, Any]) -> None:
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            assert cell.get("outputs") == []
            assert cell.get("execution_count") is None


def test_logits_mismatch_raises_before_packaging(tree: tuple[ast.Module, str]) -> None:
    module, src = tree
    guards = _guards(module, src, r"diff|tol|thresh|delta|err")
    assert guards, "找不到比對 logits 差異後 raise 的檢查"
    pack_line = _first_package_call_line(module)
    assert any(g.lineno < pack_line for g in guards), "logits 檢查必須在打包之前"
    assert any(
        isinstance(c, ast.Compare) and any(isinstance(o, (ast.Gt, ast.GtE)) for o in c.ops)
        for g in guards
        for c in ast.walk(g.test)
    ), "超過門檻（> 或 >=）時要 raise"


def test_logits_comparison_still_uses_both_torch_and_onnx(tree: tuple[ast.Module, str]) -> None:
    _, src = tree
    assert re.search(r"np\.abs\(.*\)\.max\(\)|allclose|max_abs", src)
    assert "InferenceSession" in src and "model.eval()" in src


def test_ids_consistency_check_kept(tree: tuple[ast.Module, str]) -> None:
    module, src = tree
    assert "Tokenizer.from_file" in src
    guards = [
        g
        for g in _guards(module, src, r"ids")
        if any(
            isinstance(c, ast.Compare) and any(isinstance(o, ast.NotEq) for o in c.ops)
            for c in ast.walk(g.test)
        )
    ]
    assert guards, "ids 不一致時要 raise"
    assert guards[0].lineno < _first_package_call_line(module)


def test_first_cell_still_removes_diffusers(nb: dict[str, Any]) -> None:
    first = next("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    assert "diffusers" in first and "uninstall" in first


def test_spec_727_mentions_diffusers_removal() -> None:
    text = SPEC.read_text(encoding="utf-8")
    m = re.search(r"^### 7\.27 .*?(?=^#{2,3} )", text, re.S | re.M)
    assert m, "找不到 7.27 小節"
    assert "diffusers" in m.group(0), "7.27 要說明第一格會移除 diffusers"
