// Optional acceptance test: use the actual loader shipped with Companion 5.1.1,
// in a separate child and temporary IPC socket. No running Companion config is used.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { existsSync } from 'node:fs'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { createServer as netServer } from 'node:net'
import { createServer as httpServer } from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const resources = process.env.COMPANION_RESOURCES || '/Applications/Companion.app/Contents/Resources'
const runtime = path.join(resources, 'node-runtimes/node22/bin/node')
const loader = path.join(resources, 'ConnectionThread.js')
const packaged = path.join(root, 'pkg/notesprompter-master')

test('packaged module loads and executes in the real Companion 5.1.1 connection runtime', {
  skip: !existsSync(runtime) || !existsSync(loader) || !existsSync(path.join(packaged, 'main.js')),
  timeout: 12000,
}, async (t) => {
  const temp = await mkdtemp(path.join(tmpdir(), 'np-companion-ipc-'))
  const socketPath = path.join(temp, 'runtime.sock')
  const received = []
  const pending = new Map()
  let socket
  let callId = 1000
  let output = ''
  const send = (message) => {
    const body = Buffer.from(JSON.stringify(message))
    const length = Buffer.alloc(4)
    length.writeUInt32BE(body.length)
    socket.write(Buffer.concat([length, body]))
  }
  const server = netServer((connection) => {
    socket = connection
    let buffered = Buffer.alloc(0)
    socket.on('data', (chunk) => {
      buffered = Buffer.concat([buffered, chunk])
      while (buffered.length >= 4) {
        const length = buffered.readUInt32BE(0)
        if (buffered.length < length + 4) break
        const message = JSON.parse(buffered.subarray(4, 4 + length).toString())
        buffered = buffered.subarray(4 + length)
        received.push(message)
        if (message.direction === 'response') {
          const handler = pending.get(message.callbackId)
          pending.delete(message.callbackId)
          if (handler) {
            clearTimeout(handler.timer)
            message.success ? handler.resolve(message.payload) : handler.reject(new Error(JSON.stringify(message.payload)))
          }
        } else if (message.name === 'register') {
          send({ direction: 'response', callbackId: message.callbackId, success: true,
            payload: { connectionId: 'np-runtime-test', moduleApiVersion: '2.1.3' } })
        } else if (message.callbackId) {
          send({ direction: 'response', callbackId: message.callbackId, success: true, payload: {} })
        }
      }
    })
  })
  await new Promise((resolve) => server.listen(socketPath, resolve))
  const state = {
    computer: 'Synthetic master', source: 'local', source_enabled: true,
    sources: [{ id: 'local', name: 'Synthetic master', kind: 'local' }],
    slide: { presentation: 'Test', index: 1, total: 3 }, live_adjustment: false,
    effective_display_settings: { min_font_px: 48, speed_px_s: 24, font_mode: 'auto', auto_scroll: true },
  }
  const api = httpServer(async (req, res) => {
    if (req.method !== 'GET') {
      let raw = ''
      for await (const chunk of req) raw += chunk
      const body = JSON.parse(raw)
      for (const key of ['min_font_px', 'font_mode', 'speed_px_s']) if (key in body) state.effective_display_settings[key] = body[key]
      state.live_adjustment = true
    }
    res.setHeader('Content-Type', 'application/json')
    res.end(JSON.stringify(state))
  })
  await new Promise((resolve) => api.listen(0, '127.0.0.1', resolve))
  const child = spawn(runtime, [loader], {
    cwd: resources,
    env: { ...process.env, MODULE_ENTRYPOINT: path.join(packaged, 'main.js'),
      MODULE_MANIFEST: path.join(packaged, 'companion/manifest.json'),
      MODULE_DATA_CHANNEL: socketPath, VERIFICATION_TOKEN: 'isolated-local-test' },
    stdio: ['ignore', 'pipe', 'pipe', 'ipc'],
  })
  child.stdout.on('data', (data) => { output += data.toString() })
  child.stderr.on('data', (data) => { output += data.toString() })
  t.after(async () => {
    for (const handler of pending.values()) clearTimeout(handler.timer)
    if (child.exitCode === null) { child.kill('SIGTERM'); await once(child, 'exit') }
    socket?.destroy()
    api.closeAllConnections()
    await Promise.all([new Promise((resolve) => server.close(resolve)), new Promise((resolve) => api.close(resolve))])
    await rm(temp, { recursive: true, force: true })
  })
  const waitFor = async (predicate) => {
    const start = Date.now()
    while (Date.now() - start < 5000) {
      const found = received.find(predicate)
      if (found) return found
      if (child.exitCode !== null) throw new Error(`Runtime exited: ${output}`)
      await new Promise((resolve) => setTimeout(resolve, 20))
    }
    throw new Error(`Runtime timeout: ${output}\n${JSON.stringify(received.filter((item) => item.name === 'log-message'))}`)
  }
  const call = (name, payload) => new Promise((resolve, reject) => {
    const id = callId++
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`${name} timeout: ${output}`)) }, 5000)
    pending.set(id, { resolve, reject, timer })
    send({ direction: 'call', name, payload, callbackId: id })
  })
  await waitFor((message) => message.name === 'register')
  await call('init', { label: 'NP', isFirstInit: false, lastUpgradeIndex: -1, config: {
    host: '127.0.0.1', port: api.address().port, font_step: 4, speed_step: 2, poll_ms: 500,
  } })
  await waitFor((message) => message.name === 'set-status' && message.payload.status === 'ok')
  const actionMessage = await waitFor((message) => message.name === 'setActionDefinitions')
  assert.ok(actionMessage.payload.actions.font_increase)
  const presetsMessage = await waitFor((message) => message.name === 'setPresetDefinitions')
  assert.ok(presetsMessage.payload.presets)
  assert.match(JSON.stringify(presetsMessage.payload.presets), /rotate_right/)
  assert.match(JSON.stringify(presetsMessage.payload.presets), /"rotaryActions":true/)
  const config = await call('getConfigFields', {})
  assert.match(JSON.stringify(config.fields), /font_step/)
  const result = await call('executeAction', { action: {
    id: 'font-test', actionId: 'font_increase', controlId: 'button:1/0/0', options: { step: 0 },
  } })
  assert.equal(result.success, true)
  assert.equal(state.effective_display_settings.min_font_px, 52)
  assert.equal(state.effective_display_settings.font_mode, 'fixed')
  const speedResult = await call('executeAction', { action: {
    id: 'speed-test', actionId: 'speed_decrease', controlId: 'button:1/0/1', options: { step: 1.5 },
  } })
  assert.equal(speedResult.success, true)
  assert.equal(state.effective_display_settings.speed_px_s, 22.5)
  const failures = received.filter((message) => message.name === 'log-message' && ['error', 'warn'].includes(message.payload.level))
  assert.deepEqual(failures, [], JSON.stringify(failures))
  await call('destroy', {})
})
