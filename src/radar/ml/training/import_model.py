"""[一次性] 匯入 notebook 產生的模型包（開發規格 7.27 步驟 3、威脅與對策）。

用法：python -m radar.ml.training.import_model --zip <model_version>.zip
只解出白名單的三個檔，比對 model_card.files 的 SHA-256 後才寫入 models/<model_version>/。
"""

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from radar.common.log import log, setup_logging
from radar.ml.training.classifier import ONNX_MODEL_FILE, TOKENIZER_FILE
from radar.ml.training.train import CARD_FILE, MODELS_DIR, ModelCard, ModelKind

ALLOWED_FILES = frozenset({ONNX_MODEL_FILE, TOKENIZER_FILE, CARD_FILE})
# 解壓後的總大小上限（zip bomb）；以 zip 內實際讀出的位元組計，不信任標頭宣稱的大小
MAX_TOTAL_BYTES = 2 * 1024**3
MODEL_VERSION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class ModelPackageError(ValueError):
    """模型包不合格（雜湊不符、多餘或缺少檔名、路徑穿越、超過大小、版本名稱不合法）。"""


class ModelExistsError(FileExistsError):
    """models/<model_version>/ 已存在；不覆寫。"""


def package_sha256(zip_path: Path) -> str:
    digest = hashlib.sha256()
    with zip_path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_members(zip_path: Path) -> dict[str, bytes]:
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise ModelPackageError("not a valid zip file") from exc
    with zf:
        names = [info.filename for info in zf.infolist()]
        # 檔名必須逐字等於白名單：路徑、多餘、重複、缺少都拒絕
        if len(names) != len(set(names)) or set(names) != ALLOWED_FILES:
            raise ModelPackageError(f"zip members must be exactly {sorted(ALLOWED_FILES)}")
        for info in zf.infolist():
            if info.flag_bits & 0x1:
                raise ModelPackageError(f"encrypted member not supported: {info.filename}")
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ModelPackageError(f"unsupported compression for {info.filename}")
        members: dict[str, bytes] = {}
        total = 0
        for name in sorted(ALLOWED_FILES):
            with zf.open(name) as fh:
                data = fh.read(MAX_TOTAL_BYTES - total + 1)
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise ModelPackageError("uncompressed size exceeds limit")
            members[name] = data
    return members


def _parse_card(raw: bytes) -> ModelCard:
    try:
        version = json.loads(raw).get("model_version")
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as exc:
        raise ModelPackageError("model_card.json is not a JSON object") from exc
    if not isinstance(version, str) or not MODEL_VERSION_RE.fullmatch(version):
        raise ModelPackageError("invalid model_version")
    try:
        card = ModelCard.model_validate_json(raw)
    except ValueError as exc:
        raise ModelPackageError("invalid model_card.json") from exc
    if card.kind is not ModelKind.ONNX:
        raise ModelPackageError("model_card kind must be onnx")
    return card


def import_model(zip_path: Path, models_dir: Path, *, sha256: str | None = None) -> Path:
    """驗證通過才寫入 models_dir/<model_version>/ 並回傳該路徑；失敗時不留下半成品。

    sha256 給了就先比對整包 zip（大小寫不分），不符丟 ModelPackageError。
    """
    if sha256 is not None and package_sha256(zip_path) != sha256.strip().lower():
        raise ModelPackageError(f"package sha256 mismatch, actual {package_sha256(zip_path)}")
    members = _read_members(zip_path)
    card = _parse_card(members[CARD_FILE])
    for name in (ONNX_MODEL_FILE, TOKENIZER_FILE):
        expected = card.files.get(name)
        if expected is None or hashlib.sha256(members[name]).hexdigest() != expected.lower():
            raise ModelPackageError(f"sha256 mismatch for {name}")
    target = models_dir / card.model_version
    if target.exists():
        raise ModelExistsError(str(target))
    models_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".import-", dir=models_dir))
    try:
        for name, data in members.items():
            (staging / name).write_bytes(data)
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("import_model")
    parser = argparse.ArgumentParser(description="匯入 BERT 模型包（S8-01）")
    parser.add_argument("--zip", type=Path, required=True, help="notebook 產生的模型包 zip 路徑")
    parser.add_argument(
        "--sha256",
        help="預期的整包 zip SHA-256（hex，大小寫不分）；給了就比對，不符拒絕匯入",
    )
    args = parser.parse_args()
    try:
        digest = package_sha256(args.zip)
        log.info("package sha256 %s", digest)
        target = import_model(args.zip, MODELS_DIR, sha256=args.sha256)
    except ModelExistsError as exc:
        sys.exit(f"error: model version already exists: {exc}")
    except (ModelPackageError, OSError) as exc:
        sys.exit(f"error: {args.zip}: {exc}")
    log.info("imported %s; next: python -m radar.ml.training.evaluate --model %s", target, target)


if __name__ == "__main__":
    main()
