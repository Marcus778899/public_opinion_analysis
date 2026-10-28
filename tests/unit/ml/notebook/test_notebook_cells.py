"""notebook 每格語法與純函式的單元測試（不執行 torch／下載，開發規格 7.27）。"""

import ast
import json
import textwrap
from pathlib import Path
from typing import Any

import numpy as np
import pytest

NOTEBOOK = Path(__file__).resolve().parents[4] / "notebooks" / "bert_finetune.ipynb"


def _cells() -> list[str]:
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


def _strip_magics(cell: str) -> str:
    return "\n".join("" if ln.lstrip().startswith(("!", "%")) else ln for ln in cell.splitlines())


def _load_function(name: str, namespace: dict[str, Any]) -> Any:
    for cell in _cells():
        for node in ast.parse(_strip_magics(cell)).body:
            if isinstance(node, ast.FunctionDef) and node.name == name:
                code = textwrap.dedent(ast.unparse(node))
                exec(code, namespace)  # noqa: S102 - 只執行 notebook 內的純函式
                return namespace[name]
    raise AssertionError(f"notebook 沒有函式 {name}")


@pytest.mark.parametrize("index", range(len(_cells())))
def test_code_cell_parses_as_python(index: int) -> None:
    ast.parse(_strip_magics(_cells()[index]))


def test_no_cell_uses_shell_or_magic_lines() -> None:
    for cell in _cells():
        assert not any(ln.lstrip().startswith(("!", "%")) for ln in cell.splitlines())


def test_pad_batch_pads_to_longest_and_masks_padding() -> None:
    pad_batch = _load_function("pad_batch", {"np": np})
    ids, mask = pad_batch([[1, 2, 3], [4], [5, 6]], [0, 1], 0)
    assert ids.tolist() == [[1, 2, 3], [4, 0, 0]]
    assert mask.tolist() == [[1, 1, 1], [1, 0, 0]]
    assert ids.dtype == np.int64


def test_pad_batch_uses_given_pad_id() -> None:
    pad_batch = _load_function("pad_batch", {"np": np})
    ids, _ = pad_batch([[7], [8, 9]], [0, 1], 99)
    assert ids.tolist() == [[7, 99], [8, 9]]


def test_estimate_total_seconds_scales_linearly() -> None:
    estimate = _load_function("estimate_total_seconds", {})
    assert estimate(10.0, 50, 1000) == 200.0


def test_check_time_budget_passes_at_limit() -> None:
    check = _load_function("check_time_budget", {})
    check(10 * 3600)


def test_check_time_budget_over_limit_raises_and_suggests_max_len_256() -> None:
    check = _load_function("check_time_budget", {})
    with pytest.raises(RuntimeError, match="MAX_LEN"):
        check(10 * 3600 + 1)


def test_first_cell_pins_torchvision_and_torchaudio_with_torch() -> None:
    first = _cells()[0]
    assert "torch==" in first
    assert "torchvision==" in first
    assert "torchaudio==" in first


def test_checkpoint_dirs_depend_on_base_and_max_len() -> None:
    source = "\n".join(_cells())
    assert 'RUN_NAME = f"{BASE}-len{MAX_LEN}"' in source
    for name in ("CKPT_DIR", "FINAL_DIR"):
        line = next(ln for ln in source.splitlines() if ln.startswith(f"{name} = "))
        assert "{RUN_NAME}" in line


def test_first_cell_uninstalls_diffusers_after_installing_packages() -> None:
    first = _cells()[0]
    assert '"uninstall", "-y", "-q", "diffusers"' in first
    assert first.index('"install"') < first.index('"uninstall"')
    assert first.index('"uninstall"') < first.index("import torch")


def test_notebook_has_no_outputs() -> None:
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == []
            assert cell["execution_count"] is None
