<script setup>
import { computed, h, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Dropdown, Sidebar, createResource } from 'frappe-ui'
import Icon from './Icon.vue'
import AppLauncher from './AppLauncher.vue'
import { session, logout } from '../data/session'
import { prefs, toggleDevMode, toggleTheme } from '../data/prefs'

const router = useRouter()
const route = useRoute()
const launcher = ref(false)

const activeView = computed(() => route.query.view || 'all')
const counts = createResource({ url: 'forms.admin.nav_counts', auto: true })
defineExpose({ refreshCounts: () => counts.reload() })

// Header dropdown (Frappe CRM-style: brand + user identity is the menu trigger).
const headerMenu = computed(() => [
  { label: 'Apps', icon: 'lucide-layout-grid', onClick: () => (launcher.value = true) },
  { label: prefs.dark ? 'Light mode' : 'Dark mode', icon: prefs.dark ? 'sun' : 'moon', onClick: toggleTheme },
  { label: 'Developer mode', icon: prefs.devMode ? 'lucide-check' : 'lucide-code', onClick: toggleDevMode },
  { label: 'Log out', icon: 'log-out', onClick: logout },
])

// frappe-ui SidebarItem renders string icons as literal text, so pass a real component.
const icon = (name) => () => h(Icon, { name, size: 16 })

const NAV = [
  { id: 'all', label: 'All forms', icon: 'clipboard-list' },
  { id: 'shared', label: 'Shared with me', icon: 'users' },
  { id: 'templates', label: 'Templates', icon: 'layout-template' },
  { id: 'archived', label: 'Archived', icon: 'archive' },
]
function go(view) {
  router.push(view === 'all' ? '/' : { path: '/', query: { view } })
}

const sections = computed(() => [{
  items: NAV.map((n) => ({
    label: n.label,
    icon: icon(n.icon),
    suffix: counts.data?.[n.id] ? String(counts.data[n.id]) : undefined,
    isActive: activeView.value === n.id,
    onClick: () => go(n.id),
  })),
}])
</script>

<template>
  <div class="flex h-full w-full">
    <Sidebar v-model:collapsed="prefs.navCollapsed" :sections="sections" class="!bg-surface-white">
      <!-- header: brand + user identity is the menu (Frappe CRM pattern), then search -->
      <template #header>
        <Dropdown :options="headerMenu" placement="bottom-start">
          <button class="flex items-center h-12 w-full rounded-md transition-colors hover:bg-surface-gray-3"
                  :class="prefs.navCollapsed ? 'justify-center' : 'gap-2.5 px-2'">
            <span class="w-8 h-8 rounded-[7px] bg-accent flex items-center justify-center text-white shrink-0">
              <Icon name="clipboard-list" :size="16" />
            </span>
            <template v-if="!prefs.navCollapsed">
              <div class="flex flex-col flex-1 min-w-0 text-left leading-tight">
                <span class="text-sm font-medium text-ink-gray-9 truncate">Frappe Forms</span>
                <span class="text-[11px] text-ink-gray-5 truncate">{{ session.fullName || session.user || 'Signed in' }}</span>
              </div>
              <Icon name="chevron-down" :size="15" class="text-ink-gray-5 shrink-0" />
            </template>
          </button>
        </Dropdown>
      </template>
    </Sidebar>

    <div class="flex flex-col flex-1 min-w-0">
      <slot />
    </div>

    <AppLauncher v-model="launcher" />
  </div>
</template>
