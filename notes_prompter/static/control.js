// Control de operador: envía comandos y muestra el estado que recibe del emisor.
(() => {
  "use strict";
  const tr = window.NPI18n.t;

  const $ = (id) => document.getElementById(id);
  const list = $("presentations");
  const empty = $("empty");
  const position = $("position");
  const preview = $("preview");
  const errorBox = $("error");
  const status = $("status");
  const prevButton = $("prev");
  const nextButton = $("next");
  const gotoInput = $("goto-index");

  let socket = null;
  let attempt = 0;
  let slide = { presentation: null, index: 0, total: 0 };
  let items = [];
  let active = null;

  function send(message) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(message));
    } else {
      showError(tr("sin conexión con el emisor"));
    }
  }

  let errorTimer = null;
  function showError(text) {
    errorBox.textContent = text;
    clearTimeout(errorTimer);
    errorTimer = setTimeout(() => (errorBox.textContent = ""), 6000);
  }

  function renderPresentations() {
    list.replaceChildren();
    empty.hidden = items.length > 0;
    for (const name of items) {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = name;
      button.className = name === active ? "active" : "";
      button.addEventListener("click", () => send({ type: "select", presentation: name }));
      li.appendChild(button);
      list.appendChild(li);
    }
  }

  function renderSlide() {
    const hasDeck = slide.total > 0;
    position.textContent = hasDeck ? `${slide.index} / ${slide.total}` : "–";
    prevButton.disabled = !hasDeck || slide.index <= 1;
    nextButton.disabled = !hasDeck || slide.index >= slide.total;
    gotoInput.max = slide.total || 1;
    preview.textContent = slide.notes || "";
  }

  function onMessage(event) {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    if (msg.type === "slide") {
      slide = { presentation: msg.presentation, index: msg.index, total: msg.total, notes: msg.notes };
      renderSlide();
    } else if (msg.type === "presentations") {
      items = msg.items;
      active = msg.active;
      renderPresentations();
    } else if (msg.type === "error") {
      showError(msg.message);
    }
  }

  function connect() {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    status.dataset.state = "connecting";
    status.textContent = tr("conectando…");
    socket = new WebSocket(`${scheme}://${location.host}/ws`);

    socket.onopen = () => {
      attempt = 0;
      status.dataset.state = "connected";
      status.textContent = tr("conectado al emisor");
      socket.send(JSON.stringify({ type: "hello", role: "control" }));
    };
    socket.onmessage = onMessage;
    socket.onclose = () => {
      const delay = Math.min(5000, 500 * 2 ** attempt);
      attempt += 1;
      status.dataset.state = "disconnected";
      status.textContent = tr("sin conexión, reintentando en {0} s", Math.round(delay / 1000));
      setTimeout(connect, delay);
    };
    socket.onerror = () => socket.close();
  }

  $("prev").addEventListener("click", () => send({ type: "prev" }));
  $("next").addEventListener("click", () => send({ type: "next" }));

  $("goto-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const index = Number.parseInt(gotoInput.value, 10);
    if (Number.isNaN(index)) {
      showError(tr("escribe un número de diapositiva"));
      return;
    }
    send({ type: "goto", index });
  });

  $("load-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const path = $("path").value.trim();
    if (path) send({ type: "load", path });
  });

  document.addEventListener("keydown", (event) => {
    if (event.target instanceof HTMLInputElement) return;
    if (event.key === "ArrowRight") send({ type: "next" });
    if (event.key === "ArrowLeft") send({ type: "prev" });
  });

  renderSlide();
  connect();
})();
