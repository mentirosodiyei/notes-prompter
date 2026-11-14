import { afterEach, test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { MasterClient, masterUrl, sourceChoices } from '../src/client.js'

const cleanups = []
afterEach(async () => { while (cleanups.length) await cleanups.pop()() })

async function fixture(options = {}) {
  let state = {
    source: 'local', source_enabled: true, computer: 'Master de prueba',
    sources: [{ id: 'local', name: 'Master', kind: 'local', presentation: 'Charla' },
      { id: '192.0.2.5:8765', name: 'PC escenario', kind: 'remote', presentation: 'Ponencia' }],
    slide: { presentation: 'Charla', index: 1, total: 3 },
    effective_display_settings: { min_font_px: 48, font_mode: 'auto', speed_px_s: 24, auto_scroll: true },
    live_adjustment: false,
  }
  const writes = []
  let beforeWrite = null
  const server = createServer(async (req, res) => {
    const reply = (code, data) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(data)) }
    if (req.method === 'GET') {
      if (options.delay) await new Promise((resolve) => setTimeout(resolve, options.delay))
      reply(200, state)
      return
    }
    let raw = ''
    for await (const chunk of req) raw += chunk
    const body = JSON.parse(raw)
    writes.push({ path: req.url, body })
    if (beforeWrite) beforeWrite()
    if (req.url === '/api/admin/source') {
      state.source = body.source
      reply(200, state)
      return
    }
    if (body.source !== state.source || body.presentation !== state.slide.presentation || body.index !== state.slide.index) {
      reply(409, { detail: 'La diapositiva ha cambiado.' })
      return
    }
    if (req.url.endsWith('/save') && options.saveError) { reply(409, { detail: 'Vincula un preset.' }); return }
    for (const key of ['min_font_px', 'font_mode', 'speed_px_s', 'auto_scroll']) {
      if (key in body) state.effective_display_settings[key] = body[key]
    }
    state.live_adjustment = !req.url.endsWith('/reset')
    reply(200, state)
  })
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  const client = new MasterClient({ host: '127.0.0.1', port: server.address().port, timeout: options.timeout || 1000 })
  cleanups.push(async () => { client.close(); server.closeAllConnections(); await new Promise((resolve) => server.close(resolve)) })
  await client.refresh()
  return { client, writes, state, mutateBeforeWrite: (fn) => { beforeWrite = fn }, setState: (next) => { state = next } }
}

test('IP/hostname and IPv6 work; invalid host or port rejected', () => {
  assert.equal(masterUrl('127.0.0.1', 8765), 'http://127.0.0.1:8765')
  assert.equal(masterUrl('master.local', 8765), 'http://master.local:8765')
  assert.equal(masterUrl('::1', 8765), 'http://[::1]:8765')
  for (const host of ['', 'http://localhost', 'host/path', 'user@host', 'host?x']) assert.throws(() => masterUrl(host, 8765))
  for (const port of [0, 65536, 1.5]) assert.throws(() => masterUrl('localhost', port))
})

test('dynamic source list includes stable identifiers, name and PPT', async () => {
  const { client } = await fixture()
  assert.match(sourceChoices(client.state)[1].label, /PC escenario.*Ponencia.*192\.0\.2\.5/)
  await client.selectSource('192.0.2.5:8765')
  assert.equal(client.state.source, '192.0.2.5:8765')
  await client.cycleSource(1)
  assert.equal(client.state.source, 'local')
  await client.cycleSource(-1)
  assert.equal(client.state.source, '192.0.2.5:8765')
})

test('missing source and disabled source selection never write', async () => {
  const { client, state, writes } = await fixture()
  await assert.rejects(client.selectSource('gone'), /disponible/)
  state.source_enabled = false
  await assert.rejects(client.selectSource('local'), /Escuchar/)
  assert.equal(writes.length, 0)
})

test('rapid simultaneous knob turns accumulate without losing increments', async () => {
  const { client, writes } = await fixture()
  await Promise.all(Array.from({ length: 20 }, () => client.adjust('min_font_px', 2)))
  assert.equal(client.state.effective_display_settings.min_font_px, 88)
  assert.equal(writes.length, 20)
  assert.equal(writes[0].body.font_mode, 'fixed')
  assert.equal(writes[19].body.min_font_px, 88)
  assert.ok(writes.every((write) => write.path === '/api/admin/live-settings'))
})

test('font and speed in mixed burst preserve both; fractional speed supported', async () => {
  const { client } = await fixture()
  await Promise.all([client.adjust('min_font_px', -3), client.adjust('speed_px_s', 0.5), client.adjust('speed_px_s', -2)])
  assert.equal(client.state.effective_display_settings.min_font_px, 45)
  assert.equal(client.state.effective_display_settings.speed_px_s, 22.5)
})

