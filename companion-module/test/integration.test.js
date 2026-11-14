import { test } from 'node:test'
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { MasterClient } from '../src/client.js'

const here = path.dirname(fileURLToPath(import.meta.url))
const project = process.env.NP_PROJECT || path.resolve(here, '../..')
const python = process.env.NP_PYTHON || path.join(project, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python')

async function until(operation, predicate, timeout = 4000) {
  const start = Date.now()
  while (Date.now() - start < timeout) {
    const value = await operation()
    if (predicate(value)) return value
    await new Promise((resolve) => setTimeout(resolve, 25))
  }
  throw new Error('Tiempo agotado esperando al master de prueba.')
}

test('real Notes Prompter 0.5 API: local/remote source, live settings, wire output, save/reset and slide changes', {
  skip: !existsSync(python) || !existsSync(path.join(project, 'notes_prompter/server.py')),
  timeout: 15000,
}, async (t) => {
  const temp = await mkdtemp(path.join(tmpdir(), 'notes-prompter-companion-test-'))
  const settingsPath = path.join(temp, 'settings.json')
  const child = spawn(python, [path.join(here, 'master_fixture.py'), project, settingsPath], { stdio: ['ignore', 'pipe', 'pipe'] })
  let stderr = ''
  child.stderr.on('data', (data) => { stderr += data.toString() })
  t.after(async () => {
    if (child.exitCode === null) { child.kill('SIGTERM'); await once(child, 'exit') }
    await rm(temp, { recursive: true, force: true })
  })
  const ports = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`No arranca la API: ${stderr}`)), 6000)
    let output = ''
    child.stdout.on('data', (data) => {
      output += data.toString()
      if (output.includes('\n')) {
        clearTimeout(timer)
        try { resolve(JSON.parse(output.split('\n')[0])) } catch (error) { reject(error) }
      }
    })
    child.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Fixture terminada (${code}): ${stderr}`)) })
    child.once('error', (error) => { clearTimeout(timer); reject(error) })
  })
  const client = new MasterClient({ host: '127.0.0.1', port: ports.master_port })
  t.after(() => client.close())
  await until(() => client.refresh(), (state) => state.slide.index === 1)
  assert.ok(Number(client.state.version.split('.')[1]) >= 4)
  assert.equal(client.state.sources.length, 2)
  const firstSource = `127.0.0.1:${ports.first_agent_port}`
  assert.equal(client.state.source, firstSource)
  assert.equal(client.state.slide.total, 3)
  const wrongTarget = new MasterClient({ host: '127.0.0.1', port: ports.first_agent_port })
  await assert.rejects(wrongTarget.refresh(), /Escuchar|Escoltar|Listen/)
  wrongTarget.close()

  // Observe real output messages sent by the unmodified master.
  const messages = []
  const ws = new WebSocket(`ws://127.0.0.1:${ports.master_port}/ws`)
  ws.addEventListener('message', (event) => messages.push(JSON.parse(event.data)))
  t.after(() => ws.close())
  await once(ws, 'open')
  ws.send(JSON.stringify({ type: 'hello', role: 'display' }))
  await client.adjust('min_font_px', 4)
  await client.adjust('speed_px_s', -3.5)
  await until(async () => messages, (items) => items.some((message) => message.type === 'display_settings' && message.min_font_px === 52 && message.speed_px_s === 20.5 && message.live))
  assert.equal(client.state.effective_display_settings.font_mode, 'fixed')
  assert.equal(client.state.live_adjustment, true)

  await client.liveCommand('save')
  const saved = JSON.parse(await readFile(settingsPath, 'utf8'))
  assert.equal(saved.presets[0].rules['1'].min_font_px, 52)
  assert.equal(saved.presets[0].rules['1'].speed_px_s, 20.5)
  await client.adjust('speed_px_s', 4)
  await client.liveCommand('reset')
  assert.equal(client.state.effective_display_settings.speed_px_s, 20.5)
  assert.equal(client.state.live_adjustment, false)

  await fetch(`${client.base}/_fixture/slide/2`, { method: 'PUT' })
  await until(() => client.refresh(), (state) => state.slide.index === 2)
  assert.equal(client.state.effective_display_settings.speed_px_s, 24)
  assert.equal(client.state.effective_display_settings.min_font_px, 48)

  const remoteSource = `127.0.0.1:${ports.remote_port}`
  await client.selectSource(remoteSource)
  await until(() => client.refresh(), (state) => state.slide.presentation === 'Ensayo remoto')
  assert.equal(client.state.source, remoteSource)
  await client.adjust('speed_px_s', 7)
  assert.equal(client.state.effective_display_settings.speed_px_s, 31)
  await assert.rejects(client.liveCommand('save'), /preset|preconfiguració/i)
  await fetch(`${client.base}/_fixture/peers/0`, { method: 'PUT' })
  await client.refresh()
  assert.equal(client.state.sources.length, 1)
  await client.selectSource(firstSource)
  await until(() => client.refresh(), (state) => state.slide.presentation === 'Ensayo local')
  assert.equal(client.state.effective_display_settings.speed_px_s, 24)
  assert.equal(client.state.live_adjustment, false)
})
