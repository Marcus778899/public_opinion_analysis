"""[一次性] 匯入 notebook 產生的模型包（開發規格 7.27 步驟 3、威脅與對策）。

用法：python -m radar.ml.training.import_model --zip <model_version>.zip
只解出白名單的三個檔，比對 model_card.files 的 SHA-256 後才寫入 models/<model_version>/。
"""

import argparse
import re
from pathlib import Path

from radar.common.log import log, setup_logging
from radar.ml.training.classifier import ONNX_MODEL_FILE, TOKENIZER_FILE
from radar.ml.training.train import CARD_FILE, MODELS_DIR

ALLOWED_FILES = frozenset({ONNX_MODEL_FILE, TOKENIZER_FILE, CARD_FILE})
# 解壓後的總大小上限（zip bomb）；以 zip 內實際讀出的位元組計，不信任標頭宣稱的大小
MAX_TOTAL_BYTES = 2 * 1024**3
MODEL_VERSION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class ModelPackageError(ValueError):
    """模型包不合格（雜湊不符、多餘或缺少檔名、路徑穿越、超過大小、版本名稱不合法）。"""


class ModelExistsError(FileExistsError):
    """models/<model_version>/ 已存在；不覆寫。"""


def import_model(zip_path: Path, models_dir: Path) -> Path:
    """驗證通過才寫入 models_dir/<model_version>/ 並回傳該路徑；失敗時不留下半成品。"""
    # TODO(bert-model-import)
    raise NotImplementedError  # pragma: no cover（骨架）


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("import_model")
    parser = argparse.ArgumentParser(description="匯入 BERT 模型包（S8-01）")
    parser.add_argument("--zip", type=Path, required=True)
    args = parser.parse_args()
    target = import_model(args.zip, MODELS_DIR)
    log.info("imported %s; next: python -m radar.ml.training.evaluate --model %s", target, target)


if __name__ == "__main__":
    main()
