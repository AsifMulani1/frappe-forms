<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Sidebar, SidebarHeader, SidebarItem, SidebarCollapseToggle, createResource } from 'frappe-ui'
import AppLauncher from './AppLauncher.vue'
import { session, logout } from '../data/session'
import { prefs, toggleDevMode, toggleTheme } from '../data/prefs'
import brandLogo from '../assets/logo.svg'

const router = useRouter()
const route = useRoute()
const launcher = ref(false)

const activeView = computed(() => route.query.view || 'all')
const counts = createResource({ url: 'forms.admin.nav_counts', auto: true })
defineExpose({ refreshCounts: () => counts.reload() })

// Header dropdown (Frappe CRM-style: brand + user identity is the menu trigger).
const headerMenu = computed(() => [
  { label: 'Apps', icon: 'lucide-layout-grid', onClick: () => (launcher.value = true) },
  { label: prefs.dark ? 'Light mode' : 'Dark mode', icon: prefs.dark ? 'lucide-sun' : 'lucide-moon', onClick: toggleTheme },
  { label: 'Developer mode', icon: prefs.devMode ? 'lucide-check' : 'lucide-code', onClick: toggleDevMode },
  { label: 'Log out', icon: 'lucide-log-out', onClick: logout },
])

const NAV = [
  { id: 'all', label: 'All forms', icon: 'lucide-clipboard-list' },
  { id: 'shared', label: 'Shared with me', icon: 'lucide-users' },
  { id: 'templates', label: 'Templates', icon: 'lucide-layout-template' },
  { id: 'archived', label: 'Archived', icon: 'lucide-archive' },
]
function go(view) {
  router.push(view === 'all' ? '/' : { path: '/', query: { view } })
}
</script>

<template>
  <div class="flex h-full w-full">
    <Sidebar v-model:collapsed="prefs.navCollapsed">
      <div class="flex h-full flex-col p-2">
        <!-- brand + user identity is the menu (Frappe CRM pattern) -->
        <SidebarHeader
          title="Frappe Forms"
          :subtitle="session.fullName || session.user || 'Signed in'"
          :logo="brandLogo"
          :menu-items="headerMenu"
        />

        <!-- -mx/px so the active item's shadow ring isn't clipped at the edges -->
        <nav class="-mx-1 mt-1 flex-1 space-y-0.5 overflow-y-auto overflow-x-hidden px-1">
          <SidebarItem
            v-for="n in NAV"
            :key="n.id"
            :label="n.label"
            :icon="n.icon"
            :active="activeView === n.id"
            :suffix="counts.data?.[n.id] ? String(counts.data[n.id]) : undefined"
            @click="go(n.id)"
          />
        </nav>

        <div class="mt-auto">
          <SidebarCollapseToggle />
        </div>
      </div>
    </Sidebar>

    <div class="flex flex-col flex-1 min-w-0">
      <slot />
    </div>

    <AppLauncher v-model="launcher" />
  </div>
</template>
