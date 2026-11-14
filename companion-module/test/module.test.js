import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import Module, { UpgradeScripts } from '../src/main.js'

export function hostContext() {
  const host = {
    _isInstanceContext: true, id: 'np-test', label: 'NP', upgradeScripts: [],
    sharedUdpSocketHandlers: new Map(), vars: {}, statuses: [],
    setActionDefinitions: (actions) => { host.actions = actions },
    setFeedbackDefinitions: (feedbacks) => { host.feedbacks = feedbacks },
    setPresetDefinitions: (structure, presets) => { host.structure = structure; host.presets = presets },
    setVariableDefinitions: (variables) => { host.variableDefinitions = variables },
    setVariableValues: (variables) => { Object.assign(host.vars, variables) },
    getVariableValue: (id) => host.vars[id],
    updateStatus: (status, message) => { host.statuses.push({ status, message }) },
    checkAllFeedbacks() {},
  }
  return host
}

test('module exposes Companion 5 API, knobs, buttons, dynamic presets and feedbacks', async (t) => {
  const state = {
    source: 'local', source_enabled: true, sources: [{ id: 'local', name: 'Mac escenario', kind: 'local' }],
    slide: { presentation: 'Charla', index: 2, total: 13 }, live_adjustment: false,
    effective_display_settings: { min_font_px: 48, speed_px_s: 24, font_mode: 'auto', auto_scroll: true },
  }
  const writes = []
  const server = createServer(async (req, res) => {
    if (req.method !== 'GET') {
      let raw = ''
      for await (const chunk of req) raw += chunk
      const body = JSON.parse(raw)
      writes.push(body)
      for (const field of ['min_font_px', 'speed_px_s', 'font_mode']) if (field in body) state.effective_display_settings[field] = body[field]
    }
    res.setHeader('Content-Type', 'application/json')
    res.end(JSON.stringify(state))
  })
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  const host = hostContext()
  const instance = new Module(host)
  t.after(async () => { await instance.destroy(); server.closeAllConnections(); await new Promise((resolve) => server.close(resolve)) })
  await instance.init({ host: '127.0.0.1', port: server.address().port, font_step: 4, speed_step: 1.5 })
  assert.equal(host.vars.connected, 1)
  assert.equal(host.vars.font, 48)
  assert.equal(host.vars.total, 13)
  assert.equal(host.statuses.at(-1).status, 'ok')
  assert.equal(Array.isArray(host.variableDefinitions), false)
  assert.equal(UpgradeScripts.length, 0)
  assert.equal(host.actions.select_source.options[0].choices[0].id, 'local')
  assert.equal(host.presets.font_knob.type, 'simple')
  assert.equal(host.presets.font_knob.steps[0].rotate_right[0].actionId, 'font_increase')
  assert.equal(host.presets.font_knob.steps[0].rotate_left[0].actionId, 'font_decrease')
  assert.equal(host.presets.font_knob.steps[0].down.length, 0)
  assert.equal(host.presets.font_plus.steps[0].down[0].actionId, 'font_increase')
  assert.ok(host.structure.find((section) => section.id === 'sources').definitions.includes('source_local'))
  assert.equal(host.feedbacks.source_selected.callback({ options: { source: 'local' } }), true)
  await host.actions.font_increase.callback({ options: { step: 0 } })
  assert.equal(host.vars.font, 52)
  await host.actions.font_decrease.callback({ options: { step: 3 } })
  assert.equal(host.vars.font, 49)
  await host.actions.speed_increase.callback({ options: { step: 0 } })
  assert.equal(host.vars.speed, 25.5)
  assert.equal(writes[0].font_mode, 'fixed')
  await assert.rejects(host.actions.font_increase.callback({ options: { step: -1 } }), /paso X/)
  assert.match(host.vars.last_error, /paso X/)
  state.sources.push({ id: '192.0.2.8:8765', name: 'PC nuevo', presentation: 'Otro PPT', kind: 'remote' })
  await host.actions.refresh.callback({ options: {} })
  assert.equal(host.vars.sources_count, 2)
  assert.ok(host.presets['source_192.0.2.8:8765'])
  state.sources.pop()
  await host.actions.refresh.callback({ options: {} })
  assert.equal(host.presets['source_192.0.2.8:8765'], undefined)
  await instance.configUpdated({ host: 'http://bad', port: 8765 })
  assert.equal(host.statuses.at(-1).status, 'bad_config')
  assert.equal(host.vars.connected, 0)
  assert.equal(host.feedbacks.connected.callback(), false)
})
