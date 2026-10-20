"""驗證 worker 回報是否符合 contracts/report.schema.json，給 hook 呼叫。

兩種用法：
    validate_report.py reports/<task_id>.json   # 手動驗證
    （無參數）                                  # SubagentStop hook：從 stdin 讀 hook JSON

hook 模式檢查 worker（WORKER_TYPES）與會寫回報的設計角色（DESIGN_TYPES）；qa 等角色直接放行。
回報路徑取自最後一則訊息裡的 `reports/<task_id>.json`。worker 一定要附；architect、designer 只在
做派工單時才寫回報（review、仲裁不寫），所以訊息裡有回報路徑才驗，免得 pr.py open 才發現格式錯、重新喚起 agent。
同一個 worker 被退回 MAX_BLOCKS 次後放行，避免無限循環燒額度；壞回報留給 manager／qa 處理。

exit 0 = 通過；exit 2 = 不通過（stderr 的訊息會回饋給 agent，逼它重做）。
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "contracts" / "report.schema.json"
WORKER_TYPES = {"backend", "frontend"}
DESIGN_TYPES = {"architect", "designer"}
REPORT_PATH_RE = re.compile(r"reports/[\w.-]+\.json")
MAX_BLOCKS = 3
BLOCKS_PATH = ROOT / "reports" / ".hook-blocks.json"
JSON_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "boolean": bool,
}


class ReportError(Exception):
    pass


def load_report(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ReportError(f"找不到回報檔 {path}；請依 contracts/report.schema.json 寫入")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ReportError(f"{path} 不是合法 JSON：{e}") from e
    if not isinstance(report, dict):
        raise ReportError(f"{path} 頂層必須是 object")
    return report


def _validate(value: object, schema: dict, where: str) -> list[str]:
    """只實作 schema 用到的子集：type、enum、required、properties、additionalProperties、items。"""
    errors: list[str] = []
    expected = schema.get("type")
    if expected:
        py_type = JSON_TYPES[expected]
        # bool 是 int 的子類別，integer 不可接受 true/false
        if not isinstance(value, py_type) or (expected == "integer" and isinstance(value, bool)):
            return [f"{where}：應為 {expected}，實際是 {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}：必須是 {schema['enum']} 之一，實際是 {value!r}")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{where}：缺少必填欄位 {key}")
        if schema.get("additionalProperties") is False:
            for key in value.keys() - props.keys():
                errors.append(f"{where}：不允許的欄位 {key}")
        for key, sub in props.items():
            if key in value:
                errors += _validate(value[key], sub, f"{where}.{key}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            errors += _validate(item, schema["items"], f"{where}[{i}]")
    return errors


def check_schema(report: dict[str, object]) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return _validate(report, schema, "report")


def check_consistency(report: dict[str, object], path: Path) -> list[str]:
    errors: list[str] = []
    status = report.get("status")
    verification = report.get("verification") or {}
    if report.get("task_id") != path.stem:
        errors.append(f"task_id {report.get('task_id')!r} 與檔名 {path.name} 不一致")
    if status == "done":
        if verification.get("exit_code") != 0:
            errors.append(f"status=done 但驗證指令 exit_code={verification.get('exit_code')}：不可謊報完成")
        if not report.get("files_changed"):
            errors.append("status=done 但 files_changed 是空的")
        if not str(verification.get("tail", "")).strip():
            errors.append("status=done 但沒有附驗證輸出（verification.tail）")
    if report.get("disputes") and status != "blocked":
        errors.append(f"有 disputes（測試與契約矛盾）時 status 必須是 blocked，實際是 {status}")
    if status in ("blocked", "failed") and not (report.get("open_questions") or report.get("disputes")):
        errors.append(f"status={status} 必須在 open_questions 說明卡在哪裡（測試與契約矛盾就填 disputes）")
    return errors


def _last_assistant_text(transcript: Path) -> str:
    text = ""
    for line in transcript.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        content = entry.get("message", {}).get("content", [])
        parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        if parts:
            text = "\n".join(parts)
    return text


def _report_path_from_hook(payload: dict) -> Path | None:
    """回傳要驗證的回報路徑；None 表示這個 subagent 不需要驗證。"""
    agent_type = payload.get("agent_type")
    if agent_type is not None and agent_type not in WORKER_TYPES | DESIGN_TYPES:
        return None

    message = payload.get("last_assistant_message") or ""
    if not message:
        transcript = payload.get("agent_transcript_path") or payload.get("transcript_path")
        if transcript and Path(transcript).is_file():
            message = _last_assistant_text(Path(transcript))

    match = REPORT_PATH_RE.search(message)
    if match is None:
        if agent_type is None or agent_type in DESIGN_TYPES:
            # 設計角色這次不是做派工單；拿不到角色資訊時無法分辨是不是 worker：沒提到回報檔就放行
            return None
        raise ReportError("最後一則訊息必須包含回報檔路徑 reports/<task_id>.json")
    # reports/ 永遠在主目錄；hook 的 cwd 可能是 worker 的 worktree
    return ROOT / match.group(0)


def _count_block(agent_id: str) -> int:
    """記錄並回傳這個 worker 被退回的次數。"""
    try:
        blocks = json.loads(BLOCKS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        blocks = {}
    blocks[agent_id] = blocks.get(agent_id, 0) + 1
    BLOCKS_PATH.parent.mkdir(exist_ok=True)
    BLOCKS_PATH.write_text(json.dumps(blocks, indent=2) + "\n", encoding="utf-8")
    return blocks[agent_id]


def main() -> None:
    payload: dict | None = None
    try:
        if len(sys.argv) > 1:
            path = Path(sys.argv[1])
        else:
            payload = json.load(sys.stdin)
            path = _report_path_from_hook(payload)
            if path is None:
                sys.exit(0)
        report = load_report(path)
        errors = check_schema(report)
        if not errors:
            errors = check_consistency(report, path)
    except ReportError as e:
        errors = [str(e)]

    if not errors:
        return
    if payload is not None:
        agent_id = str(payload.get("agent_id") or payload.get("session_id") or "unknown")
        if _count_block(agent_id) > MAX_BLOCKS:
            # 放行，交給 manager／qa；stdout 只會出現在 transcript
            print(f"回報仍不合格，已退回 {MAX_BLOCKS} 次，放行交由 manager 處理：{errors}")
            sys.exit(0)
    print("回報驗證失敗，修正後重新回報：", file=sys.stderr)
    for e in errors:
        print(f"- {e}", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
    sys.exit(0)
