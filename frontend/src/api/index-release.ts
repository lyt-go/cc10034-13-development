/** 索引发布接口封装：资源分级、发布核验、回执与等级检索。 */
import { request } from './client'
import type {
  PublishableIndex,
  PublishResult,
  ReleaseReceipt,
  ResourceLevel,
  SearchResult,
} from '@/data/index-release'

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    let detail = fallback
    try {
      const body = await response.json()
      detail = body.detail ?? fallback
    } catch {
      /* 保持兜底文案 */
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

export async function fetchResources(): Promise<ResourceLevel[]> {
  const response = await request('/api/index-release/resources')
  const body = await readJson<{ items: ResourceLevel[] }>(response, '资源分级读取失败')
  return body.items
}

export async function upgradeResource(tagId: number, targetLevel: string): Promise<void> {
  const response = await request(`/api/index-release/resources/${tagId}/upgrade`, {
    method: 'POST',
    body: JSON.stringify({ target_level: targetLevel }),
  })
  await readJson(response, '资源升等失败')
}

export async function fetchPublishableIndexes(): Promise<PublishableIndex[]> {
  const response = await request('/api/index-release/indexes')
  const body = await readJson<{ items: PublishableIndex[] }>(response, '可发布索引读取失败')
  return body.items
}

export async function publishIndexes(
  indexIds: number[],
  resourceLevel: string,
  operator: string,
  remark: string,
): Promise<PublishResult> {
  const response = await request('/api/index-release/publish', {
    method: 'POST',
    body: JSON.stringify({
      index_ids: indexIds,
      resource_level: resourceLevel,
      operator,
      remark,
    }),
  })
  return readJson<PublishResult>(response, '索引发布失败')
}

export async function fetchReceipts(): Promise<ReleaseReceipt[]> {
  const response = await request('/api/index-release/receipts')
  const body = await readJson<{ items: ReleaseReceipt[] }>(response, '发布回执读取失败')
  return body.items
}

export async function fetchReceiptDetail(receiptId: number): Promise<ReleaseReceipt> {
  const response = await request(`/api/index-release/receipts/${receiptId}`)
  return readJson<ReleaseReceipt>(response, '发布详情读取失败')
}

export async function searchByLevel(accessLevel: string, keyword = ''): Promise<SearchResult> {
  const response = await request('/api/index-release/search', {
    method: 'POST',
    body: JSON.stringify({ access_level: accessLevel, keyword: keyword || null }),
  })
  return readJson<SearchResult>(response, '检索失败')
}
