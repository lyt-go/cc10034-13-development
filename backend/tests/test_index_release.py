"""索引发布服务测试：范围核验、升等冲突、两级检索与失败重建保留。

覆盖业务约束：
- 发布提交后由后端计算覆盖范围并生成回执；
- 索引发布与资源升等冲突时失败发布不替换旧回执，普通分析员不漏出受限资源；
- 一次检索对应一个可识别生效范围（receipt_id）；
- 失败的重建不得吞掉同范围内仍可检索的低等级条目。

运行：cd backend && python3 -m pytest tests/test_index_release.py -v
"""
from __future__ import annotations

import pytest

from app.services.classify_tag import ClassifyTagService
from app.services.encrypt_index import EncryptIndexService
from app.services.index_release import RECEIPT_TABLE, IndexReleaseService
from app.store import store

# 种子数据中两项 L1 资源对应的分级标签与密文索引 ID。
L1_TAG_ORDER = 4          # 电商订单明细库
L1_TAG_MEMBER = 5         # 会员营销标签库
INDEX_ORDER = 4           # ENCR-0004 -> 电商订单明细库
INDEX_MEMBER = 5          # ENCR-0005 -> 会员营销标签库


@pytest.fixture
def service():
    """每个用例使用全新的发布服务，并清空运行期回执表，避免相互串数据。"""
    store.ensure_table(RECEIPT_TABLE).clear()
    return IndexReleaseService()


@pytest.fixture(autouse=True)
def restore_seed_rows():
    """仓库为全局单例，用例前后恢复相关种子行，避免升等/重建状态跨用例串扰。"""
    snapshot = {
        "encrypt_index": [dict(r) for r in store.rows("encrypt_index")],
        "classify_tag": [dict(r) for r in store.rows("classify_tag")],
    }
    store.ensure_table(RECEIPT_TABLE).clear()
    yield
    store.rows("encrypt_index")[:] = [dict(r) for r in snapshot["encrypt_index"]]
    store.rows("classify_tag")[:] = [dict(r) for r in snapshot["classify_tag"]]
    store.ensure_table(RECEIPT_TABLE).clear()


@pytest.fixture
def classify():
    return ClassifyTagService()


@pytest.fixture
def index_service():
    return EncryptIndexService()


class TestResourcePreparation:
    def test_two_l1_resources_exist(self, service):
        levels = {r["数据资源"]: r["安全等级"] for r in service.resource_levels()}
        assert levels["电商订单明细库"] == "L1"
        assert levels["会员营销标签库"] == "L1"

    def test_publishable_candidates_carry_resource_level(self, service):
        candidates = {c["index_id"]: c for c in service.publishable_indexes()}
        for index_id in (INDEX_ORDER, INDEX_MEMBER):
            assert candidates[index_id]["publishable"] is True
            assert candidates[index_id]["resource_level"] == "L1"


class TestPublishScope:
    def test_publish_l1_success_creates_active_receipt(self, service):
        receipt = service.publish([INDEX_ORDER, INDEX_MEMBER], "L1", operator="操作员甲")
        assert receipt["status"] == "生效中"
        assert receipt["effective_index_ids"] == [INDEX_ORDER, INDEX_MEMBER]
        assert receipt["effective_level"] == "L1"
        assert receipt["conflicts"] == []
        assert service.current_receipt()["id"] == receipt["id"]

    def test_rebuild_index_not_publishable(self, service, index_service):
        index_service.run_action(INDEX_ORDER, "发起重建")
        receipt = service.publish([INDEX_ORDER, INDEX_MEMBER], "L1")
        assert receipt["status"] == "发布失败"
        assert any(item["index_id"] == INDEX_ORDER for item in receipt["invalid_indexes"])
        assert receipt["effective_index_ids"] == []

    def test_empty_submission_is_rejected_by_router_contract(self, service):
        # 服务层对空提交返回失败回执而不是凭空生效。
        receipt = service.publish([], "L1")
        assert receipt["status"] == "发布失败"
        assert service.current_receipt() is None


