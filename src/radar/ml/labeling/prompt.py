"""標註 prompt 與輸出格式（S3-01）；改 prompt 內容就要升 PROMPT_VERSION。"""

import json
from dataclasses import dataclass

from radar.common.schemas import Sentiment, check_sentiments

PROMPT_VERSION = "prompt-v4"

# Gemini responseSchema（OpenAPI 子集），要求模型只輸出這個結構
RESPONSE_SCHEMA: dict[str, object] = {
    "type": "OBJECT",
    "properties": {
        "sentiments": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "target": {"type": "STRING", "nullable": True},
                    "polarity": {"type": "STRING", "enum": ["positive", "negative", "neutral"]},
                },
                "required": ["target", "polarity"],
            },
        }
    },
    "required": ["sentiments"],
}


# 同一結構的標準 JSON Schema，給 OpenAI 相容 API 的 response_format 使用
JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "sentiments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target": {"type": ["string", "null"]},
                    "polarity": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                },
                "required": ["target", "polarity"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sentiments"],
    "additionalProperties": False,
}


class LabelParseError(ValueError):
    """模型輸出不是合法的 JSON，或不符合 Label 的規則；不可重試，記錄後略過該篇。"""


@dataclass(frozen=True)
class PostText:
    post_id: str
    board: str
    title: str | None
    content: str | None


# NOTE: 與 docs/labeling-guideline.md 的規則逐字一致（單元測試檢查）；修改時升 PROMPT_VERSION
RULES: tuple[str, ...] = (
    "polarity 只能是 positive、negative、neutral。",
    "必須有、且只有一筆 target 為 null 的項目，代表作者對整篇文章主題的整體情緒。",
    "文中被作者明確評論的對象（公司、人物、政黨、政策、產品、股票等）各列一筆，"
    "target 用文中出現的名稱；只是被提及、被詢問或被比較而作者沒有評價的對象不要列。"
    "沒有明確評論的對象就只輸出整篇那一筆。最多列 5 個對象，同一對象只列一次。",
    "判斷的是作者的態度，不是事件本身的好壞：轉述壞消息但作者沒有表態 → neutral。",
    "PTT 常見反串與酸文：字面稱讚但語氣明顯諷刺（例如「真是太棒了呢」搭配負面事實）→ negative。",
    "純提問、求助、徵才或交易資訊、新聞轉貼且作者沒有評論 → neutral。",
    "標題為 [新聞] 的文章，只依作者的「心得/評論」段落判斷；沒有該段落或內容空白 → 整篇 neutral。",
    "心得若用帶評價的字眼（例如「慘敗」「被打爆」「笑死」）描述事件或對象，"
    "視為作者表態，整篇與該對象都依字眼的語氣判斷；只是中性地摘要新聞 → neutral。",
    "轉貼他人的貼文、聲明或發言（例如 [爆卦] 轉貼臉書文）時，被轉貼者的立場不是作者的立場；"
    "作者沒有另外評論 → 整篇 neutral，也不列對象。",
    "只依標題與內文判斷，不參考推文。",
)

_INSTRUCTIONS = "\n".join(
    [
        "你是 PTT 文章的情緒標註員。閱讀以下 PTT {board} 板的文章，判斷「作者」的情緒立場。",
        "",
        "規則：",
        *(f"{i}. {rule}" for i, rule in enumerate(RULES, start=1)),
    ]
)


def build_prompt(post: PostText, max_chars: int) -> str:
    content = (post.content or "").strip()
    truncated = len(content) > max_chars
    if truncated:
        content = content[:max_chars]
    parts = [
        _INSTRUCTIONS.format(board=post.board),
        f"標題：{(post.title or '').strip() or '（無標題）'}",
        f"內文：\n{content or '（無內文）'}",
    ]
    if truncated:
        parts.append("（內文過長，以上已截斷）")
    return "\n\n".join(parts)


def parse_sentiments(raw: str) -> list[Sentiment]:
    try:
        data = json.loads(raw)
        items = data["sentiments"]
        sentiments = [
            Sentiment(
                target=(item.get("target") or "").strip() or None,
                polarity=item["polarity"],
            )
            for item in items
        ]
        check_sentiments(sentiments)
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError, ValueError) as e:
        raise LabelParseError(f"invalid labeler output: {e!r}; raw={raw[:200]!r}") from e
    return sentiments
