import { combineRgb } from '@companion-module/base'
import { sourceChoices } from './client.js'

const white = combineRgb(255, 255, 255)
const blue = combineRgb(20, 52, 90)
const green = combineRgb(20, 120, 55)
const orange = combineRgb(155, 70, 0)

export const variableDefinitions = Object.fromEntries(Object.entries({
  connected: 'Conexión con el master (1/0)',
  master: 'Nombre del master',
  source: 'Nombre de la fuente activa',
  source_id: 'Identificador de la fuente activa',
  sources_count: 'Número de fuentes detectadas por el master',
  presentation: 'PowerPoint actual',
  slide: 'Diapositiva actual',
  total: 'Total de diapositivas',
  font: 'Tamaño de letra (px)',
  font_mode: 'Modo de letra (fixed/auto)',
  speed: 'Velocidad (px/s)',
  auto_scroll: 'Desplazamiento automático (1/0)',
  live: 'Ajuste temporal activo (1/0)',
  last_error: 'Último error de una acción',
}).map(([id, name]) => [id, { name }]))

function sourceOption(instance) {
  const choices = sourceChoices(instance.client?.state)
  return {
    type: 'dropdown', id: 'source', label: 'Fuente detectada por el master',
    choices: choices.length ? choices : [{ id: '', label: 'Conecta con el master para ver las fuentes' }],
    default: choices[0]?.id || '',
  }
}

export function actionDefinitions(instance) {
  const actions = {
    select_source: {
      name: 'Fuente: seleccionar', options: [sourceOption(instance)],
      callback: (event) => instance.perform(() => instance.client.selectSource(String(event.options.source))),
    },
    source_next: {
      name: 'Fuente: siguiente', options: [],
      callback: () => instance.perform(() => instance.client.cycleSource(1)),
    },
    source_previous: {
      name: 'Fuente: anterior', options: [],
      callback: () => instance.perform(() => instance.client.cycleSource(-1)),
    },
    refresh: {
      name: 'Estado: actualizar fuentes y valores', options: [],
      callback: () => instance.perform(() => instance.client.refresh()),
    },
    scroll_toggle: {
      name: 'Lectura: activar/desactivar desplazamiento automático', options: [],
      callback: () => instance.perform(() => instance.client.toggleScroll()),
    },
    live_save: {
      name: 'Diapositiva: guardar ajustes actuales en su preset', options: [],
      description: 'Guarda solo la diapositiva actual. Requiere un preset vinculado al PowerPoint y activo en el master.',
      callback: () => instance.perform(() => instance.client.liveCommand('save')),
    },
    live_reset: {
      name: 'Diapositiva: recuperar ajustes del preset', options: [],
      callback: () => instance.perform(() => instance.client.liveCommand('reset')),
    },
  }
  for (const [prefix, field, title, unit, max] of [
    ['font', 'min_font_px', 'Letra', 'px', 96],
    ['speed', 'speed_px_s', 'Velocidad', 'px/s', 199],
  ]) {
    for (const [suffix, sign, verb] of [['increase', 1, 'aumentar'], ['decrease', -1, 'reducir']]) {
      actions[`${prefix}_${suffix}`] = {
        name: `${title}: ${verb} X ${unit}`,
        description: 'Sirve tanto para pulsación como para giro. X=0 usa el paso general de esta conexión.',
        options: [{ type: 'number', id: 'step', label: `Paso X (${unit}); 0 = paso de la conexión`,
          default: 0, min: 0, max, step: prefix === 'font' ? 1 : 0.1, range: false }],
        callback: (event) => instance.perform(() => {
          const requested = Number(event.options.step)
          const step = requested === 0 ? instance.config[`${prefix}_step`] : requested
          if (!Number.isFinite(step) || step <= 0 || step > max || (prefix === 'font' && !Number.isInteger(step))) {
            throw new Error('El paso X no es válido.')
          }
          return instance.client.adjust(field, sign * step)
        }),
      }
    }
  }
  return actions
}

