"""索引发布领域服务：密文索引重建后的上线前范围核验。

设计目标（对应业务约束）：

1. 操作员在「索引发布」页提交待发布索引条目与本次发布的资源分级上限，
   后端逐条核验条目当前状态及其关联资源在分级分类模块中的实际安全等级，
   计算实际覆盖范围并生成「索引发布回执」。
2. 索引发布与资源升等发生冲突时（某关联资源实际等级高于本次发布声明的
   分级上限），本次发布判定为失败（回执 status=发布失败），**不替换**
   此前仍生效的回执——失败的重建/发布不得吞掉此前仍可检索的低等级条目。
3. 检索入口按「当前生效回执 + 访问者等级」返回可用条目：一次检索的结果
   必然对应一个可识别的生效范围（receipt_id），普通分析员（L1）不会漏出
   已被升等受限的资源条目。

全部状态保存在内存仓库的两张运行期表：
- index_release_receipt：发布回执（含提交快照、实际生效范围、冲突明细）；
- 不新增索引条目表，复用 encrypt_index，资源等级复用 classify_tag。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.classify_tag import level_value
from app.store import store

RECEIPT_TABLE = "index_release_receipt"

# 回执状态：生效中（当前可检索范围）/ 发布失败（留痕，不替换旧回执）/ 已被替代。
RECEIPT_ACTIVE = "生效中"
RECEIPT_FAILED = "发布失败"
RECEIPT_SUPERSEDED = "已被替代"


class IndexReleaseService:
    """索引发布、回执核验与按等级检索的领域服务。"""

    MODULE = "index_release"
    ENTITY = "索引发布回执"

    def __init__(self) -> None:
        store.ensure_table(RECEIPT_TABLE)

    # ------------------------------------------------------------------
    # 基础读取
    # ------------------------------------------------------------------
    def _receipts(self) -> list[dict[str, Any]]:
        return store.rows(RECEIPT_TABLE)

    def _next_id(self) -> int:
        return max((int(r.get("id", 0)) for r in self._receipts()), default=0) + 1

    def list_receipts(self) -> list[dict[str, Any]]:
        """按时间倒序返回全部回执，便于发布页展示发布历史。"""
        return sorted(self._receipts(), key=lambda r: int(r["id"]), reverse=True)

    def get_receipt(self, receipt_id: int) -> dict[str, Any] | None:
        return store.find(RECEIPT_TABLE, receipt_id)

    def current_receipt(self) -> dict[str, Any] | None:
        """当前生效回执：状态为「生效中」的最新一条；不存在则 None。"""
        active = [r for r in self._receipts() if r.get("status") == RECEIPT_ACTIVE]
        return max(active, key=lambda r: int(r["id"]), default=None)

    # ------------------------------------------------------------------
    # 资源 / 索引辅助
    # ------------------------------------------------------------------
    def resource_levels(self) -> list[dict[str, Any]]:
        """汇总分级分类模块中各数据资源的当前安全等级，供发布页展示与升等。"""
        result: list[dict[str, Any]] = []
        for tag in store.rows("classify_tag"):
            result.append({
                "tag_id": tag.get("id"),
                "数据资源": tag.get("数据资源"),
                "安全等级": tag.get("安全等级"),
                "level_value": level_value(tag.get("安全等级")),
                "status": tag.get("status"),
                "abnormal": bool(tag.get("abnormal")),
            })
        return result

    def level_of_resource(self, resource: str) -> dict[str, Any] | None:
        """按数据资源名取当前分级标签（取同资源中等级最高的一条为准）。"""
        matches = [
            tag for tag in store.rows("classify_tag")
            if str(tag.get("数据资源", "")).casefold() == str(resource or "").casefold()
        ]
        if not matches:
            return None
        return max(matches, key=lambda tag: level_value(tag.get("安全等级")))

    def publishable_indexes(self) -> list[dict[str, Any]]:
        """可发布候选：仅「有效」且可搜索的索引条目，附带关联资源当前等级。"""
        candidates: list[dict[str, Any]] = []
        for entry in store.rows("encrypt_index"):
            tag = self.level_of_resource(entry.get("关联资源", ""))
            candidates.append({
                "index_id": entry.get("id"),
                "条目编号": entry.get("条目编号"),
                "加密域": entry.get("加密域"),
                "索引类型": entry.get("索引类型"),
                "关联资源": entry.get("关联资源"),
                "index_status": entry.get("status"),
                "可搜索标记": entry.get("可搜索标记"),
                "resource_level": tag.get("安全等级") if tag else "未登记分级",
                "level_value": level_value(tag.get("安全等级")) if tag else 0,
                "publishable": entry.get("status") == "有效" and entry.get("可搜索标记") == "可搜索",
            })
        return candidates

    # ------------------------------------------------------------------
    # 核心：发布核验并生成回执
    # ------------------------------------------------------------------
    def publish(
        self,
        index_ids: list[int],
        resource_level: str,
        operator: str | None = None,
        remark: str | None = None,
    ) -> dict[str, Any]:
        """提交发布，计算覆盖范围并生成回执；冲突时回执失败且不动旧回执。"""
        declared = str(resource_level or "").strip()
        declared_value = level_value(declared)
        receipt_id = self._next_id()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        selected: list[dict[str, Any]] = []
        invalid_indexes: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        unregistered: list[dict[str, Any]] = []

        for index_id in index_ids:
            entry = store.find("encrypt_index", int(index_id))
            if entry is None:
                invalid_indexes.append({"index_id": index_id, "reason": "索引条目不存在"})
                continue
            tag = self.level_of_resource(entry.get("关联资源", ""))
            current_level = tag.get("安全等级") if tag else "未登记分级"
            snapshot = {
                "index_id": entry.get("id"),
                "条目编号": entry.get("条目编号"),
                "加密域": entry.get("加密域"),
                "关联资源": entry.get("关联资源"),
                "index_status": entry.get("status"),
                "resource_level": current_level,
            }
            selected.append(snapshot)

            # 规则 1：重建中/已失效的索引不具备上线条件。
            if entry.get("status") != "有效" or entry.get("可搜索标记") != "可搜索":
                invalid_indexes.append({
                    "index_id": entry.get("id"),
                    "条目编号": entry.get("条目编号"),
                    "reason": f"索引当前状态为「{entry.get('status')}」，不满足发布条件",
                })
                continue

            # 规则 2：关联资源未登记分级，无法核验范围。
            if tag is None:
                unregistered.append({
                    "index_id": entry.get("id"),
                    "条目编号": entry.get("条目编号"),
                    "关联资源": entry.get("关联资源"),
                    "reason": "关联资源未在分级分类模块登记，无法核验覆盖范围",
                })
                continue

            # 规则 3：资源实际等级高于本次发布声明的分级上限 => 升等冲突。
            if level_value(tag.get("安全等级")) > declared_value:
                conflicts.append({
                    "index_id": entry.get("id"),
                    "条目编号": entry.get("条目编号"),
                    "关联资源": entry.get("关联资源"),
                    "declared_level": declared,
                    "actual_level": tag.get("安全等级"),
                    "reason": (
                        f"资源「{tag.get('数据资源')}」实际等级 {tag.get('安全等级')} "
                        f"高于本次发布声明的 {declared}，存在受限资源漏出风险"
                    ),
                })

        success = not (conflicts or invalid_indexes or unregistered) and bool(selected)
        # 实际生效范围：仅在发布成功时等于提交范围；失败时本次发布不生效。
        effective_scope = [dict(item) for item in selected] if success else []
        # 覆盖等级取本次发布声明等级与纳入条目实际等级的最低公共上限。
        if success:
            scope_level = max(
                (level_value(item["resource_level"]) for item in effective_scope),
                default=declared_value,
            )
        else:
            scope_level = None

        previous = self.current_receipt()
        receipt: dict[str, Any] = {
            "id": receipt_id,
            "回执编号": f"RLSE-{receipt_id:04d}",
            "status": RECEIPT_ACTIVE if success else RECEIPT_FAILED,
            "operator": operator or "值班操作员",
            "remark": remark or "",
            "created_at": now,
            "declared_level": declared,
            "submitted_index_ids": [int(i) for i in index_ids],
            "submitted_snapshot": selected,
            "conflicts": conflicts,
            "invalid_indexes": invalid_indexes,
            "unregistered_resources": unregistered,
            "effective_index_ids": [item["index_id"] for item in effective_scope],
            "effective_scope": effective_scope,
            "effective_level": self._level_text(scope_level),
            "superseded_receipt_id": previous.get("id") if (success and previous) else None,
            "retained_receipt_id": previous.get("id") if (not success and previous) else None,
        }

        if success:
            # 仅在发布成功时把旧生效回执标记为已替代，失败时旧回执原样保留。
            if previous is not None:
                previous["status"] = RECEIPT_SUPERSEDED
            self._receipts().append(receipt)
        else:
            # 失败回执只留痕，绝不触碰旧回执，保证低等级条目仍可检索。
            self._receipts().append(receipt)

        return receipt

    @staticmethod
    def _level_text(value: int | None) -> str:
        if value is None:
            return "未生效"
        for text, num in {"L1": 1, "L2": 2, "L3": 3, "L4": 4}.items():
            if num == value:
                return text
        return f"L{value}"

    # ------------------------------------------------------------------
    # 核心：按访问者等级在生效回执范围内检索
    # ------------------------------------------------------------------
    def search(self, access_level: str, keyword: str | None = None) -> dict[str, Any]:
        """按访问者等级检索当前生效回执内的可用条目。

        - 没有任何生效回执时返回空结果并显式说明，绝不返回未发布条目；
        - 结果只来自当前生效回执的 effective_index_ids；
        - 再按关联资源的「当前实际等级」过滤，已升等受限的资源对低等级不可见；
        - 每条结果都带 receipt_id，一次检索对应一个可识别的生效范围。
        """
        visitor_value = level_value(access_level)
        receipt = self.current_receipt()
        if receipt is None:
            return {
                "receipt_id": None,
                "receipt_no": None,
                "access_level": access_level,
                "effective_level": None,
                "items": [],
                "total": 0,
                "message": "当前没有生效中的索引发布回执，暂无可检索条目",
            }

        items: list[dict[str, Any]] = []
        hidden_by_level: list[dict[str, Any]] = []
        hidden_unavailable: list[dict[str, Any]] = []
        for index_id in receipt.get("effective_index_ids", []):
            entry = store.find("encrypt_index", int(index_id))
            if entry is None:
                continue
            tag = self.level_of_resource(entry.get("关联资源", ""))
            actual_level = tag.get("安全等级") if tag else "未登记分级"
            actual_value = level_value(tag.get("安全等级")) if tag else 0
            # 重建中/已失效的条目即使仍被旧回执引用，也不得作为可检索结果返回；
            # 但同回执内其它仍可搜索的低等级条目必须保留，不能被一次失败重建吞掉。
            if entry.get("status") != "有效" or entry.get("可搜索标记") != "可搜索":
                hidden_unavailable.append({
                    "index_id": entry.get("id"),
                    "条目编号": entry.get("条目编号"),
                    "关联资源": entry.get("关联资源"),
                    "index_status": entry.get("status"),
                    "可搜索标记": entry.get("可搜索标记"),
                })
                continue
            # 访问者等级必须不低于资源当前实际等级，否则该受限条目不可见。
            if visitor_value < actual_value:
                hidden_by_level.append({
                    "index_id": entry.get("id"),
                    "条目编号": entry.get("条目编号"),
                    "关联资源": entry.get("关联资源"),
                    "actual_level": actual_level,
                })
                continue
            item = {
                "index_id": entry.get("id"),
                "条目编号": entry.get("条目编号"),
                "加密域": entry.get("加密域"),
                "索引类型": entry.get("索引类型"),
                "关联资源": entry.get("关联资源"),
                "resource_level": actual_level,
                "可搜索标记": entry.get("可搜索标记"),
                "receipt_id": receipt.get("id"),
                "回执编号": receipt.get("回执编号"),
            }
            if keyword:
                haystack = " ".join(str(item.get(k, "")) for k in ("条目编号", "加密域", "关联资源", "索引类型"))
                if keyword.casefold() not in haystack.casefold():
                    continue
            items.append(item)

        return {
            "receipt_id": receipt.get("id"),
            "receipt_no": receipt.get("回执编号"),
            "access_level": access_level,
            "effective_level": receipt.get("effective_level"),
            "items": items,
            "total": len(items),
            "hidden_by_level": hidden_by_level,
            "hidden_unavailable": hidden_unavailable,
            "message": "ok",
        }

    # ------------------------------------------------------------------
    # 发布详情：实际生效范围 + 失败后保留条目
    # ------------------------------------------------------------------
    def receipt_detail(self, receipt_id: int) -> dict[str, Any] | None:
        """回执详情，补充当前生效范围与失败后仍保留的可检索条目。"""
        receipt = self.get_receipt(receipt_id)
        if receipt is None:
            return None
        current = self.current_receipt()
        retained: list[dict[str, Any]] = []
        if receipt.get("status") == RECEIPT_FAILED and current is not None:
            # 失败后仍保留的条目 = 当前生效回执范围内、L1 普通分析员仍可见的条目。
            retained = self.search("L1").get("items", [])
        detail = dict(receipt)
        detail["current_receipt_id"] = current.get("id") if current else None
        detail["retained_entries"] = retained
        return detail


index_release_service = IndexReleaseService()
