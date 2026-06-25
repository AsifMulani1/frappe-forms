<script setup>
import { FrappeUIProvider, Dialogs } from 'frappe-ui'
</script>

<template>
  <FrappeUIProvider>
    <router-view />
    <!-- Host for confirmDialog() — without this, confirm dialogs never render. -->
    <Dialogs />
  </FrappeUIProvider>
</template>
