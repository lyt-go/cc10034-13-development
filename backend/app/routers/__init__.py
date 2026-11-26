"""业务路由汇总：跨模块链接与索引发布路由必须先于通用资源路由注册。"""
from __future__ import annotations

from app.routers import cross_links, index_release, resource

ROUTERS = [cross_links, index_release, resource]
