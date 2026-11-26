"""分级分类领域服务：维护数据资源安全等级与标签状态。

新增「资源升等」动作：在不改变标签状态机（待分级/已分级/…）的前提下，
把资源安全等级调整到更高等级（如 L1 -> L3）。升等结果会被索引发布服务
读取，用于在发布与检索时核验覆盖范围，防止受限资源漏给低等级访问者。
"""
from __future__ import annotations

from typing import Any

from app.services.base import BaseModuleService

# 安全等级数值映射：数值越大越敏感，未分级按最低等级处理以便正常发布。
LEVEL_ORDER = {"L1": 1, "L2": 2, "L3": 3, "L4": 4, "未分级": 0}


def level_value(level: Any) -> int:
    """把安全等级文本转成可比较的数值，无法识别时按最高限制处理。"""
    text = str(level or "").strip()
    if text in LEVEL_ORDER:
        return LEVEL_ORDER[text]
    # 形如 "L3" 之外的未知等级：保守视为最高敏感，避免越权漏出。
    if text.startswith("L") and text[1:].isdigit():
        return int(text[1:])
    return max(LEVEL_ORDER.values()) if text else 0


class ClassifyTagService(BaseModuleService):
    MODULE = "classify_tag"
    ENTITY = "分级标签"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["标签编号", "数据资源", "安全等级", "数据类型", "合规要求", "保留期限", "脱敏要求", "标签时间"]
    REQUIRED_FIELDS = ["标签编号", "数据资源", "安全等级"]
    STATUS_ORDER = ["待分级", "已分级", "需重审", "已降级"]
    # 资源升等是等级调整动作，不进入状态机，由 run_action 单独处理。
    ACTION_RULES = {"确认分级": "已分级", "标记重审": "需重审", "标记降级": "已降级"}
    NEGATIVE_ACTIONS = []

    def run_action(self, entry_id: int, action: str):
        if action == "资源升等":
            return self.upgrade_level(entry_id, target_level="L3")
        return super().run_action(entry_id, action)

    def upgrade_level(self, entry_id: int, target_level: str = "L3"):
        """把指定资源升等到 target_level（只允许调高，不允许借升等降级）。"""
        from app.store import store

        entry = store.find(self.MODULE, entry_id)
        if entry is None:
            return None, f"{self.ENTITY} {entry_id} 不存在或已归档"
        current = level_value(entry.get("安全等级"))
        target = level_value(target_level)
        if target <= current:
            return None, (
                f"资源「{entry.get('数据资源')}」当前等级 {entry.get('安全等级')} "
                f"不低于目标等级 {target_level}，升等被拒绝"
            )
        entry["安全等级"] = target_level
        # 升等后资源仍处于已分级状态，但需要重新核验发布范围。
        entry["status"] = "已分级"
        entry["pending"] = False
        entry["abnormal"] = True
        return entry, f"资源「{entry.get('数据资源')}」已由升等到 {target_level}"
