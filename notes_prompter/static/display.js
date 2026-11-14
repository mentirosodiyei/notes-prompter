(() => {
  "use strict";
  const tr = window.NPI18n.t;
  const MAX_PX = 600;
  const note = document.getElementById("note");
  const text = document.getElementById("text");
  const pager = document.getElementById("pager");
  const status = document.getElementById("status");
  let settings = {auto_scroll:true, font_mode:"auto", min_font_px:48, speed_px_s:24, start_delay_s:3};
  let pages = [""], pageIndex = 0, currentNotes = "", slideKey = null;
  let frame = null, lastFrame = null, holdUntil = 0, position = 0;
  let scrolling = false, paused = false, finished = false;
  let playbackScope = null, lastRestartId = null, activePlayback = null;
  const scopeKey = value => JSON.stringify([value.source, value.presentation, value.index]);

  function fits(value, px) {
    text.style.fontSize = px + "px";
    text.textContent = value;
    return text.offsetHeight <= note.clientHeight && text.scrollWidth <= note.clientWidth;
  }
  function bestSize(value) {
    if(settings.font_mode === "fixed") return settings.min_font_px;
    let lo = settings.min_font_px, hi = MAX_PX, best = lo;
    while (lo <= hi) {
      const mid = Math.floor((lo + hi) / 2);
      if (fits(value, mid)) {best = mid; lo = mid + 1;} else hi = mid - 1;
    }
    return best;
  }
  function paginate(value) {
    const tokens = value.split(/(\s+)/), result = [];
    let start = 0;
    while (start < tokens.length) {
      let lo = 1, hi = tokens.length - start, take = 1;
      while (lo <= hi) {
        const mid = Math.floor((lo + hi) / 2);
        if (fits(tokens.slice(start, start + mid).join("").trim(), settings.min_font_px)) {take = mid; lo = mid + 1;} else hi = mid - 1;
      }
      const page = tokens.slice(start, start + take).join("").trim();
      if (page) result.push(page);
      start += take;
    }
    return result.length ? result : [""];
  }
  function renderPage() {
    const value = pages[pageIndex];
    text.style.fontSize = bestSize(value) + "px";
    text.textContent = value;
    pager.hidden = pages.length <= 1;
    pager.textContent = tr("Página {0}/{1} ›", pageIndex + 1, pages.length);
  }
  function cancelFrame() {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null; lastFrame = null;
  }
  function updateMotion() {
    cancelFrame();
    if (!scrolling) return;
    const end = Math.max(0, note.scrollHeight-note.clientHeight);
    position = Math.max(0, Math.min(end, position));
    finished = (settings.speed_px_s > 0 && position >= end) || (settings.speed_px_s < 0 && position <= 0);
    if (!paused && !finished && settings.speed_px_s !== 0) frame = requestAnimationFrame(tick);
  }
  function tick(now) {
    frame = null;
    if (!scrolling || paused || finished) return;
    if (lastFrame !== null && now >= holdUntil) {
      const end = Math.max(0, note.scrollHeight-note.clientHeight);
      position = Math.max(0, Math.min(end, position + settings.speed_px_s * Math.min(0.1, (now-lastFrame)/1000)));
      note.scrollTop = position;
      if ((settings.speed_px_s > 0 && position >= end) || (settings.speed_px_s < 0 && position <= 0)) {
        finished = true; return;
      }
    }
    lastFrame = now;
    frame = requestAnimationFrame(tick);
  }
  function layout() {
    cancelFrame();
    scrolling = finished = false;
    paused = Boolean(activePlayback?.paused);
    position = 0;
    note.classList.remove("scrolling");
    note.scrollTop = 0;
    pager.hidden = true;
    if (settings.auto_scroll && currentNotes && !fits(currentNotes, settings.min_font_px)) {
      note.classList.add("scrolling");
      text.style.fontSize = settings.min_font_px + "px";
      text.textContent = currentNotes;
      // El contenedor ya vuelve a tener overflow: ahora sí puede volver al inicio.
      note.scrollTop = 0;
      position = 0;
      scrolling = true;
      holdUntil = performance.now() + settings.start_delay_s*1000;
      updateMotion();
    } else {
      pages = settings.auto_scroll ? [currentNotes] : paginate(currentNotes);
      pageIndex = 0; renderPage();
    }
  }
  function applySettings(value) {
    const {restart, live, playback, ...next} = value;
    const merged = {...settings, ...next};
    const structural = restart || ["auto_scroll", "min_font_px", "font_mode"].some(key => merged[key] !== settings[key]);
    const speedChanged = merged.speed_px_s !== settings.speed_px_s;
    const progress=note.scrollTop / Math.max(1,note.scrollHeight-note.clientHeight);
    const wasScrolling=scrolling, wasPaused=paused;
    settings = merged;
    if (structural) {
      layout();
      if(live && wasScrolling && scrolling) {
        position=progress*Math.max(0,note.scrollHeight-note.clientHeight);
        note.scrollTop=position;holdUntil=performance.now();
        paused=wasPaused;updateMotion();
      }
    } else if (speedChanged && scrolling) {
      // Direction changes resume from either end without resetting the note.
      position=note.scrollTop;
      if(live) holdUntil=performance.now();
      updateMotion();
    }
    if (playback) applyPlayback(playback);
  }
  function setSlide(message) {
    const value = message.notes || "";
    const nextScope = message.playback ? scopeKey(message.playback) : null;
    if (nextScope !== playbackScope) {playbackScope = nextScope; lastRestartId = null; activePlayback = null;}
    const key = JSON.stringify([nextScope, message.presentation, message.index, value]);
    if (key !== slideKey) {
      if (message.display_settings) settings = {...settings, ...message.display_settings};
      slideKey = key; currentNotes = value; layout();
    } else if (message.display_settings) applySettings(message.display_settings);
    if (message.playback) applyPlayback(message.playback);
  }
  function applyPlayback(value) {
    if (scopeKey(value) !== playbackScope) return;
    if (activePlayback && (value.revision ?? 0) < (activePlayback.revision ?? 0)) return;
    activePlayback = value;
    if (lastRestartId !== null && value.restart_id !== lastRestartId) layout();
    lastRestartId = value.restart_id;
    paused = value.paused;
    if (scrolling) {position = note.scrollTop; updateMotion();}
  }
  document.addEventListener("visibilitychange", () => {lastFrame = null;});
  pager.addEventListener("click", () => {pageIndex = (pageIndex + 1) % pages.length; renderPage();});
  window.addEventListener("resize", layout);

  let socket = null, attempt = 0;
  function setStatus(state, label) {status.dataset.state = state; status.textContent = label;}
  async function connect() {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    setStatus("connecting", tr("conectando…"));
    try {
      const response = await fetch("/api/display-settings", {cache:"no-store"});
      if (response.ok) applySettings(await response.json());
    } catch { /* Se conserva la última configuración si la red está caída. */ }
    socket = new WebSocket(`${scheme}://${location.host}/ws`);
    socket.onopen = () => {attempt = 0; setStatus("connected", tr("conectado")); socket.send(JSON.stringify({type:"hello", role:"display"}));};
    socket.onmessage = event => {
      let message;
      try {message = JSON.parse(event.data);} catch {return;}
      if (message.type === "display_settings") {
        const {type, ...value} = message; applySettings(value);
      } else if (message.type === "playback") {
        applyPlayback(message);
      } else if (message.type === "slide") {
        setSlide(message); setStatus("connected", message.total ? `${message.index}/${message.total}` : tr("sin presentación"));
      }
    };
    socket.onclose = () => {
      const delay = Math.min(5000, 500 * 2 ** attempt++);
      setStatus("disconnected", tr("sin conexión, reintentando en {0} s", Math.round(delay/1000)));
      setTimeout(connect, delay);
    };
    socket.onerror = () => socket.close();
  }
  layout(); connect();
})();
