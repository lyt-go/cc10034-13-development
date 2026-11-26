/** 索引发布相关类型：与后端 /api/index-release 返回结构保持一致。 */

export type ResourceLevel = {
  tag_id: number
  数据资源: string
  安全等级: string
  level_value: number
  status: string
  abnormal: boolean
}

export type PublishableIndex = {
  index_id: number
  条目编号: string
  加密域: string
  索引类型: string
  关联资源: string
  index_status: string
  可搜索标记: string
  resource_level: string
  level_value: number
  publishable: boolean
}

export type ScopeItem = {
  index_id: number
  条目编号: string
  加密域: string
  关联资源: string
  index_status: string
  resource_level: string
}

export type ConflictItem = {
  index_id: number
  条目编号: string
  关联资源: string
  declared_level: string
  actual_level: string
  reason: string
}

export type ReleaseReceipt = {
  id: number
  回执编号: string
  status: string
  operator: string
  remark: string
  created_at: string
  declared_level: string
  submitted_index_ids: number[]
  submitted_snapshot: ScopeItem[]
  conflicts: ConflictItem[]
  invalid_indexes: { index_id: number; 条目编号?: string; reason: string }[]
  unregistered_resources: unknown[]
  effective_index_ids: number[]
  effective_scope: ScopeItem[]
  effective_level: string
  superseded_receipt_id: number | null
  retained_receipt_id: number | null
  current_receipt_id?: number | null
  retained_entries?: SearchItem[]
}

export type SearchItem = {
  index_id: number
  条目编号: string
  加密域: string
  索引类型: string
  关联资源: string
  resource_level: string
  可搜索标记: string
  receipt_id: number
  回执编号: string
}

export type SearchResult = {
  receipt_id: number | null
  receipt_no: string | null
  access_level: string
  effective_level: string | null
  items: SearchItem[]
  total: number
  hidden_by_level: { index_id: number; 条目编号: string; 关联资源: string; actual_level: string }[]
  hidden_unavailable: { index_id: number; 条目编号: string; index_status: string; 可搜索标记: string }[]
  message: string
}

export type PublishResult = {
  ok: boolean
  receipt: ReleaseReceipt
}
