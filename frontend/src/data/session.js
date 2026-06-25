import { createResource } from 'frappe-ui'
import { reactive } from 'vue'

// Live session - who is logged in. No hardcoded user anywhere.
export const session = reactive({
  user: null,
  fullName: null,
  isLoggedIn: false,
})

export const sessionUser = createResource({
  url: 'forms.api.session_info',
  onSuccess(data) {
    session.user = data?.user || null
    session.fullName = data?.full_name || null
    session.isLoggedIn = !!session.user
  },
  onError() {
    session.user = null
    session.fullName = null
    session.isLoggedIn = false
  },
})

export function loginRedirect(to) {
  const target = to || window.location.pathname
  window.location.href = `/login?redirect-to=${encodeURIComponent(target)}`
}

export function logout() {
  window.location.href = '/api/method/logout'
}
