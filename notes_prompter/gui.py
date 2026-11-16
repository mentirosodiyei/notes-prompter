"""Aplicación de escritorio. Dos modos:

- Escuchar: solo recibe notas de un agente de la red y las pinta en la pantalla elegida.
- Agente: lee la presentación de PowerPoint de este PC (o recibe de otro agente) y la
  sirve a la red. Este PC anuncia su presentación para que otros la encuentren.
"""

from __future__ import annotations

from .i18n import tr

import asyncio
import queue
import webbrowser
import socket
import sys
import subprocess
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, font as tkfont

import uvicorn
from fastapi import HTTPException

from . import __version__
from .discovery import Announcer, PeerListener
from .powerpoint import PowerPointWatcher
from .screens import Screen, find_browser, kiosk_command, list_screens
from .server import create_app
from .state import Controller
from .network import local_addresses
from .tray import TrayService, icon_image
from .settings import SettingsStore, default_settings_path

AGENT_PORT = 8765
LOCAL = "local"  # entrada: PowerPoint de este PC
REFRESH_MS = 1500


class ServerThread:
    """Servidor uvicorn en un hilo, parable desde la interfaz."""

    def __init__(self, app, port: int) -> None:
        self._server = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning",
                                                     log_config=None, access_log=False))
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self, port: int) -> None:
        self._thread.start()
        deadline = time.monotonic() + 5
        while not self._server.started:
            if not self._thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError(tr('no se pudo arrancar el servidor en el puerto {0}', f'{port}'))
            time.sleep(0.05)

    def stop(self) -> None:
        self._server.should_exit = True
        if self._thread.ident is not None:
            self._thread.join(5)


# Paleta inspirada en los paneles y controles de macOS.
BACKGROUND = "#F5F5F7"
SURFACE = "#FFFFFF"
TEXT = "#1D1D1F"
SECONDARY = "#777780"
BORDER = "#E5E5EA"
ACCENT = "#007AFF"


