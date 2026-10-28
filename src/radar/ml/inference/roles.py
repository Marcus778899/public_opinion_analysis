"""推論角色 → consumer group、輸出 topic、ClickHouse 表的固定對照（開發規格 7.27）。

INFERENCE_ROLE 只接受列舉值，名稱不由設定字串組出；shadow 的 group 依模型版本分開。
"""

from dataclasses import dataclass

from radar.common.kafka import names
from radar.common.settings import InferenceRole

PRIMARY_GROUP = "inference"
SHADOW_GROUP_PREFIX = "inference-shadow-"


@dataclass(frozen=True)
class RoleTargets:
    topic: str
    # 推論結果的表；啟動時從這裡載入 hash 快取（7.19），compare 也讀它
    table: str


ROLE_TARGETS: dict[InferenceRole, RoleTargets] = {
    InferenceRole.PRIMARY: RoleTargets(topic=names.PREDICTIONS, table="predictions"),
    InferenceRole.SHADOW: RoleTargets(topic=names.PREDICTIONS_SHADOW, table="predictions_shadow"),
}


def consumer_group(role: InferenceRole, model_version: str) -> str:
    """shadow 每個模型版本一個 group，從頭消費 cdc.public.posts（保留期間內的文章都會推論）。"""
    if role is InferenceRole.PRIMARY:
        return PRIMARY_GROUP
    return f"{SHADOW_GROUP_PREFIX}{model_version}"
