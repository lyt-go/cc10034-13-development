"""通用接口契约；模块字段由领域服务持有，不再为每个模块复制一份模型类。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ActionPayload(BaseModel):
    action: str
    remark: str | None = None


class IndexPublishPayload(BaseModel):
    """索引发布请求：操作员提交待发布索引条目与本次发布的资源分级上限。"""

    index_ids: list[int] = Field(default_factory=list)
    resource_level: str = Field(default="", description="本次发布声明覆盖的最高资源分级，如 L1/L3")
    operator: str | None = None
    remark: str | None = None


class LevelUpgradePayload(BaseModel):
    """资源升等请求：把分级标签对应资源调整到目标安全等级。"""

    target_level: str = Field(default="L3")


class IndexSearchPayload(BaseModel):
    """检索入口请求：按访问者等级在当前生效回执范围内返回可用条目。"""

    access_level: str = Field(default="L1", description="访问者持有的访问资格等级，如 L1/L3")
    keyword: str | None = None