def rounded_rectangle(canvas, x1, y1, x2, y2, radius=12, **kwargs):
    points = [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
              x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
              x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


class MacButton(tk.Canvas):
    """Botón redondeado con foco de teclado y estados activo, normal y desactivado."""

    def __init__(self, parent, text, command, *, width=132, primary=False, **kwargs):
        super().__init__(parent, width=width, height=42, background=parent.cget("bg"),
                         highlightthickness=0, takefocus=True, cursor="hand2", **kwargs)
        self.text, self.command = text, command
        self.primary = primary
        self.selected = False
        self.disabled = False
        self.hovered = False
        self.family = parent.winfo_toplevel().font_family
        self.bind("<Enter>", lambda _: self._hover(True))
        self.bind("<Leave>", lambda _: self._hover(False))
        self.bind("<Button-1>", self._invoke)
        self.bind("<Return>", self._invoke)
        self.bind("<space>", self._invoke)
        self.bind("<FocusIn>", lambda _: self._draw())
        self.bind("<FocusOut>", lambda _: self._draw())
        self._draw()

    def _hover(self, hovered):
        self.hovered = hovered
        self._draw()

    def _invoke(self, event=None):
        if not self.disabled:
            self.focus_set()
            self.command()
        return "break"

    def config(self, **kwargs):
        if "state" in kwargs:
            self.disabled = kwargs.pop("state") == "disabled"
            super().configure(takefocus=not self.disabled, cursor="arrow" if self.disabled else "hand2")
        if "text" in kwargs:
            self.text = kwargs.pop("text")
        if kwargs:
            super().configure(**kwargs)
        self._draw()

    configure = config

    def _draw(self):
        self.delete("all")
        width, height = int(self.cget("width")), int(self.cget("height"))
        if self.primary:
            fill = "#BCD7F8" if self.disabled else "#006BE0" if self.hovered else ACCENT
            foreground = "#FFFFFF"
            outline = fill
        else:
            fill = SURFACE if self.selected else "#E7E7EC" if self.hovered and not self.disabled else self.cget("bg")
            foreground = "#B6B6BD" if self.disabled else TEXT if self.selected else SECONDARY
            outline = BORDER if self.selected else fill
        if str(self.tk.call("focus")) == str(self) and not self.disabled:
            rounded_rectangle(self, 0, 0, width, height, 11, fill="#A9CEFF", outline="")
        rounded_rectangle(self, 3, 3, width - 3, height - 3, 9, fill=fill, outline=outline)
        self.create_text(width / 2, height / 2, text=self.text, fill=foreground,
                         font=(self.family, -13, "bold"))


class RoundedPanel(tk.Canvas):
    def __init__(self, parent, *, height, fill=SURFACE):
        super().__init__(parent, height=height, bg=parent.cget("bg"), highlightthickness=0)
        self.fill = fill
        self.content = tk.Frame(self, bg=fill)
        self.window = self.create_window(1, 1, anchor="nw", window=self.content)
        self.bind("<Configure>", self._resize)

    def _resize(self, event):
        self.delete("panel")
        rounded_rectangle(self, 1, 1, event.width - 1, event.height - 1, 16,
                          fill=self.fill, outline=BORDER, tags="panel")
        self.tag_lower("panel")
        self.coords(self.window, 16, 12)
        self.itemconfigure(self.window, width=max(1, event.width - 32), height=max(1, event.height - 24))


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"Notes Prompter · {__version__}")
        self.configure(bg=BACKGROUND)
        height = min(720, max(600, self.winfo_screenheight() - 100))
        self.geometry(f"820x{height}")
        self.minsize(760, min(670, height))
        self.font_family = next((name for name in ("SF Pro Text", "Helvetica Neue", "Segoe UI")
                                 if name in tkfont.families()), "Arial")
        self._running = False
        self._exiting = False
        self.bind("<Control-Return>", lambda _: self._start() if not self._running else None)
        self._configure_styles()

        self.screens: list[Screen] = list_screens()
        self.listener = PeerListener()
        self.listener.start()
        self.server: ServerThread | None = None
        self.announcer: Announcer | None = None
        self.browser: subprocess.Popen | None = None
        self.native_output = None
        self.mac_menu = None
        self.profile: tempfile.TemporaryDirectory | None = None
        self._local_addresses = local_addresses()
        self.sources: dict[str, object] = {}
        self.mode = tk.StringVar(value="listen")
        self.source_var = tk.StringVar()
        self.screen_var = tk.StringVar()

        self.settings_store = SettingsStore(default_settings_path())
        self.admin_app = None
        self._mode_ui = None
        self.tray = TrayService()
        self.tray.start()
        from PIL import ImageTk
        self._window_icon = ImageTk.PhotoImage(icon_image())
        self.iconphoto(True, self._window_icon)
        menu = tk.Menu(self)
        application_menu = tk.Menu(menu, tearoff=False)
        application_menu.add_command(label=tr('Panel de administración'), command=self._open_admin)
        application_menu.add_command(label=tr('Ocultar ventana') if sys.platform == "darwin" else tr('Ocultar junto al reloj'), command=self._hide_to_tray)
        application_menu.add_command(label=tr('Buscar actualizaciones…'), command=lambda: self.updates.check(manual=True))
        application_menu.add_command(label=tr('Actualizaciones…'), command=lambda: self.updates.settings())
        application_menu.add_separator()
        application_menu.add_command(label=tr('Salir'), command=lambda: self.after_idle(self._close))
        menu.add_cascade(label=tr('Aplicación'), menu=application_menu)
        application_menu.insert_command(0, label=tr('Abrir ventana'), command=self._show_window)
        self.application_menu = application_menu
        self.config(menu=menu)
        if sys.platform == "darwin":
            from .macos import MacMenu
            self.mac_menu = MacMenu(self)
        body = tk.Frame(self, bg=BACKGROUND, padx=34)
        body.pack(fill="both", expand=True)
        header = tk.Frame(body, bg=BACKGROUND)
        header.pack(fill="x", pady=(9, 25))
        icon = tk.Canvas(header, width=54, height=54, bg=BACKGROUND, highlightthickness=0)
        icon.pack(side="left", padx=(0, 15))
        rounded_rectangle(icon, 0, 0, 54, 54, 14, fill="#E3ECFE", outline="")
        rounded_rectangle(icon, 15, 10, 39, 43, 5, fill=ACCENT, outline="")
        for y, end in ((20, 32), (26, 32), (32, 28)):
            icon.create_line(21, y, end, y, fill="white", width=2, capstyle="round")
        titles = tk.Frame(header, bg=BACKGROUND)
        titles.pack(side="left")
        self._label(titles, "Notes Prompter", size=25, weight="bold").pack(anchor="w")
        self.version_label = self._label(titles, tr('Versión {0} · Receptor y configuración', f'{__version__}'), size=13, color=SECONDARY)
        self.version_label.pack(anchor="w", pady=(4, 0))
        tools = tk.Frame(header, bg=BACKGROUND)
        tools.pack(side="right")
        self.network_badge = self._label(tools, tr('●  Red local'), size=12, color="#32805A")
        self.network_badge.pack(anchor="e", pady=(0, 4))
        self.admin_button = MacButton(tools, tr('Panel de administración'), self._open_admin, width=210)
        self.admin_button.pack(anchor="e")

        mode_row = tk.Frame(body, bg=BACKGROUND)
        mode_row.pack(fill="x", pady=(0, 11))
        self._label(mode_row, tr('Cómo quieres usarlo'), size=13, weight="bold").pack(side="left")
        segments = tk.Frame(mode_row, bg="#E9E9EE", padx=2, pady=1)
        segments.pack(side="right")
        self.listen_button = MacButton(segments, tr('Escuchar'), lambda: self._change_mode("listen"), width=112)
        self.listen_button.pack(side="left")
        self.agent_button = MacButton(segments, tr('Agente'), lambda: self._change_mode("agent"), width=112)
        self.agent_button.pack(side="left")
        self.mode_hint = self._label(body, tr('Recibe las notas de un equipo de tu red.'), size=12, color=SECONDARY)
        self.mode_hint.pack(anchor="w", pady=(0, 19))

        origin_panel = RoundedPanel(body, height=106)
        origin_panel.pack(fill="x", pady=(0, 15))
        origin = origin_panel.content
        self._label(origin, tr('Origen de las notas'), size=13, weight="bold").pack(anchor="w", pady=(0, 9))
        self.source_box = ttk.Combobox(origin, state="readonly", textvariable=self.source_var,
                                       style="Mac.TCombobox", font=(self.font_family, -13))
        self.source_box.pack(fill="x", ipady=6)

        output_panel = RoundedPanel(body, height=247)
        self.output_panel = output_panel
        output_panel.pack(fill="both", expand=True)
        output = output_panel.content
        output_header = tk.Frame(output, bg=SURFACE)
        output_header.pack(fill="x", pady=(1, 2))
        self._label(output_header, tr('Pantalla de salida'), size=13, weight="bold").pack(side="left")
        self.screen_count = self._label(output_header, "", size=11, color=SECONDARY)
        self.screen_count.pack(side="right")
        self._label(output, tr('Elige dónde quieres leer tus notas.'), size=12, color=SECONDARY).pack(anchor="w", pady=(0, 4))
        self.screen_canvas = tk.Canvas(output, height=112, bg=SURFACE, highlightthickness=0)
        self.screen_canvas.pack(fill="both", expand=True, pady=(2, 4))
        self.screen_canvas.bind("<Configure>", lambda _: self._draw_screens())
        self.screen_box = ttk.Combobox(output, state="readonly", textvariable=self.screen_var,
                                      style="Mac.TCombobox", font=(self.font_family, -12),
                                      values=[screen.label for screen in self.screens])
        self.screen_box.pack(fill="x", ipady=5, pady=(0, 2))
        self.screen_box.bind("<<ComboboxSelected>>", lambda _: self._draw_screens())
        if self.screens:
            self.screen_box.current(self._default_screen_index())

        footer = tk.Frame(body, bg=BACKGROUND)
        self.footer = footer
        footer.pack(fill="x", pady=(20, 23))
        information = tk.Frame(footer, bg=BACKGROUND)
        information.pack(side="left", fill="x", expand=True)
        self.status = self._label(information, tr('Listo para conectar'), size=12, color=SECONDARY)
        self.status.config(wraplength=420, justify="left")
        self.status.pack(anchor="w")
        self._label(information, tr('La X mantiene la app en segundo plano.'), size=11, color="#9999A1").pack(anchor="w", pady=(6, 0))
        self.stop_button = MacButton(footer, tr('Parar'), self._stop, width=72)
        self.stop_button.pack(side="right", padx=(0, 5))
        self.stop_button.config(state="disabled")
        self.start_button = MacButton(footer, tr('Iniciar  →'), self._start, primary=True, width=126)
        self.start_button.pack(side="right", padx=(0, 8))
        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        self.after(150, self._process_tray_actions)
        self._refresh()
        from .updates_ui import UpdateManager
        self.updates = UpdateManager(self)

    def _label(self, parent, text, *, size=13, weight="normal", color=TEXT):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=(self.font_family, -size, weight), borderwidth=0)

    def _configure_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Mac.TCombobox", foreground=TEXT, fieldbackground="#F8F8FA", background="#F8F8FA",
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, arrowcolor=SECONDARY,
                        padding=(10, 3), selectforeground=TEXT, selectbackground="#F8F8FA", borderwidth=1)
        style.map("Mac.TCombobox", fieldbackground=[("disabled", "#F3F3F5"), ("readonly", "#F8F8FA")],
                  foreground=[("disabled", "#A5A5AD")], bordercolor=[("focus", ACCENT)])
        self.option_add("*TCombobox*Listbox.font", (self.font_family, -13))
        self.option_add("*TCombobox*Listbox.background", SURFACE)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", SURFACE)

    def _hide_to_tray(self):
        if sys.platform == "darwin" or self.tray.available:
            self.withdraw()
        else:
            # Si Windows no admite el icono, queda accesible en la barra de tareas.
            self.iconify()

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _process_tray_actions(self):
        while True:
            try:
                action = self.tray.actions.get_nowait()
            except queue.Empty:
                break
            if action == "exit":
                self._close()
                return
            if action == "open":
                self._show_window()
            elif action == "stop":
                self._stop()
                self._show_window()
            elif action == "admin":
                self._open_admin()
        if not self._exiting:
            self.after(150, self._process_tray_actions)

    def _open_admin(self, section=None):
        if self.mode.get() == "agent":
            self._say(tr('El agente solo entrega notas. Los ajustes y presets están en el receptor, en modo Escuchar.'))
            return
        try:
            if self.server is None:
                source = self.sources.get(self.source_var.get())
                self._start_master(f"ws://{source.ip}:{source.port}/ws" if source else None)
        except (OSError, RuntimeError, HTTPException, TimeoutError) as exc:
            self._stop()
            self._say(tr('No se pudo abrir el panel del receptor: {0}', f'{exc}'))
            self._show_window()
            return
        url = f"http://127.0.0.1:{AGENT_PORT}/?v={__version__}"
        if section:
            url += f"#{section}"
        webbrowser.open(url)

    def _remote_peers(self):
        return [peer for peer in self.listener.peers()
                if not (peer.port == AGENT_PORT and peer.ip in self._local_addresses)]

    def _change_mode(self, mode):
        if self._running:
            return
        if self.server is not None and mode != self.mode.get():
            self._stop()
        self.mode.set(mode)
        self._refresh(schedule=False)

    def _draw_screens(self):
        canvas = self.screen_canvas
        canvas.delete("all")
        count = len(self.screens)
        self.screen_count.config(text=tr("1 pantalla activa") if count == 1 else tr("{0} pantallas activas", count))
        if not count:
            canvas.create_text(max(1, canvas.winfo_width())/2, 55, text=tr('Conecta una pantalla para continuar.'),
                               fill=SECONDARY, font=(self.font_family, -12))
            return
        width = max(200, canvas.winfo_width())
        min_x, min_y = min(s.x for s in self.screens), min(s.y for s in self.screens)
        span_x = max(s.x+s.width for s in self.screens)-min_x
        span_y = max(s.y+s.height for s in self.screens)-min_y
        scale = min((width-48)/max(1,span_x), 69/max(1,span_y), 0.085)
        left = (width-span_x*scale)/2
        selected = self.screen_box.current()
        for i, screen in enumerate(self.screens):
            x, y = left+(screen.x-min_x)*scale, 10+(screen.y-min_y)*scale
            w, h = screen.width*scale, screen.height*scale
            # Un pequeño margen distingue monitores contiguos.
            x, w = x+4, max(8,w-8)
            active = i == selected
            tag = f"screen-{i}"
            rounded_rectangle(canvas,x,y,x+w,y+h,7,fill="#EAF2FF" if active else "#F4F4F7",
                              outline=ACCENT if active else "#DADAE1",width=2 if active else 1,tags=tag)
            canvas.create_text(x+w/2,y+h/2,text=tr('Notas') if active else str(screen.index+1),
                               fill=ACCENT if active else "#A0A0AA",font=(self.font_family,-12,"bold"),tags=tag)
            canvas.create_line(x+w/2,y+h+1,x+w/2,y+h+7,fill="#D1D1D8",width=2,tags=tag)
            canvas.create_line(x+w/2-11,y+h+7,x+w/2+11,y+h+7,fill="#D1D1D8",width=2,tags=tag)
            canvas.create_text(x+w/2,y+h+21,text=f"{screen.index+1}" + (tr(" · Principal") if screen.primary else ""),
                               fill=TEXT if active else SECONDARY,font=(self.font_family,-11),tags=tag)
            canvas.tag_bind(tag,"<Button-1>",lambda _, index=i:self._choose_screen(index))
            canvas.tag_bind(tag,"<Enter>",lambda _:canvas.config(cursor="arrow" if self._running else "hand2"))
            canvas.tag_bind(tag,"<Leave>",lambda _:canvas.config(cursor="arrow"))

    def _choose_screen(self, index):
        if not self._running:
            self.screen_box.current(index)
            self._draw_screens()

    def _default_screen_index(self) -> int:
        # Preferencia: primera pantalla que no sea la principal (la del portátil), si existe.
        for screen in self.screens:
            if not screen.primary:
                return screen.index
        return 0

    def _refresh(self, schedule: bool = True) -> None:
        """Rellena el combo de entrada según el modo y los agentes vistos en la red."""
        self._local_addresses = local_addresses()
        sources: dict[str, object] = {}
        if self.mode.get() == "agent":
            sources[tr('PowerPoint de este equipo')] = LOCAL
        for peer in self.listener.peers():
            if peer.port == AGENT_PORT and peer.ip in self._local_addresses:
                continue
            sources[peer.label] = peer
        if self.admin_app is not None:
            source_id = self.admin_app.state.source_id()
            chosen = next((label for label, item in sources.items()
                           if ("local" if item == LOCAL else f"{item.ip}:{item.port}") == source_id), None)
            if chosen:
                self.source_var.set(chosen)
        current = self.source_var.get()
        previous_source = self.sources.get(current)
        if current not in sources and previous_source is not None and previous_source != LOCAL:
            current = next((label for label, peer in sources.items()
                            if peer != LOCAL and (peer.ip, peer.port) == (previous_source.ip, previous_source.port)), current)
            self.source_var.set(current)
        self.sources = sources
        self.source_box["values"] = list(sources)
        if current not in sources:
            self.source_var.set(next(iter(sources), ""))
        if not self._running:
            previous = self._selected_screen()
            self.screens = list_screens()
            self.screen_box["values"] = [screen.label for screen in self.screens]
            selected = next((i for i, screen in enumerate(self.screens) if screen == previous), None)
            if self.screens:
                self.screen_box.current(selected if selected is not None else self._default_screen_index())
            else:
                self.screen_var.set("")
            if not sources:
                self._say(tr('Buscando un agente en tu red…'))
            else:
                self._say(tr('Todo listo. Puedes iniciar la salida.') if self.mode.get() == "listen"
                          else tr('Todo listo. Puedes iniciar el envío de notas.'))
        self.listen_button.selected = self.mode.get() == "listen"
        self.agent_button.selected = self.mode.get() == "agent"
        self.listen_button._draw()
        self.agent_button._draw()
        self.mode_hint.config(text=tr('Recibe las notas de un equipo de tu red.') if self.mode.get() == "listen"
                              else tr('Entrega las notas a la red, sin abrir salida ni navegador.'))
        self._update_mode_controls()
        self._draw_screens()
        if self.admin_app is not None:
            error = self.admin_app.state.source_error()
            if error:
                self._say(error)
        if schedule:
            self.after(REFRESH_MS, self._refresh)

    def _say(self, text: str) -> None:
        self.status.config(text=text, fg=ACCENT if self._running else SECONDARY)

    def _selected_screen(self) -> Screen | None:
        index = self.screen_box.current()
        return self.screens[index] if 0 <= index < len(self.screens) else None

    def _update_mode_controls(self):
        mode = self.mode.get()
        if mode == self._mode_ui:
            return
        self._mode_ui = mode
        listening = mode == "listen"
        self.version_label.config(text=tr('Versión {0} · ', f'{__version__}') + (tr('Receptor y configuración') if listening else tr('Agente de notas')))
        self.start_button.config(text=tr('Iniciar salida') if listening else tr('Iniciar agente'))
        if listening:
            self.admin_button.pack(anchor="e")
            self.output_panel.pack(fill="both", expand=True, before=self.footer)
        else:
            self.admin_button.pack_forget()
            self.output_panel.pack_forget()
        self.application_menu.entryconfigure(1, state="normal" if listening else "disabled")
        self.tray.set_configuration_enabled(listening)
        if self.mac_menu is not None:
            self.mac_menu.set_configuration_enabled(listening)

    def _start(self) -> None:
        if getattr(getattr(self, 'updates', None), 'installing', False):
            return
        if self._running:
            return
        source = self.sources.get(self.source_var.get())
        if source is None:
            self._say(tr('Elige una entrada.'))
            return
        agent = self.mode.get() == "agent"
        if not agent and self._selected_screen() is None:
            self._say(tr('No hay una pantalla activa seleccionada.'))
            return
        browser = None if agent else find_browser() if sys.platform != "darwin" else "native"
        if not agent and browser is None:
            self._say(tr('No encuentro Chrome ni Edge. Instala uno para mostrar la nota.'))
            return

        try:
            if agent:
                self._start_agent(None if source == LOCAL else f"ws://{source.ip}:{source.port}/ws")
            else:
                self._start_master(f"ws://{source.ip}:{source.port}/ws")
                self._open_output(browser, f"http://127.0.0.1:{AGENT_PORT}/display", self._selected_screen())
        except (RuntimeError, OSError, HTTPException, TimeoutError) as exc:
            self._stop()
            self._say(f"Error: {exc}")
            return

        self._set_running(True)
        self.stop_button.config(state="normal")
        self._say(tr('Enviando notas de {0} a la red.', f'{self.source_var.get()}') if agent
                  else tr('Mostrando la nota desde {0}.', f'{self.source_var.get()}'))

    def _set_running(self, running: bool) -> None:
        self._running = running
        self.start_button.config(state="disabled" if running else "normal")
        for button in (self.listen_button, self.agent_button):
            button.config(state="disabled" if running else "normal")
        for box in (self.source_box, self.screen_box):
            box.config(state="disabled" if running else "readonly")

    def _start_agent(self, upstream: str | None = None) -> None:
        self._start_service(upstream, agent=True)

    def _start_master(self, upstream: str | None = None) -> None:
        self._start_service(upstream, agent=False)

    def _start_service(self, upstream: str | None, *, agent: bool) -> None:
        if self.server is not None:
            source_id = ("local" if agent else "manual") if upstream is None else upstream.split("/")[2]
            if source_id == self.admin_app.state.source_id():
                return
            future = asyncio.run_coroutine_threadsafe(self.admin_app.state.select_source(source_id),
                                                     self.admin_app.state.loop)
            future.result(timeout=5)
            return
        controller = Controller()
        watcher = PowerPointWatcher() if agent and upstream is None else None
        app = create_app(controller, powerpoint=watcher, upstream=upstream,
                         peers_fn=None if agent else self._remote_peers,
                         settings=SettingsStore() if agent else self.settings_store,
                         role="agent" if agent else "master", allow_local_source=agent)
        self.admin_app = app
        self.server = ServerThread(app, AGENT_PORT)
        self.server.start(AGENT_PORT)
        if agent:
            self.announcer = Announcer(socket.gethostname(), AGENT_PORT, lambda: app.state.presentation_name())
            self.announcer.start()

    def _open_output(self, browser: str, url: str, screen: Screen | None) -> None:
        if sys.platform == "darwin":
            from .macos import NativeOutput
            self.native_output = NativeOutput(url, screen, lambda: self.tray.actions.put("stop"))
            return
        self.profile = tempfile.TemporaryDirectory(prefix="notes-prompter-", ignore_cleanup_errors=True)
        # PyInstaller altera la búsqueda de DLL. El navegador debe usar las del sistema.
        if sys.platform == "win32" and getattr(sys, "frozen", False):
            import ctypes

            ctypes.windll.kernel32.SetDllDirectoryW(None)
            try:
                self.browser = subprocess.Popen(kiosk_command(browser, url, screen, self.profile.name))
            finally:
                ctypes.windll.kernel32.SetDllDirectoryW(sys._MEIPASS)
        else:
            self.browser = subprocess.Popen(kiosk_command(browser, url, screen, self.profile.name))

    def _stop(self) -> None:
        if self.native_output is not None:
            self.native_output.close()
            self.native_output = None
        if self.browser is not None:
            try:
                self.browser.terminate()
                self.browser.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.browser.kill()
                self.browser.wait(timeout=3)
            except OSError:
                pass
            self.browser = None
        if self.profile is not None:
            self.profile.cleanup()
            self.profile = None
        if self.announcer is not None:
            self.announcer.stop()
            self.announcer.join(2)
            self.announcer = None
        if self.server is not None:
            self.server.stop()
            self.server = None
            self.admin_app = None
        self._set_running(False)
        self.stop_button.config(state="disabled")
        self._say(tr('Parado.'))

    def _close(self) -> None:
        if self._exiting:
            return
        self._exiting = True
        if hasattr(self, 'updates'):
            self.updates.closed = True
        self._stop()
        self.listener.stop()
        self.listener.join(2)
        self.tray.stop()
        if self.mac_menu is not None:
            self.mac_menu.close()
        self.destroy()


def main() -> None:
    if sys.platform == "win32":
        import ctypes

        # Coordenadas físicas coherentes entre Tk, screeninfo y el navegador.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    App().mainloop()


if __name__ == "__main__":
    main()
