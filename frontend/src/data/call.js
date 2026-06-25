import { frappeRequest } from 'frappe-ui'

// Thin wrapper around frappeRequest for whitelisted method calls.
// Returns the unwrapped `message` payload (frappeRequest handles CSRF + cookies).
export function call(method, params = {}) {
  return frappeRequest({ url: method, method: 'POST', params })
}
