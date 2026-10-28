"""衍生只改 max_len 的模型包（開發規格 7.27 順序 4），不重訓。

用法：python -m radar.ml.training.derive_model --model models/<v> --max-len 256
產生 models/<v>-len256/；model.onnx、tokenizer.json 原樣複製，只改 card。
"""

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from radar.common.log import log, setup_logging
from radar.ml.training.classifier import ONNX_MODEL_FILE, TOKENIZER_FILE
from radar.ml.training.import_model import MODEL_VERSION_RE
from radar.ml.training.train import CARD_FILE, ModelCard


class DeriveError(ValueError):
    """無法衍生（來源不合格、max_len 不小於原值、新版本名稱不合法、目標已存在）。"""


def derive_model(model_dir: Path, max_len: int) -> Path:
    """在 model_dir 同層建立 <model_version>-len<max_len>，回傳新路徑；失敗不留半成品。"""
    card_path = model_dir / CARD_FILE
    if not card_path.is_file():
        raise DeriveError(f"{card_path} not found")
    raw = card_path.read_text(encoding="utf-8")
    try:
        card = ModelCard.model_validate_json(raw)
    except ValueError as exc:
        raise DeriveError("invalid model_card.json") from exc
    if card.max_len is None:
        raise DeriveError("source card has no max_len")
    if max_len < 1 or max_len >= card.max_len:
        raise DeriveError(f"max_len must be smaller than {card.max_len}, got {max_len}")
    new_version = f"{card.model_version}-len{max_len}"
    if not MODEL_VERSION_RE.fullmatch(new_version):
        raise DeriveError(f"invalid model_version: {new_version}")
    target = model_dir.parent / new_version
    if target.exists():
        raise DeriveError(f"{target} already exists")
    for name in (ONNX_MODEL_FILE, TOKENIZER_FILE):
        if not (model_dir / name).is_file():
            raise DeriveError(f"{model_dir / name} not found")

    data = json.loads(raw)
    data["model_version"] = new_version
    data["max_len"] = max_len
    data["params"] = {**data.get("params", {}), "derived_from": card.model_version}
    staging = Path(tempfile.mkdtemp(prefix=".derive-", dir=model_dir.parent))
    try:
        for name in (ONNX_MODEL_FILE, TOKENIZER_FILE):
            shutil.copyfile(model_dir / name, staging / name)
        (staging / CARD_FILE).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("derive_model")
    parser = argparse.ArgumentParser(description="衍生只改 max_len 的模型版本")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--max-len", type=int, required=True)
    args = parser.parse_args()
    try:
        target = derive_model(args.model, args.max_len)
    except DeriveError as exc:
        sys.exit(f"error: {exc}")
    log.info("derived %s; next: python -m radar.ml.training.evaluate --model %s", target, target)


if __name__ == "__main__":
    main()
