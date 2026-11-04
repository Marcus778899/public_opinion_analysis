"""指令列工具共用：一行錯誤說明加非 0 結束碼，不印 traceback。"""

import sys
from collections.abc import Callable
from typing import NoReturn

from pydantic import ValidationError
from pydantic_settings import BaseSettings

ENV_FILE_HINT = "uv run --env-file .env python -m ..."


def fail(message: str) -> NoReturn:
    # NOTE: SystemExit 不是 Exception，不會被 @log.catch 吞掉，結束碼才會非 0
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def missing_env_names(exc: ValidationError, prefix: str) -> list[str]:
    return [f"{prefix}{str(e['loc'][0]).upper()}" for e in exc.errors() if e["type"] == "missing"]


def load_settings[T: BaseSettings](factory: Callable[[], T]) -> T:
    """建立設定；缺必填環境變數時列出變數名稱與 .env 載入提示後結束。"""
    try:
        return factory()
    except ValidationError as exc:
        prefix = str(getattr(factory, "model_config", {}).get("env_prefix", ""))
        missing = missing_env_names(exc, prefix)
        if not missing:
            raise
        fail(f"缺少環境變數 {', '.join(missing)}；請用 `{ENV_FILE_HINT}` 執行以載入 .env")
