import { createRouter, createWebHistory } from 'vue-router'

import Overview from '@/views/Overview.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'
import IndexReleaseView from '@/views/IndexReleaseView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    // 索引发布为独立页面，需排在动态 :moduleKey 之前，避免被工作台路由吞掉。
    { path: '/index-release', name: 'index-release', component: IndexReleaseView },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
