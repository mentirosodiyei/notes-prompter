export class MasterError extends Error {
  constructor(message, status = 0) {
    super(message)
    this.status = status
  }
}

export function masterUrl(host, port) {
  const address = String(host || '').trim()
  if (!address || /[\s/@?#]/.test(address) || address.includes('://')) {
    throw new MasterError('Indica solo la IP o el nombre del master, sin http:// ni ruta.')
  }
  const portNumber = Number(port)
  if (!Number.isInteger(portNumber) || portNumber < 1 || portNumber > 65535) {
    throw new MasterError('Puerto no válido.')
  }
  const hostname = address.includes(':') && !address.startsWith('[') ? `[${address}]` : address
  try {
    return new URL(`http://${hostname}:${portNumber}`).origin
  } catch {
    throw new MasterError('IP o nombre del master no válido.')
  }
}

export function scopeOf(state) {
  const slide = state?.slide
  if (!slide?.presentation || !Number.isInteger(slide.index) || slide.index < 1) return null
  return { source: state.source, presentation: slide.presentation, index: slide.index }
}

function sameScope(a, b) {
  return a && b && a.source === b.source && a.presentation === b.presentation && a.index === b.index
}

export function sourceChoices(state) {
  return (state?.sources || []).map((source) => ({
    id: source.id,
    label: `${source.name || source.label || source.id}${source.kind === 'local' ? ' (local)' : ''}${source.presentation ? ` · ${source.presentation}` : ''} [${source.id}]`,
  }))
}

export class MasterClient {
  constructor({ host, port = 8765, timeout = 2500, onState = () => {}, onConnection = () => {} }) {
    this.base = masterUrl(host, port)
    this.timeout = timeout
    this.onState = onState
    this.onConnection = onConnection
    this.state = null
    this.connected = false
    this.closed = false
    this.tail = Promise.resolve()
    this.pending = 0
    this.requests = new Set()
  }

  close() {
    this.closed = true
    for (const request of this.requests) request.abort()
    this.requests.clear()
  }

  // All reads and writes share a queue: rapid knob turns never overwrite one
  // another with a value read before the preceding adjustment was applied.
  enqueue(operation) {
    if (this.pending >= 64) return Promise.reject(new MasterError('Demasiados giros pendientes. Espera a que responda el master.'))
    this.pending++
    const result = this.tail.then(() => {
      if (this.closed) throw new MasterError('Conexión cerrada.')
      return operation()
    })
    this.tail = result.catch(() => {}).finally(() => { this.pending-- })
    return result
  }

  async request(path, method = 'GET', body) {
    if (this.closed) throw new MasterError('Conexión cerrada.')
    const controller = new AbortController()
    this.requests.add(controller)
    const timer = setTimeout(() => controller.abort(), this.timeout)
    try {
      const response = await fetch(`${this.base}${path}`, {
        method,
        redirect: 'error',
        signal: controller.signal,
        headers: body === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json' },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
      const data = await response.json()
      if (!response.ok) {
        throw new MasterError(typeof data.detail === 'string' ? data.detail : `El master devuelve HTTP ${response.status}.`, response.status)
      }
      return data
    } catch (error) {
      if (error instanceof MasterError) throw error
      this.connected = false
      if (!this.closed) this.onConnection(false, 'No se puede conectar con el master. Revisa IP, puerto y que esté iniciado.')
      throw new MasterError('No se puede conectar con el master. Revisa IP, puerto y que esté iniciado.')
    } finally {
      clearTimeout(timer)
      this.requests.delete(controller)
    }
  }

  accept(state) {
    if (!state?.slide || !Array.isArray(state.sources) || !state.effective_display_settings || typeof state.source !== 'string') {
      this.connected = false
      this.onConnection(false, 'Esta API requiere Notes Prompter 0.4.0 o posterior.')
      throw new MasterError('Esta API requiere Notes Prompter 0.4.0 o posterior.')
    }
    if (this.closed) throw new MasterError('Conexión cerrada.')
    this.state = state
    this.connected = true
    this.onState(state)
    this.onConnection(true, '')
    return state
  }

  async read() {
    try {
      return this.accept(await this.request('/api/admin/state'))
    } catch (error) {
      this.connected = false
      if (!this.closed) this.onConnection(false, error.message)
      throw error
    }
  }

  refresh() { return this.enqueue(() => this.read()) }

  selectSource(source) {
    return this.enqueue(async () => {
      const state = await this.read()
      if (!state.source_enabled) throw new MasterError('Inicia el receptor en modo Escuchar para seleccionar fuentes.')
      if (!state.sources.some((item) => item.id === source)) throw new MasterError('La fuente ya no está disponible en el master.')
      return this.accept(await this.request('/api/admin/source', 'POST', { source }))
    })
  }

  cycleSource(direction) {
    return this.enqueue(async () => {
      const state = await this.read()
      if (!state.source_enabled || !state.sources.length) throw new MasterError('El receptor no tiene fuentes seleccionables. Inicia el modo Escuchar y espera a los agentes.')
      const current = state.sources.findIndex((item) => item.id === state.source)
      const index = current < 0 ? (direction > 0 ? 0 : state.sources.length - 1)
        : (current + direction + state.sources.length) % state.sources.length
      return this.accept(await this.request('/api/admin/source', 'POST', { source: state.sources[index].id }))
    })
  }

  withSlide(operation) {
    // Capture what was visible at the time of the press, not when a queued
    // request eventually runs. Never retry an adjustment on a different slide.
    const expected = scopeOf(this.state)
    if (!expected) return Promise.reject(new MasterError('No hay una diapositiva activa.'))
    return this.enqueue(async () => {
      const state = await this.read()
      if (!sameScope(expected, scopeOf(state))) throw new MasterError('Ha cambiado la diapositiva o la fuente. Repite el ajuste en la actual.', 409)
      return operation(state, expected)
    })
  }

  adjust(field, delta) {
    const bounds = field === 'min_font_px' ? [24, 120] : field === 'speed_px_s' ? [1, 200] : null
    if (!bounds || !Number.isFinite(delta) || (field === 'min_font_px' && !Number.isInteger(delta))) {
      return Promise.reject(new MasterError('Incremento no válido.'))
    }
    return this.withSlide(async (state, scope) => {
      if (field === 'min_font_px' && Number.isInteger(state.font_size_limits?.max) &&
          state.font_size_limits.max >= 120 && state.font_size_limits.max <= 600) {
        bounds[1] = state.font_size_limits.max
      }
      if (field === 'speed_px_s' && state.speed_limits?.min === -200 && state.speed_limits?.max === 200) {
        bounds[0] = -200
      }
      const value = Number(state.effective_display_settings[field])
      if (!Number.isFinite(value)) throw new MasterError('El master no devuelve un ajuste válido.')
      const next = Math.round(Math.min(bounds[1], Math.max(bounds[0], value + delta)) * 1000) / 1000
      const patch = { ...scope, [field]: next }
      // The font must be fixed for an explicit knob size to be visible even on
      // short notes; auto-fit otherwise grows past the requested size.
      if (field === 'min_font_px') patch.font_mode = 'fixed'
      return this.accept(await this.request('/api/admin/live-settings', 'PUT', patch))
    })
  }

  toggleScroll() {
    return this.withSlide(async (state, scope) => this.accept(await this.request('/api/admin/live-settings', 'PUT', {
      ...scope, auto_scroll: !state.effective_display_settings.auto_scroll,
    })))
  }

  liveCommand(command) {
    if (!['save', 'reset'].includes(command)) return Promise.reject(new MasterError('Acción desconocida.'))
    return this.withSlide(async (_, scope) => this.accept(await this.request(`/api/admin/live-settings/${command}`, 'POST', scope)))
  }
}
