import { InstanceBase, InstanceStatus } from '@companion-module/base'
import { MasterClient, sourceChoices } from './client.js'
import { actionDefinitions, feedbackDefinitions, presetDefinitions, variableDefinitions } from './definitions.js'

export const UpgradeScripts = []

export default class NotesPrompterInstance extends InstanceBase {
  async init(config) {
    this.setVariableDefinitions(variableDefinitions)
    this.setVariableValues({ connected: 0, last_error: '' })
    await this.configUpdated(config)
  }

  async destroy() {
    clearTimeout(this.pollTimer)
    this.client?.close()
    this.client = null
  }

  async configUpdated(config) {
    await this.destroy()
    this.config = {
      host: config.host || '127.0.0.1', port: Number(config.port ?? 8765),
      font_step: Number(config.font_step ?? 2), speed_step: Number(config.speed_step ?? 2),
      poll_ms: Number(config.poll_ms ?? 500),
    }
    this.sourcesSignature = null
    this.setVariableValues({ connected: 0, master: '', source: '', source_id: '', sources_count: 0,
      presentation: '', slide: 0, total: 0, font: '', speed: '', font_mode: '', auto_scroll: 0, live: 0, last_error: '' })
    this.updateStatus(InstanceStatus.Connecting)
    try {
      if (!Number.isInteger(this.config.font_step) || this.config.font_step < 1 || this.config.font_step > 96 ||
        !Number.isFinite(this.config.speed_step) || this.config.speed_step < 0.1 || this.config.speed_step > 199 ||
        !Number.isInteger(this.config.poll_ms) || this.config.poll_ms < 250 || this.config.poll_ms > 5000) {
        throw new Error('Revisa los pasos de letra/velocidad y el intervalo de actualización.')
      }
      const client = new MasterClient({
        ...this.config,
        onState: (state) => { if (this.client === client) this.stateUpdated(state) },
        onConnection: (connected, message) => {
          if (this.client !== client) return
          this.setVariableValues({ connected: connected ? 1 : 0 })
          this.updateStatus(connected ? InstanceStatus.Ok : InstanceStatus.ConnectionFailure, message)
          this.checkAllFeedbacks()
        },
      })
      this.client = client
      this.updateDefinitions()
      await this.poll(client)
    } catch (error) {
      this.updateDefinitions()
      this.updateStatus(InstanceStatus.BadConfig, error.message)
    }
  }

  getConfigFields() {
    return [
      { type: 'static-text', id: 'help', label: 'Master Notes Prompter', width: 12,
        value: 'Conecta con Notes Prompter 0.4.0 o posterior, iniciado en modo Escuchar en el receptor. Las fuentes son las que detecta ese master. Los ajustes en directo afectan a su salida y a sus receptores.' },
      { type: 'textinput', id: 'host', label: 'IP o nombre del master', default: '127.0.0.1', width: 8 },
      { type: 'number', id: 'port', label: 'Puerto', default: 8765, min: 1, max: 65535, width: 4 },
      { type: 'number', id: 'font_step', label: 'Paso de letra (px por pulsación/giro)', default: 2, min: 1, max: 96, step: 1, width: 6 },
      { type: 'number', id: 'speed_step', label: 'Paso de velocidad (px/s por pulsación/giro)', default: 2, min: 0.1, max: 199, step: 0.1, width: 6 },
      { type: 'number', id: 'poll_ms', label: 'Actualizar estado cada (ms)', default: 500, min: 250, max: 5000, step: 250, width: 6 },
    ]
  }

  updateDefinitions() {
    this.setActionDefinitions(actionDefinitions(this))
    this.setFeedbackDefinitions(feedbackDefinitions(this))
    const { structure, presets } = presetDefinitions(this)
    this.setPresetDefinitions(structure, presets)
  }

  stateUpdated(state) {
    const settings = state.effective_display_settings
    const current = state.sources.find((source) => source.id === state.source)
    this.setVariableValues({
      master: state.computer || '', source: current?.name || current?.label || state.source,
      source_id: state.source, sources_count: state.sources.length,
      presentation: state.slide.presentation || '', slide: state.slide.index, total: state.slide.total,
      font: settings.min_font_px, font_mode: settings.font_mode, speed: settings.speed_px_s,
      auto_scroll: settings.auto_scroll ? 1 : 0, live: state.live_adjustment ? 1 : 0,
    })
    const signature = JSON.stringify(sourceChoices(state))
    if (signature !== this.sourcesSignature) {
      this.sourcesSignature = signature
      this.updateDefinitions()
    }
    this.checkAllFeedbacks()
  }

  async poll(client) {
    if (this.client !== client) return
    try {
      // Skip a poll while knob/button operations are queued.
      if (!client.pending) await client.refresh()
    } catch (error) {
      if (this.client === client) {
        this.setVariableValues({ connected: 0 })
        this.updateStatus(InstanceStatus.ConnectionFailure, error.message)
        this.checkAllFeedbacks()
      }
    }
    if (this.client === client) this.pollTimer = setTimeout(() => this.poll(client), this.config.poll_ms)
  }

  async perform(operation) {
    const client = this.client
    try {
      if (!client) throw new Error('Configura primero la conexión con el master.')
      await operation()
      if (this.client === client) this.setVariableValues({ last_error: '' })
    } catch (error) {
      if (this.client === client) {
        this.setVariableValues({ last_error: error.message })
        this.log('warn', error.message)
      }
      throw error
    }
  }
}
