<template>
  <section class="page index-release-page">
    <header class="page-head">
      <div>
        <h2>索引发布</h2>
        <p class="page-desc">
          密文索引重建后的上线前范围核验：提交待发布索引与资源分级，后端计算覆盖范围并生成发布回执；
          检索入口按回执与访问者等级返回可用条目。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" data-testid="refresh-all" type="button" @click="reloadAll">刷新数据</button>
      </div>
    </header>

    <p v-if="message" class="error-text" data-testid="global-message">{{ message }}</p>

    <!-- 1. 资源分级与升等 -->
    <h3 class="section-title">① 资源分级（升等会在下一次发布核验时生效）</h3>
    <table class="data-table" data-testid="resource-table">
      <thead>
        <tr>
          <th>分级标签ID</th><th>数据资源</th><th>当前安全等级</th><th>标签状态</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="res in resources" :key="res.tag_id" :data-testid="`resource-row-${res.tag_id}`">
          <td>{{ res.tag_id }}</td>
          <td>{{ res.数据资源 }}</td>
          <td>
            <span class="level-badge" :class="`level-${res.安全等级}`">{{ res.安全等级 }}</span>
            <span v-if="res.abnormal" class="warn-tag">已升等待核验</span>
          </td>
          <td>{{ res.status }}</td>
          <td class="row-actions">
            <button
              class="link"
              type="button"
              :data-testid="`upgrade-${res.tag_id}`"
              :disabled="res.安全等级 === 'L3' || res.安全等级 === 'L4'"
              @click="onUpgrade(res.tag_id)"
            >
              资源升等(L3)
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- 2. 提交发布 -->
    <h3 class="section-title">② 提交待发布索引与资源分级</h3>
    <div class="publish-panel">
      <form class="analysis-form" @submit.prevent="onPublish">
        <label>
          发布资源分级上限
          <select v-model="publishLevel" data-testid="publish-level">
            <option value="L1">L1（普通分析员可检索）</option>
            <option value="L2">L2</option>
            <option value="L3">L3（受限资源）</option>
            <option value="L4">L4</option>
          </select>
        </label>
        <label>
          操作员
          <input v-model="operator" data-testid="publish-operator" placeholder="操作员" />
        </label>
        <label class="grow">
          备注
          <input v-model="remark" data-testid="publish-remark" placeholder="本次发布说明（可选）" />
        </label>
      </form>
      <table class="data-table" data-testid="candidate-table">
        <thead>
          <tr>
            <th style="width: 40px">选择</th><th>条目编号</th><th>加密域</th><th>关联资源</th>
            <th>资源等级</th><th>索引状态</th><th>可发布</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="candidate in candidates" :key="candidate.index_id" :data-testid="`candidate-row-${candidate.index_id}`">
            <td>
              <input
                v-model="selectedIds"
                type="checkbox"
                :value="candidate.index_id"
                :data-testid="`select-${candidate.index_id}`"
                :disabled="!candidate.publishable"
              />
            </td>
            <td>{{ candidate.条目编号 }}</td>
            <td>{{ candidate.加密域 }}</td>
            <td>{{ candidate.关联资源 }}</td>
            <td><span class="level-badge" :class="`level-${candidate.resource_level}`">{{ candidate.resource_level }}</span></td>
            <td>{{ candidate.index_status }}</td>
            <td>{{ candidate.publishable ? '满足' : '不满足（重建中/已失效）' }}</td>
          </tr>
        </tbody>
      </table>
      <div class="page-actions publish-actions">
        <span class="muted-text">已选 {{ selectedIds.length }} 个索引条目</span>
        <button class="btn primary" data-testid="submit-publish" type="button" :disabled="publishing" @click="onPublish">
          {{ publishing ? '核验中…' : '提交发布并生成回执' }}
        </button>
      </div>
    </div>

    <!-- 3. 发布回执历史 -->
    <h3 class="section-title">③ 发布回执（点击查看实际生效范围）</h3>
    <table class="data-table" data-testid="receipt-table">
      <thead>
        <tr>
          <th>回执编号</th><th>状态</th><th>声明分级</th><th>生效范围等级</th>
          <th>提交条目</th><th>生效条目</th><th>冲突</th><th>操作员</th><th>时间</th><th>详情</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="receipt in receipts" :key="receipt.id" :data-testid="`receipt-row-${receipt.id}`" :data-status="receipt.status">
          <td>{{ receipt.回执编号 }}</td>
          <td><span class="receipt-status" :class="`receipt-${receipt.status}`">{{ receipt.status }}</span></td>
          <td>{{ receipt.declared_level }}</td>
          <td>{{ receipt.effective_level }}</td>
          <td>{{ receipt.submitted_index_ids.join('、') || '—' }}</td>
          <td>{{ receipt.effective_index_ids.join('、') || '—' }}</td>
          <td>{{ receipt.conflicts.length }}</td>
          <td>{{ receipt.operator }}</td>
          <td>{{ receipt.created_at }}</td>
          <td>
            <button class="link" type="button" :data-testid="`detail-${receipt.id}`" @click="onShowDetail(receipt.id)">
              发布详情
            </button>
          </td>
        </tr>
        <tr v-if="!receipts.length">
          <td colspan="10" class="empty-state">暂无发布回执，请先提交一次发布。</td>
        </tr>
      </tbody>
    </table>

    <!-- 4. 按访问者等级检索 -->
    <h3 class="section-title">④ 检索入口（按访问者等级返回生效回执内的可用条目）</h3>
    <div class="publish-panel">
      <form class="analysis-form" @submit.prevent="onSearch">
        <label>
          访问者等级
          <select v-model="accessLevel" data-testid="access-level">
            <option value="L1">L1 普通分析员</option>
            <option value="L2">L2</option>
            <option value="L3">L3 授权分析员</option>
            <option value="L4">L4</option>
          </select>
        </label>
        <label class="grow">
          关键词（条目编号/加密域/关联资源）
          <input v-model="searchKeyword" data-testid="search-keyword" placeholder="可选" />
        </label>
        <button class="btn primary" data-testid="submit-search" type="button" @click="onSearch">检索</button>
      </form>
      <p v-if="searchResult" class="muted-text" data-testid="search-scope">
        本次检索生效范围：回执
        <strong>{{ searchResult.receipt_no ?? '无' }}</strong>
        （ID={{ searchResult.receipt_id ?? '—' }}），范围等级 {{ searchResult.effective_level ?? '—' }}，
        命中 {{ searchResult.total }} 条
        <span v-if="searchResult.hidden_by_level.length">
          ，{{ searchResult.hidden_by_level.length }} 条因等级受限未返回
        </span>
        <span v-if="searchResult.hidden_unavailable.length">
          ，{{ searchResult.hidden_unavailable.length }} 条因重建/失效不可用
        </span>
      </p>
      <table class="data-table" data-testid="search-table">
        <thead>
          <tr><th>条目编号</th><th>加密域</th><th>索引类型</th><th>关联资源</th><th>资源等级</th><th>来源回执</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in searchResult?.items ?? []" :key="item.index_id" :data-testid="`search-item-${item.index_id}`">
            <td>{{ item.条目编号 }}</td>
            <td>{{ item.加密域 }}</td>
            <td>{{ item.索引类型 }}</td>
            <td>{{ item.关联资源 }}</td>
            <td><span class="level-badge" :class="`level-${item.resource_level}`">{{ item.resource_level }}</span></td>
            <td>{{ item.回执编号 }}</td>
          </tr>
          <tr v-if="searchResult && !searchResult.items.length">
            <td colspan="6" class="empty-state">{{ searchResult.message || '当前等级下无可检索条目' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 5. 发布详情弹窗 -->
    <div v-if="detail" class="modal-backdrop" data-testid="detail-modal" @click.self="detail = null">
      <div class="modal detail-modal">
        <h3>发布详情 · {{ detail.回执编号 }}</h3>
        <dl class="detail-grid">
          <dt>回执状态</dt><dd><span class="receipt-status" :class="`receipt-${detail.status}`">{{ detail.status }}</span></dd>
          <dt>声明分级</dt><dd>{{ detail.declared_level }}</dd>
          <dt>实际生效范围等级</dt><dd>{{ detail.effective_level }}</dd>
          <dt>提交索引</dt><dd>{{ detail.submitted_index_ids.join('、') || '—' }}</dd>
          <dt>实际生效索引</dt><dd>{{ detail.effective_index_ids.join('、') || '本次发布未生效' }}</dd>
          <dt>替代回执</dt><dd>{{ detail.superseded_receipt_id ?? '—' }}</dd>
          <dt>失败后保留回执</dt><dd>{{ detail.retained_receipt_id ?? '—' }}</dd>
        </dl>

        <h4 class="detail-sub">实际生效范围</h4>
        <table class="data-table">
          <thead><tr><th>条目编号</th><th>加密域</th><th>关联资源</th><th>资源等级</th></tr></thead>
          <tbody>
            <tr v-for="scope in detail.effective_scope" :key="scope.index_id">
              <td>{{ scope.条目编号 }}</td><td>{{ scope.加密域 }}</td><td>{{ scope.关联资源 }}</td><td>{{ scope.resource_level }}</td>
            </tr>
            <tr v-if="!detail.effective_scope.length"><td colspan="4" class="empty-state">本次发布失败，未产生新生效范围</td></tr>
          </tbody>
        </table>

        <h4 class="detail-sub">冲突明细</h4>
        <table v-if="detail.conflicts.length" class="data-table">
          <thead><tr><th>条目编号</th><th>关联资源</th><th>声明等级</th><th>实际等级</th><th>原因</th></tr></thead>
          <tbody>
            <tr v-for="c in detail.conflicts" :key="c.index_id">
              <td>{{ c.条目编号 }}</td><td>{{ c.关联资源 }}</td><td>{{ c.declared_level }}</td><td>{{ c.actual_level }}</td><td>{{ c.reason }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted-text">无升等冲突。</p>

        <h4 class="detail-sub">失败后仍保留的可检索条目（L1 视角）</h4>
        <table class="data-table">
          <thead><tr><th>条目编号</th><th>加密域</th><th>关联资源</th><th>资源等级</th></tr></thead>
          <tbody>
            <tr v-for="keep in detail.retained_entries ?? []" :key="keep.index_id">
              <td>{{ keep.条目编号 }}</td><td>{{ keep.加密域 }}</td><td>{{ keep.关联资源 }}</td><td>{{ keep.resource_level }}</td>
            </tr>
            <tr v-if="!(detail.retained_entries ?? []).length"><td colspan="4" class="empty-state">—</td></tr>
          </tbody>
        </table>

        <div class="page-actions">
          <button class="btn primary" type="button" @click="detail = null">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  fetchPublishableIndexes,
  fetchReceiptDetail,
  fetchReceipts,
  fetchResources,
  publishIndexes,
  searchByLevel,
  upgradeResource,
} from '@/api/index-release'
import type {
  PublishableIndex,
  ReleaseReceipt,
  ResourceLevel,
  SearchResult,
} from '@/data/index-release'

const resources = ref<ResourceLevel[]>([])
const candidates = ref<PublishableIndex[]>([])
const receipts = ref<ReleaseReceipt[]>([])
const selectedIds = ref<number[]>([])
const publishLevel = ref('L1')
const operator = ref('值班操作员')
const remark = ref('')
const publishing = ref(false)
const accessLevel = ref('L1')
const searchKeyword = ref('')
const searchResult = ref<SearchResult | null>(null)
const detail = ref<ReleaseReceipt | null>(null)
const message = ref('')

async function reloadAll() {
  message.value = ''
  try {
    const [resourceRows, candidateRows, receiptRows] = await Promise.all([
      fetchResources(),
      fetchPublishableIndexes(),
      fetchReceipts(),
    ])
    resources.value = resourceRows
    candidates.value = candidateRows
    receipts.value = receiptRows
    // 清理已不可选的选中项。
    const selectable = new Set(candidateRows.filter((c) => c.publishable).map((c) => c.index_id))
    selectedIds.value = selectedIds.value.filter((id) => selectable.has(id))
  } catch (error) {
    message.value = error instanceof Error ? error.message : '数据加载失败'
  }
}

async function onUpgrade(tagId: number) {
  message.value = ''
  try {
    await upgradeResource(tagId, 'L3')
    await reloadAll()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '资源升等失败'
  }
}

async function onPublish() {
  message.value = ''
  if (!selectedIds.value.length) {
    message.value = '请至少勾选一个待发布索引条目'
    return
  }
  publishing.value = true
  try {
    const result = await publishIndexes(
      [...selectedIds.value],
      publishLevel.value,
      operator.value,
      remark.value,
    )
    await reloadAll()
    if (!result.ok) {
      message.value = `发布回执 ${result.receipt.回执编号} 判定为「${result.receipt.status}」，旧生效回执已保留，请查看冲突明细。`
    }
  } catch (error) {
    message.value = error instanceof Error ? error.message : '索引发布失败'
  } finally {
    publishing.value = false
  }
}

async function onSearch() {
  message.value = ''
  try {
    searchResult.value = await searchByLevel(accessLevel.value, searchKeyword.value)
  } catch (error) {
    message.value = error instanceof Error ? error.message : '检索失败'
  }
}

async function onShowDetail(receiptId: number) {
  message.value = ''
  try {
    detail.value = await fetchReceiptDetail(receiptId)
  } catch (error) {
    message.value = error instanceof Error ? error.message : '发布详情读取失败'
  }
}

onMounted(reloadAll)
</script>

<style scoped>
.section-title {
  margin: 20px 0 8px;
  font-size: 15px;
  border-left: 4px solid var(--brand);
  padding-left: 8px;
}
.publish-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}
.publish-actions {
  margin-top: 12px;
  justify-content: space-between;
}
.muted-text {
  color: var(--muted);
  font-size: 13px;
}
.grow {
  flex: 1;
}
.level-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
  background: #e2e8f0;
  color: #334155;
}
.level-L3,
.level-L4 {
  background: #fee2e2;
  color: #b42318;
}
.level-L2 {
  background: #fef3c7;
  color: #92400e;
}
.level-L1 {
  background: #dcfce7;
  color: #166534;
}
.warn-tag {
  margin-left: 6px;
  font-size: 12px;
  color: #b42318;
}
.receipt-status {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
}
.receipt-生效中 {
  background: #dcfce7;
  color: #166534;
}
.receipt-发布失败 {
  background: #fee2e2;
  color: #b42318;
}
.receipt-已被替代 {
  background: #e2e8f0;
  color: #475569;
}
.detail-modal {
  width: min(820px, 100%);
}
.detail-grid {
  display: grid;
  grid-template-columns: 140px 1fr 140px 1fr;
  gap: 6px 10px;
  margin: 8px 0 12px;
  font-size: 13px;
}
.detail-grid dt {
  color: var(--muted);
}
.detail-grid dd {
  margin: 0;
}
.detail-sub {
  margin: 14px 0 6px;
  font-size: 13px;
}
</style>
