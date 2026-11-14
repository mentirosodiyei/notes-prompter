"""Read-only PowerPoint Apple Events, isolated from the HTTP event loop."""
from __future__ import annotations

from .i18n import tr

import json
import subprocess
import threading
from pathlib import Path

from .notes import Deck
from .powerpoint import SlideState, _clean_notes


class MacPowerPointWatcher:
    def __init__(self, *, interval: float = 0.3, timeout: float = 4.0):
        self.interval = interval
        self.timeout = timeout
        self.error: str | None = None
        self._state: SlideState | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def _read(self) -> SlideState | None:
        # The compiled resource lets listener-only Macs run without PowerPoint's dictionary.
        script = Path(__file__).with_name("powerpoint_mac.scpt")
        if not script.is_file():
            script = script.with_suffix(".applescript")
        # Loading from an inline wrapper avoids osascript trying to save runtime
        # variables back into a signed, read-only application bundle.
        escaped = str(script).replace("\\", "\\\\").replace('"', '\\"')
        command = ["/usr/bin/osascript", "-e", f'run script (POSIX file "{escaped}")']
        with self._lock:
            if self._stop.is_set():
                return None
            process = subprocess.Popen(command,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self._process = process
        try:
            output, error = process.communicate(timeout=self.timeout)
            if process.returncode:
                if "-1743" in error or "-10004" in error:
                    raise RuntimeError(tr('Permite a Notes Prompter acceder a PowerPoint en Ajustes del Sistema → Privacidad y seguridad → Automatización. Después vuelve a iniciar el agente.'))
                if "-1712" in error:
                    raise RuntimeError(tr('PowerPoint no responde. Cierra sus diálogos y vuelve a intentarlo.'))
                raise RuntimeError(tr('No se pudo leer PowerPoint: ') + error.strip()[:300])
            return self.decode(output)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise RuntimeError(tr('PowerPoint no responde o espera el permiso de Automatización.')) from None
        finally:
            with self._lock:
                self._process = None

    @staticmethod
    def decode(output: str) -> SlideState | None:
        data = json.loads(output)
        if data == {}:
            return None
        index, total = data["index"], data["total"]
        if type(index) is not int or type(total) is not int or not 1 <= index <= total <= 99999:
            raise ValueError(tr('PowerPoint devolvió un índice de diapositiva inválido.'))
        if any(not isinstance(data[key], str) for key in ("name", "path", "notes")):
            raise ValueError(tr('PowerPoint devolvió notas inválidas.'))
        # Only the current slide is required by Controller.follow. Re-read it every poll,
        # including unsaved notes. No disk cache can make a returned note stale.
        notes = [""] * total
        notes[index - 1] = _clean_notes(data["notes"])
        return SlideState(Deck(Path(data["name"]).stem, data["path"], tuple(notes)), index)

    def _run(self):
        while not self._stop.is_set():
            try:
                state = self._read()
                error = None if state else tr('Abre una presentación en PowerPoint y selecciona una diapositiva.')
            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
                state, error = None, str(exc)
            self._state, self.error = state, error
            # Back off after an error; never accumulate Apple Event workers.
            if self._stop.wait(self.interval if state else max(1, self.interval)):
                break

    def poll(self) -> SlideState | None:
        if self._thread is None and not self._stop.is_set():
            self._thread = threading.Thread(target=self._run, name="powerpoint-apple-events", daemon=True)
            self._thread.start()
        return self._state

    def close(self):
        self._stop.set()
        with self._lock:
            if self._process is not None:
                try:
                    self._process.kill()
                except OSError:
                    pass
        if self._thread is not None:
            self._thread.join(self.timeout + 0.5)
        self._state = None
