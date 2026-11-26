"""索引发布路由：发布页所需的资源分级、发布核验、回执与等级检索接口。

路由统一挂在 /api/index-release 前缀下，并在资源路由（/api/{module}）
之前注册，避免被通用动态路径抢先匹配。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.schemas import IndexPublishPayload, IndexSearchPayload, LevelUpgradePayload
from app.services.classify_tag import ClassifyTagService
from app.services.index_release import RECEIPT_ACTIVE, index_release_service

router = APIRouter(prefix="/api/index-release", tags=["索引发布"])

_classify_service = ClassifyTagService()


@router.get("/resources")
def list_resources() -> dict[str, Any]:
    """资源分级面板：返回各数据资源当前安全等级及对应索引条目。"""
    return {"items": index_release_service.resource_levels()}


@router.post("/resources/{tag_id}/upgrade")
def upgrade_resource(tag_id: int, payload: LevelUpgradePayload) -> dict[str, Any]:
    """资源升等：把分级标签对应资源调整到目标等级（默认 L3）。"""
    entry, message = _classify_service.upgrade_level(tag_id, payload.target_level.strip() or "L3")
    if entry is None:
        raise HTTPException(status_code=400, detail=message)
    return {"ok": True, "message": message, "entry": entry}


@router.get("/indexes")
def list_publishable_indexes() -> dict[str, Any]:
    """可发布索引候选：含关联资源当前等级与是否满足发布条件。"""
    return {"items": index_release_service.publishable_indexes()}


@router.post("/publish")
def publish_index(payload: IndexPublishPayload) -> dict[str, Any]:
    """提交待发布索引与资源分级，后端核验覆盖范围并生成发布回执。"""
    if not payload.index_ids:
        raise HTTPException(status_code=400, detail="请至少选择一个待发布索引条目")
    if not payload.resource_level.strip():
        raise HTTPException(status_code=400, detail="请提交本次发布的资源分级（如 L1/L3）")
    receipt = index_release_service.publish(
        index_ids=payload.index_ids,
        resource_level=payload.resource_level,
        operator=payload.operator,
        remark=payload.remark,
    )
    return {"ok": receipt["status"] == RECEIPT_ACTIVE, "receipt": receipt}


@router.get("/receipts")
def list_receipts() -> dict[str, Any]:
    """发布回执历史。"""
    return {"items": index_release_service.list_receipts()}


@router.get("/receipts/{receipt_id}")
def get_receipt(receipt_id: int) -> dict[str, Any]:
    """发布详情：实际生效范围，以及失败后仍保留的可检索条目。"""
    detail = index_release_service.receipt_detail(receipt_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"索引发布回执 {receipt_id} 不存在")
    return detail


@router.post("/search")
def search_index(payload: IndexSearchPayload) -> dict[str, Any]:
    """检索入口：按访问者等级在当前生效回执范围内返回可用条目。"""
    if not payload.access_level.strip():
        raise HTTPException(status_code=400, detail="请提供访问者等级（如 L1/L3）")
    return index_release_service.search(payload.access_level.strip(), payload.keyword)