class TestUpgradeConflict:
    def test_upgrade_l1_to_l3(self, service, classify):
        entry, message = classify.upgrade_level(L1_TAG_MEMBER, "L3")
        assert entry is not None
        assert entry["安全等级"] == "L3"
        levels = {r["数据资源"]: r for r in service.resource_levels()}
        assert levels["会员营销标签库"]["安全等级"] == "L3"

    def test_upgrade_cannot_lower_level(self, classify):
        classify.upgrade_level(L1_TAG_MEMBER, "L3")
        entry, message = classify.upgrade_level(L1_TAG_MEMBER, "L1")
        assert entry is None
        assert "不低于目标等级" in message

    def test_interleaved_publish_conflict_keeps_previous_receipt(self, service, classify):
        first = service.publish([INDEX_ORDER, INDEX_MEMBER], "L1")
        classify.upgrade_level(L1_TAG_MEMBER, "L3")
        conflicted = service.publish([INDEX_ORDER, INDEX_MEMBER], "L1")

        assert conflicted["status"] == "发布失败"
        assert len(conflicted["conflicts"]) == 1
        assert conflicted["conflicts"][0]["actual_level"] == "L3"
        assert conflicted["conflicts"][0]["关联资源"] == "会员营销标签库"
        assert conflicted["effective_index_ids"] == []
        # 旧回执原样保留，失败发布不替代它。
        assert service.current_receipt()["id"] == first["id"]
        assert conflicted["retained_receipt_id"] == first["id"]
        assert service.get_receipt(first["id"])["status"] == "生效中"

    def test_republish_at_correct_level_succeeds_and_supersedes(self, service, classify):
        first = service.publish([INDEX_ORDER, INDEX_MEMBER], "L1")
        classify.upgrade_level(L1_TAG_MEMBER, "L3")
        service.publish([INDEX_ORDER, INDEX_MEMBER], "L1")  # 冲突失败
        republished = service.publish([INDEX_ORDER, INDEX_MEMBER], "L3")

        assert republished["status"] == "生效中"
        assert republished["superseded_receipt_id"] == first["id"]
        assert service.get_receipt(first["id"])["status"] == "已被替代"
        assert service.current_receipt()["id"] == republished["id"]


class TestLevelFilteredSearch:
    def test_search_without_receipt_returns_empty(self, service):
        result = service.search("L1")
        assert result["items"] == []
        assert result["receipt_id"] is None

    def test_two_level_search_after_conflict(self, service, classify):
        receipt = service.publish([INDEX_ORDER, INDEX_MEMBER], "L1")
        classify.upgrade_level(L1_TAG_MEMBER, "L3")
        service.publish([INDEX_ORDER, INDEX_MEMBER], "L1")  # 冲突失败，旧回执仍生效

        l1 = service.search("L1")
        l3 = service.search("L3")

        # 每次检索都绑定一个可识别的生效范围。
        assert l1["receipt_id"] == l3["receipt_id"] == receipt["id"]
        assert [i["index_id"] for i in l1["items"]] == [INDEX_ORDER]
        assert sorted(i["index_id"] for i in l3["items"]) == [INDEX_ORDER, INDEX_MEMBER]
        # 普通分析员的隐藏清单明确包含被升等受限的资源。
        assert [h["index_id"] for h in l1["hidden_by_level"]] == [INDEX_MEMBER]

    def test_keyword_filter_keeps_receipt_scope(self, service):
        service.publish([INDEX_ORDER, INDEX_MEMBER], "L1")
        result = service.search("L3", keyword="会员")
        assert [i["index_id"] for i in result["items"]] == [INDEX_MEMBER]
        assert result["receipt_id"] is not None


class TestReceiptDetail:
    def test_failed_receipt_detail_lists_retained_entries(self, service, classify):
        service.publish([INDEX_ORDER, INDEX_MEMBER], "L1")
        classify.upgrade_level(L1_TAG_MEMBER, "L3")
        failed = service.publish([INDEX_ORDER, INDEX_MEMBER], "L1")
        detail = service.receipt_detail(failed["id"])

        assert detail["effective_index_ids"] == []
        assert [e["index_id"] for e in detail["retained_entries"]] == [INDEX_ORDER]
        assert detail["current_receipt_id"] is not None

    def test_success_receipt_detail_exposes_effective_scope(self, service):
        receipt = service.publish([INDEX_ORDER, INDEX_MEMBER], "L1")
        detail = service.receipt_detail(receipt["id"])
        assert detail["effective_index_ids"] == [INDEX_ORDER, INDEX_MEMBER]
        assert {item["resource_level"] for item in detail["effective_scope"]} == {"L1"}


class TestFailedRebuildRetention:
    def test_rebuilding_entry_hidden_but_siblings_remain_searchable(self, service, index_service):
        service.publish([INDEX_ORDER, INDEX_MEMBER], "L1")
        index_service.run_action(INDEX_ORDER, "发起重建")

        l1 = service.search("L1")
        l3 = service.search("L3")
        assert [h["index_id"] for h in l1["hidden_unavailable"]] == [INDEX_ORDER]
        assert all(i["index_id"] != INDEX_ORDER for i in l1["items"])
        # 同范围内仍可搜索的另一条低等级条目没有被失败重建吞掉。
        assert [i["index_id"] for i in l3["items"]] == [INDEX_MEMBER]

    def test_completed_rebuild_restores_searchability(self, service, index_service):
        service.publish([INDEX_ORDER, INDEX_MEMBER], "L1")
        index_service.run_action(INDEX_ORDER, "发起重建")
        restored, _ = index_service.run_action(INDEX_ORDER, "完成重建")
        assert restored["status"] == "有效"
        assert restored["可搜索标记"] == "可搜索"

        l3 = service.search("L3")
        assert sorted(i["index_id"] for i in l3["items"]) == [INDEX_ORDER, INDEX_MEMBER]
