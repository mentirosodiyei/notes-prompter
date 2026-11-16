"""Tk integration; worker threads only communicate through a queue."""
from __future__ import annotations

import json
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from .i18n import tr
from .settings import default_settings_path
from .updates import (UpdateError, UpdatePreferences, check_release, installation_target,
                      launch_helper, prepare_plan)


class UpdateManager:
    def __init__(self, root):
        self.root = root
        folder = default_settings_path().parent
        self.preferences_path = folder / 'updates.json'
        self.result_path = folder / 'update-result.json'
        self.preferences = UpdatePreferences.load(self.preferences_path)
        self.target = installation_target()
        self.events = queue.SimpleQueue()
        self.busy = False
        self.installing = False
        self.pending = None
        self.dialog = None
        self.next_check = self.scheduled_check()
        self.closed = False
        root.after(1000, self.poll)
        # Source demos/tests have no updater network traffic and cannot self-install.
        if self.target is not None:
            root.after(1500, self.show_result)

    def scheduled_check(self):
        elapsed = time.time() - self.preferences.last_checked
        remaining = self.preferences.days * 86400 - elapsed if elapsed >= 0 else 0
        return time.monotonic() + max(30, remaining)

    def show_result(self):
        try:
            data = json.loads(self.result_path.read_text(encoding='utf-8'))
            self.result_path.unlink()
        except (OSError, ValueError):
            return
        if not data.get('ok'):
            messagebox.showerror(tr('Actualizaciones'), tr('No se pudo completar la actualización. Se ha conservado la aplicación anterior.'), parent=self.root)

    def save_preferences(self):
        try:
            self.preferences.save(self.preferences_path)
            return True
        except OSError:
            messagebox.showerror(tr('Actualizaciones'), tr('No se pudieron guardar las preferencias de actualización.'), parent=self.root)
            return False

    def settings(self):
        dialog = tk.Toplevel(self.root)
        dialog.title(tr('Actualizaciones'))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=20)
        frame.pack()
        enabled = tk.BooleanVar(value=self.preferences.enabled)
        periods = [tr('Semanal'), tr('Mensual')]
        ttk.Checkbutton(frame, text=tr('Buscar actualizaciones automáticamente'), variable=enabled).pack(anchor='w')
        row = ttk.Frame(frame)
        row.pack(fill='x', pady=12)
        ttk.Label(row, text=tr('Frecuencia:')).pack(side='left', padx=(0, 10))
        period = ttk.Combobox(row, values=periods, state='readonly', width=14)
        period.current(0 if self.preferences.days == 7 else 1)
        period.pack(side='left')
        ttk.Label(frame, text=tr('Semanal: cada 7 días. Mensual: cada 30 días. Los avisos esperan mientras la app está en uso.'), wraplength=380).pack(anchor='w')
        def save():
            previous = UpdatePreferences(**vars(self.preferences))
            self.preferences.enabled, self.preferences.days = enabled.get(), (7 if period.current() == 0 else 30)
            if self.save_preferences():
                self.next_check = self.scheduled_check()
                dialog.destroy()
            else:
                self.preferences = previous
        ttk.Button(frame, text=tr('Guardar'), command=save).pack(side='right', pady=(16, 0))
        ttk.Button(frame, text=tr('Buscar ahora'), command=lambda: self.check(manual=True)).pack(side='left', pady=(16, 0))

    def check(self, manual=False):
        if self.busy or self.installing:
            return
        if self.target is None:
            if manual:
                messagebox.showinfo(tr('Actualizaciones'), tr('La actualización automática requiere la aplicación instalada o el EXE portable. Esta copia se ejecuta desde el código fuente.'), parent=self.root)
            return
        self.busy = True
        self.preferences.last_checked = time.time()
        self.next_check = time.monotonic() + self.preferences.days * 86400
        self.save_preferences()
        def worker():
            try:
                self.events.put(('checked', check_release(self.target), manual))
            except Exception:
                self.events.put(('check_error', None, manual))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        if self.closed or self.root._exiting:
            return
        while True:
            try:
                kind, data, manual = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'progress':
                self.root._say(tr('Descargando actualización: {0} %', str(round(data * 100))))
                continue
            self.busy = False
            if kind == 'checked':
                if data and (manual or data.version != self.preferences.skipped):
                    self.pending = data
                    if manual and self.root.server is not None:
                        messagebox.showinfo(tr('Actualización disponible'), tr('Hay una actualización pendiente. Para instalarla, para primero el agente o la salida.'), parent=self.root)
                elif manual:
                    messagebox.showinfo(tr('Actualizaciones'), tr('Ya tienes la versión más reciente.'), parent=self.root)
            elif kind == 'check_error' and manual:
                messagebox.showerror(tr('Actualizaciones'), tr('No se pudo consultar GitHub. Comprueba la conexión y vuelve a intentarlo.'), parent=self.root)
            elif kind == 'prepared':
                try:
                    launch_helper(data)
                except Exception:
                    self.installing = False
                    self.root.start_button.config(state='normal')
                    messagebox.showerror(tr('Actualizaciones'), tr('No se pudo iniciar el instalador. La aplicación sigue abierta.'), parent=self.root)
                else:
                    self.root._close()
                    return
            elif kind == 'prepare_error':
                self.installing = False
                self.root.start_button.config(state='normal')
                self.root._say(tr('No se pudo preparar la actualización.'))
                messagebox.showerror(tr('Actualizaciones'), data, parent=self.root)
        if not self.busy and not self.installing:
            if self.target is not None and self.preferences.enabled and time.monotonic() >= self.next_check:
                self.check()
            if self.pending and self.root.server is None and self.root.state() == 'normal' and self.dialog is None:
                self.offer()
        self.root.after(500, self.poll)

    def offer(self):
        release = self.pending
        self.pending = None
        dialog = self.dialog = tk.Toplevel(self.root)
        dialog.title(tr('Actualización disponible'))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=22)
        frame.pack()
        ttk.Label(frame, text=tr('Está disponible Notes Prompter {0}.', release.version), font=('', 14, 'bold')).pack(anchor='w')
        ttk.Label(frame, text=tr('Si aceptas, se descargará, verificará e instalará. La app se cerrará y volverá a abrirse. Tus ajustes y presets se conservarán.'), wraplength=420).pack(anchor='w', pady=12)
        def dismiss(skip=False):
            if skip:
                self.preferences.skipped = release.version
                self.save_preferences()
            self.dialog = None
            dialog.destroy()
        def accept():
            if self.root.server is not None:
                messagebox.showinfo(tr('Actualizaciones'), tr('Para primero el agente o la salida antes de actualizar.'), parent=dialog)
                return
            dismiss()
            self.installing = True
            self.root.start_button.config(state='disabled')
            self.root._say(tr('Preparando actualización…'))
            def worker():
                try:
                    path = prepare_plan(release, self.target, self.result_path,
                                        lambda value: self.events.put(('progress', value, False)))
                    self.events.put(('prepared', path, False))
                except Exception as error:
                    detail = str(error) if isinstance(error, UpdateError) else tr('No se pudo preparar la actualización. Comprueba los permisos, el espacio disponible y la conexión. La aplicación no se ha cambiado.')
                    self.events.put(('prepare_error', detail, False))
            threading.Thread(target=worker, daemon=True).start()
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=(5, 0))
        ttk.Button(buttons, text=tr('Omitir esta versión'), command=lambda: dismiss(True)).pack(side='left')
        ttk.Button(buttons, text=tr('Ahora no'), command=dismiss).pack(side='left', padx=8)
        ttk.Button(buttons, text=tr('Descargar e instalar'), command=accept).pack(side='right')
        dialog.protocol('WM_DELETE_WINDOW', dismiss)
