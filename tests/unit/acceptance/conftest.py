"""驗收測試共用的 fixture（架構師維護，qa 不改）：階段 8 的測試用小 ONNX 模型（開發規格 7.27）。"""

from collections.abc import Callable
from pathlib import Path

import pytest

from tests.helpers.onnx_model import build_model_dir, build_model_package


@pytest.fixture
def tiny_model_dir(tmp_path: Path) -> Path:
    """import 後的 fp32 模型資料夾（models/<model_version>/ 的樣子）。"""
    return build_model_dir(tmp_path / "models" / "bert-test-202610210000")


@pytest.fixture
def tiny_int8_model_dir(tmp_path: Path) -> Path:
    return build_model_dir(tmp_path / "models" / "bert-test-202610210000-int8", quantized=True)


@pytest.fixture
def make_model_package(tmp_path: Path) -> Callable[..., Path]:
    """產生模型包 zip；參數同 tests.helpers.onnx_model.package_members。"""

    def make(**kwargs: object) -> Path:
        return build_model_package(tmp_path / "packages", **kwargs)

    return make
