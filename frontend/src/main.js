import { createApp } from 'vue'
import { FrappeUI, setConfig, frappeRequest } from 'frappe-ui'
import App from './App.vue'
import router from './router'
import './index.css'

// frappe-ui handles CSRF + cookies through frappeRequest.
setConfig('resourceFetcher', frappeRequest)

const app = createApp(App)
app.use(router)
// socketio: false — we don't use realtime; avoids a failed socket.io connection in the console.
app.use(FrappeUI, { socketio: false })
app.mount('#app')
