// End-to-end identity encryption for forms. Everything here runs in the browser with the native
// WebCrypto API — no dependencies, no key ever crosses the network in usable form.
//
// Scheme (a "sealed box" / ECIES):
//   • The creator owns an ECDH P-256 keypair. The private key is wrapped under a passphrase
//     (PBKDF2 → AES-GCM) and only ever stored wrapped; the passphrase never leaves this browser.
//   • Each respondent seals their identity to the creator's PUBLIC key: an ephemeral ECDH keypair
//     agrees an AES-GCM key with the creator's public key, encrypts, and ships the ephemeral public
//     key alongside the ciphertext. Only the creator's private key can re-derive that AES key.
//   • The server stores only ciphertext and can never read it.
//
// Honest ceiling: this defeats anyone reading the database, files, or backups. It cannot defeat an
// attacker who rewrites the JS this page serves (they could swap the public key or capture the
// passphrase) — the fingerprint check mitigates key-swap; the rest is the fundamental limit of
// browser-delivered crypto.

const PBKDF2_ITERATIONS = 210000
const enc = new TextEncoder()
const dec = new TextDecoder()

function b64(buf) {
  const bytes = new Uint8Array(buf)
  let s = ''
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i])
  return btoa(s)
}
function unb64(str) {
  const s = atob(str)
  const bytes = new Uint8Array(s.length)
  for (let i = 0; i < s.length; i++) bytes[i] = s.charCodeAt(i)
  return bytes
}

const ECDH = { name: 'ECDH', namedCurve: 'P-256' }

// --- Creator key lifecycle -------------------------------------------------

// Generate a fresh identity keypair. Returns the base64 public key (shared with respondents) and
// the private CryptoKey (kept in memory, wrapped before it's ever persisted).
export async function generateKeypair() {
  const pair = await crypto.subtle.generateKey(ECDH, true, ['deriveKey', 'deriveBits'])
  const raw = await crypto.subtle.exportKey('raw', pair.publicKey)
  return { publicKey: b64(raw), privateKey: pair.privateKey }
}

async function passphraseKey(passphrase, salt) {
  const base = await crypto.subtle.importKey('raw', enc.encode(passphrase), 'PBKDF2', false, ['deriveKey'])
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations: PBKDF2_ITERATIONS, hash: 'SHA-256' },
    base,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  )
}

// Wrap the private key under the passphrase so it can be stored server-side without exposing it.
export async function wrapPrivateKey(privateKey, passphrase) {
  const salt = crypto.getRandomValues(new Uint8Array(16))
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const aes = await passphraseKey(passphrase, salt)
  const pkcs8 = await crypto.subtle.exportKey('pkcs8', privateKey)
  const wrapped = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, aes, pkcs8)
  return { wrapped: b64(wrapped), salt: b64(salt), iv: b64(iv) }
}

// Reverse of wrapPrivateKey. Throws (AES-GCM auth failure) on a wrong passphrase — callers treat
// that as "incorrect passphrase".
export async function unwrapPrivateKey(wrappedB64, saltB64, ivB64, passphrase) {
  const aes = await passphraseKey(passphrase, unb64(saltB64))
  const pkcs8 = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: unb64(ivB64) }, aes, unb64(wrappedB64))
  return crypto.subtle.importKey('pkcs8', pkcs8, ECDH, false, ['deriveKey', 'deriveBits'])
}

// A short, human-comparable fingerprint of the public key (SHA-256, first 8 bytes as hex pairs).
export async function fingerprint(publicKeyB64) {
  const hash = await crypto.subtle.digest('SHA-256', unb64(publicKeyB64))
  return Array.from(new Uint8Array(hash).slice(0, 8))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join(':')
}

// --- Per-submission sealing ------------------------------------------------

async function importPublic(publicKeyB64) {
  return crypto.subtle.importKey('raw', unb64(publicKeyB64), ECDH, false, [])
}

// Seal an identity object to the creator's public key. Returns a self-contained JSON string that
// only the matching private key can open.
export async function sealIdentity(publicKeyB64, obj) {
  const recipient = await importPublic(publicKeyB64)
  const ephemeral = await crypto.subtle.generateKey(ECDH, true, ['deriveKey'])
  const aes = await crypto.subtle.deriveKey(
    { name: 'ECDH', public: recipient }, ephemeral.privateKey,
    { name: 'AES-GCM', length: 256 }, false, ['encrypt'],
  )
  const iv = crypto.getRandomValues(new Uint8Array(12))
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, aes, enc.encode(JSON.stringify(obj)))
  const epk = await crypto.subtle.exportKey('raw', ephemeral.publicKey)
  return JSON.stringify({ v: 1, epk: b64(epk), iv: b64(iv), ct: b64(ct) })
}

// Open a sealed identity blob with the creator's private key. Returns the original object.
export async function openIdentity(privateKey, blobStr) {
  const blob = JSON.parse(blobStr)
  const ephemeral = await importPublic(blob.epk)
  const aes = await crypto.subtle.deriveKey(
    { name: 'ECDH', public: ephemeral }, privateKey,
    { name: 'AES-GCM', length: 256 }, false, ['decrypt'],
  )
  const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv: unb64(blob.iv) }, aes, unb64(blob.ct))
  return JSON.parse(dec.decode(pt))
}