export function feedbackDefinitions(instance) {
  const feedback = (name, callback, options = [], bgcolor = green) => ({
    type: 'boolean', name, options, defaultStyle: { color: white, bgcolor }, callback,
  })
  return {
    connected: feedback('Master conectado', () => !!instance.client?.connected),
    source_selected: feedback('Fuente seleccionada', (event) => !!instance.client?.connected && instance.client.state?.source === event.options.source, [sourceOption(instance)]),
    auto_scroll: feedback('Desplazamiento automático activado', () => !!instance.client?.connected && !!instance.client.state?.effective_display_settings.auto_scroll),
    live: feedback('Ajustes temporales en esta diapositiva', () => !!instance.client?.connected && !!instance.client.state?.live_adjustment, [], orange),
  }
}

export function presetDefinitions(instance) {
  const presets = {}
  const action = (actionId, options = {}) => ({ actionId, options })
  const value = (name) => `$(${instance.label}:${name})`
  const button = (id, name, text, down = [], feedbacks = [], extra = {}) => {
    presets[id] = {
      type: 'simple', name,
      style: { text, size: 'auto', color: white, bgcolor: blue },
      steps: [{ down, up: [], ...extra }], feedbacks,
    }
  }
  const highlight = (feedbackId, options = {}, bgcolor = green) => ({ feedbackId, options, style: { color: white, bgcolor } })
  for (const [prefix, title, variable, unit] of [['font', 'LETRA', 'font', 'px'], ['speed', 'VELOC.', 'speed', 'px/s']]) {
    button(`${prefix}_plus`, `${title} +X`, `${title} +\n${value(variable)} ${unit}`, [action(`${prefix}_increase`, { step: 0 })])
    button(`${prefix}_minus`, `${title} −X`, `${title} −\n${value(variable)} ${unit}`, [action(`${prefix}_decrease`, { step: 0 })])
    button(`${prefix}_knob`, `Knob: ${title}`, `${title}\n${value(variable)} ${unit}\n← − / + →`, [], [], {
      rotate_left: [action(`${prefix}_decrease`, { step: 0 })],
      rotate_right: [action(`${prefix}_increase`, { step: 0 })],
    })
  }
  button('source_previous', 'Fuente anterior', 'FUENTE\n← anterior', [action('source_previous')])
  button('source_next', 'Fuente siguiente', 'FUENTE\nsiguiente →', [action('source_next')])
  button('status', 'Estado del master', `${value('source')}\n${value('presentation')}\n${value('slide')}/${value('total')}`, [action('refresh')], [highlight('connected')])
  button('scroll', 'Desplazamiento automático', 'AUTO\nSCROLL', [action('scroll_toggle')], [highlight('auto_scroll')])
  button('save', 'Guardar esta diapositiva', 'GUARDAR\nSLIDE', [action('live_save')], [highlight('live', {}, orange)])
  button('reset', 'Recuperar ajustes del preset', 'RECUPERAR\nPRESET', [action('live_reset')])
  const sources = sourceChoices(instance.client?.state)
  for (const source of sources) {
    const detail = instance.client.state.sources.find((item) => item.id === source.id)
    const text = `${detail.name || detail.label || source.id}\n${detail.presentation || (detail.kind === 'local' ? 'PowerPoint local' : 'Sin presentación')}`
    button(`source_${source.id}`, `Seleccionar: ${source.label}`, text,
      [action('select_source', { source: source.id })], [highlight('source_selected', { source: source.id })])
  }
  return {
    structure: [
      { id: 'buttons', name: 'Letra y velocidad · botones', definitions: ['font_plus', 'font_minus', 'speed_plus', 'speed_minus'] },
      { id: 'knobs', name: 'Letra y velocidad · knobs', definitions: ['font_knob', 'speed_knob'] },
      { id: 'sources', name: 'Fuentes detectadas por el master', definitions: [...sources.map((source) => `source_${source.id}`), 'source_previous', 'source_next', 'status'] },
      { id: 'reading', name: 'Lectura y ajustes por diapositiva', definitions: ['scroll', 'save', 'reset'] },
    ],
    presets,
  }
}