test('clamps respect master font and speed limits in both directions', async () => {
  const { client } = await fixture()
  await client.adjust('min_font_px', 500)
  assert.equal(client.state.effective_display_settings.min_font_px, 120)
  await client.adjust('min_font_px', -500)
  assert.equal(client.state.effective_display_settings.min_font_px, 24)
  await client.adjust('speed_px_s', 500)
  assert.equal(client.state.effective_display_settings.speed_px_s, 200)
  await client.adjust('speed_px_s', -500)
  assert.equal(client.state.effective_display_settings.speed_px_s, 1)
})

test('invalid or fractional font increment never writes', async () => {
  const { client, writes } = await fixture()
  await assert.rejects(client.adjust('min_font_px', 1.5), /válido/)
  await assert.rejects(client.adjust('speed_px_s', NaN), /válido/)
  assert.equal(writes.length, 0)
})

test('slide changed before queued adjustment: no adjustment is sent', async () => {
  const { client, state, writes } = await fixture()
  state.slide.index = 2
  await assert.rejects(client.adjust('speed_px_s', 2), /cambiado/)
  assert.equal(writes.length, 0)
})

test('source changed before queued adjustment: no adjustment is sent', async () => {
  const { client, state, writes } = await fixture()
  state.source = 'another'
  await assert.rejects(client.adjust('speed_px_s', 2), /cambiado/)
  assert.equal(writes.length, 0)
})

test('master 409 between GET and PUT is surfaced and never retried', async () => {
  const { client, state, writes, mutateBeforeWrite } = await fixture()
  mutateBeforeWrite(() => { state.slide.index = 2 })
  await assert.rejects(client.adjust('speed_px_s', 2), { status: 409 })
  assert.equal(writes.length, 1)
  assert.equal(state.effective_display_settings.speed_px_s, 24)
})

test('no active slide rejects controls; reset and save require original scope', async () => {
  const { client, writes, state } = await fixture()
  await client.toggleScroll()
  assert.equal(client.state.effective_display_settings.auto_scroll, false)
  await client.liveCommand('save')
  assert.equal(writes.at(-1).path, '/api/admin/live-settings/save')
  await client.liveCommand('reset')
  assert.equal(client.state.live_adjustment, false)
  state.slide.index = 0
  await client.refresh()
  await assert.rejects(client.adjust('speed_px_s', 2), /diapositiva activa/)
})

test('save without bound preset preserves error detail and never retries', async () => {
  const { client, writes } = await fixture({ saveError: true })
  await assert.rejects(client.liveCommand('save'), /Vincula un preset/)
  assert.equal(writes.length, 1)
})

test('rejects legacy master without live controls', async () => {
  const { client, setState } = await fixture()
  setState({ slide: {}, source: 'local', sources: [] })
  await assert.rejects(client.refresh(), /0.4.0/)
  assert.equal(client.connected, false)
})

test('timeout, close and reconnect; no actions after disposal', async () => {
  const { client } = await fixture({ delay: 40 })
  client.timeout = 5
  await assert.rejects(client.refresh(), /conectar/)
  assert.equal(client.connected, false)
  client.timeout = 1000
  await client.refresh()
  assert.equal(client.connected, true)
  client.close()
  await assert.rejects(client.refresh(), /cerrada/)
})


test('new receiver font range is used without reducing large fonts to 120', async () => {
  const { client, state } = await fixture()
  state.font_size_limits = { min: 24, max: 600 }
  state.effective_display_settings.min_font_px = 300
  await client.adjust('min_font_px', 2)
  assert.equal(client.state.effective_display_settings.min_font_px, 302)
  await client.adjust('min_font_px', 500)
  assert.equal(client.state.effective_display_settings.min_font_px, 600)
  await client.adjust('min_font_px', -2)
  assert.equal(client.state.effective_display_settings.min_font_px, 598)
})


test('new receiver supports reverse and zero speed while legacy keeps positive limits', async () => {
  const { client, state } = await fixture()
  state.speed_limits = { min: -200, max: 200 }
  state.effective_display_settings.speed_px_s = 1
  await client.adjust('speed_px_s', -1)
  assert.equal(client.state.effective_display_settings.speed_px_s, 0)
  await client.adjust('speed_px_s', -2)
  assert.equal(client.state.effective_display_settings.speed_px_s, -2)
  await client.adjust('speed_px_s', -500)
  assert.equal(client.state.effective_display_settings.speed_px_s, -200)
  await client.adjust('speed_px_s', 500)
  assert.equal(client.state.effective_display_settings.speed_px_s, 200)
})
