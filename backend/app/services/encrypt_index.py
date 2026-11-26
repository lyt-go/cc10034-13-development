"""密文索引领域服务：维护可搜索加密索引的字段、状态与动作。

在通用 CRUD/动作骨架之上补充与「索引发布」联动的能力：
- LIST_FIELDS 增加「关联资源」，用于和分级分类模块按数据资源对齐安全等级；
- 增加「完成重建」动作，使重建中的条目可恢复为「有效」，
  避免失败的重建把此前仍可检索的低等级条目直接吞掉。
"""
from __future__ import annotations

from app.services.base import BaseModuleService


class EncryptIndexService(BaseModuleService):
    MODULE = "encrypt_index"
    ENTITY = "索引条目"
    OPERATION_TERM = "存储"
    LIST_FIELDS = [
        "条目编号", "加密域", "索引类型", "陷门哈希", "可搜索标记",
        "存储位置", "创建时间", "索引版本", "关联资源",
    ]
    REQUIRED_FIELDS = ["条目编号", "加密域", "索引类型"]
    STATUS_ORDER = ["有效", "重建中", "已失效"]
    # 「完成重建」把重建中的条目恢复为有效，重建失败/完成后仍可被发布与检索。
    ACTION_RULES = {"发起重建": "重建中", "完成重建": "有效", "标记失效": "已失效"}
    NEGATIVE_ACTIONS = []

    def run_action(self, entry_id: int, action: str):
        entry, message = super().run_action(entry_id, action)
        if entry is None:
            return entry, message
        # 状态恢复为「有效」时同步恢复可搜索标记，保证低等级条目仍可被检索。
        if action == "完成重建" and entry.get("status") == "有效":
            entry["可搜索标记"] = "可搜索"
            entry["abnormal"] = False
        elif action == "发起重建":
            entry["可搜索标记"] = "重建中-不可搜索"
        elif action == "标记失效":
            entry["可搜索标记"] = "不可搜索"
        return entry, message
