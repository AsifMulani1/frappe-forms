import { createRouter, createWebHistory } from 'vue-router'
import { sessionUser, session, loginRedirect } from './data/session'

const routes = [
  { path: '/', name: 'Dashboard', component: () => import('./pages/Dashboard.vue') },
  { path: '/:slug/edit', name: 'Builder', component: () => import('./pages/Builder.vue'), props: true },
  { path: '/:slug/responses', name: 'Responses', component: () => import('./pages/Responses.vue'), props: true },
  // Public, guest-allowed respondent form.
  { path: '/f/:slug', name: 'PublicForm', component: () => import('./pages/PublicForm.vue'), props: true, meta: { public: true } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory('/forms'),
  routes,
})

// Guard non-public routes with a live session check; redirect guests to login.
router.beforeEach(async (to) => {
  if (to.meta.public) return true
  if (session.user === null && !session.isLoggedIn) {
    try {
      await sessionUser.fetch()
    } catch (e) {
      // ignore
    }
  }
  if (!session.isLoggedIn) {
    loginRedirect('/forms' + to.fullPath)
    return false
  }
  return true
})

export default router
