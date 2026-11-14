"""Servidor HTTP + WebSocket: sirve las páginas y reparte el estado a los clientes."""

from __future__ import annotations

from .i18n import tr, localized_html
from . import i18n

import asyncio
import json
import logging
from contextlib import suppress
from contextlib import asynccontextmanager
from pathlib import Path
import socket
from urllib.parse import urlsplit, unquote
from typing import Callable, Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .powerpoint import PowerPointWatcher
from .protocol import parse_slide, slide_message
from .protocol import ProtocolError, error_message, parse_command, presentations_message
from .state import Controller
from .settings import DisplaySettings, SettingsStore, PresetInput
from .notes import presentation_metadata

class SourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str


class PresetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=80)
    copy_from: str | None = None


class PresetSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preset_id: str | None = None


class AutomaticSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(strict=True)


class SlideScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    presentation: str
    index: int = Field(ge=1, le=99999, strict=True)


class LiveAdjustment(SlideScope):
    min_font_px: int | None = Field(default=None, ge=24, le=600, strict=True)
    speed_px_s: float | None = Field(default=None, ge=-200, le=200, strict=True, allow_inf_nan=False)
    auto_scroll: bool | None = Field(default=None, strict=True)
    font_mode: str | None = None


class PlaybackRequest(SlideScope):
    action: Literal["pause", "resume", "restart"]


STATIC_DIR = Path(__file__).parent / "static"
DISPLAY_ROLE = "display"
CONTROL_ROLE = "control"


def html_page(name: str) -> HTMLResponse:
    return HTMLResponse(localized_html((STATIC_DIR / name).read_text(encoding="utf-8")),
                        headers={"Content-Language":i18n.get_language(),"Cache-Control":"no-store"})


def create_app(
    controller: Controller | None = None,
    powerpoint: PowerPointWatcher | None = None,
    poll_interval: float = 0.3,
    upstream: str | None = None,
    reconnect_interval: float = 1.0,
    peers_fn: Callable | None = None,
    settings: SettingsStore | None = None,
    role: Literal["master", "agent"] = "master",
    allow_local_source: bool = True,
) -> FastAPI:
    if role not in {"master", "agent"}:
        raise ValueError(tr('El rol debe ser master o agent.'))
    ctrl = controller or Controller()
    clients: dict[WebSocket, str] = {}  # WebSocket -> rol declarado en su hello

    if powerpoint is not None and upstream is not None:
        raise ValueError(tr('Elige una sola entrada para el agente.'))
    store = settings if settings is not None else SettingsStore()
    active_source_id = "local" if powerpoint is not None else urlsplit(upstream).netloc if upstream else "manual"
    remote = slide_message(None, 0, 0, "")
    task = None
    source_lock = asyncio.Lock()
    live_scope = None
    live_values = {}
    playback_scope = None
    playback_paused = False
    restart_id = 0
    playback_revision = 0

    def source_options():
        items = ([{"id": "local", "name": socket.gethostname(), "label": tr('PowerPoint de este PC'),
                   "presentation": "", "kind": "local"}] if allow_local_source else [])
        for peer in peers_fn() if peers_fn else []:
            items.append({"id": f"{peer.ip}:{peer.port}", "name": peer.name, "label": peer.label,
                          "presentation": peer.presentation, "kind": "remote"})
        return items

    async def stop_following():
        nonlocal task
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            task = None
        if powerpoint is not None and hasattr(powerpoint, "close"):
            powerpoint.close()

    async def select_source(source_id: str):
        nonlocal upstream, powerpoint, active_source_id, remote, task
        if role == "agent" or peers_fn is None:
            raise HTTPException(409, tr('Selecciona el modo Escuchar en el receptor para cambiar la fuente desde su panel.'))
        async with source_lock:
            if source_id == active_source_id:
                return
            chosen = next((item for item in source_options() if item["id"] == source_id), None)
            if chosen is None:
                raise HTTPException(409, tr('El equipo ya no está disponible. Actualiza la lista.'))
            await stop_following()
            ctrl.clear()
            remote = slide_message(None, 0, 0, "")
            active_source_id = source_id
            upstream = None if source_id == "local" else f"ws://{source_id}/ws"
            powerpoint = PowerPointWatcher() if source_id == "local" else None
            await broadcast_state()
            task = asyncio.create_task(follow_powerpoint() if powerpoint is not None else follow_remote())

    def current_message() -> dict:
        return remote if upstream is not None else ctrl.current_message()

    def current_scope():
        slide = current_message()
        return (active_source_id, slide["presentation"], slide["index"])

    def check_scope(payload: SlideScope):
        if (payload.source, payload.presentation, payload.index) != current_scope():
            raise HTTPException(409, tr('La diapositiva o el origen ha cambiado. Revisa la actual antes de ajustar o guardar.'))

    def playback_state():
        nonlocal playback_scope, playback_paused
        scope = current_scope()
        if playback_scope != scope:
            playback_scope, playback_paused = scope, False
        return {"source": scope[0], "presentation": scope[1], "index": scope[2],
                "paused": playback_paused, "restart_id": restart_id, "revision": playback_revision}

    def effective_settings():
        nonlocal live_scope, live_values
        if live_scope != current_scope():
            live_scope, live_values = None, {}
        slide = current_message()
        base = store.effective(slide["presentation"], slide["index"]).model_dump()
        return {**base, **live_values}

    def wire_slide():
        if role == "agent":
            return current_message()
        # Each slide carries its complete reading configuration, including the reset
        # after a temporary live adjustment. Extra fields remain compatible with 0.2.
        return {**current_message(), "display_settings": effective_settings(), "playback": playback_state()}

    async def broadcast_settings(restart=False, live=False):
        message = {"type": "display_settings", **effective_settings(), "playback": playback_state()}
        if restart:
            message["restart"] = True
        if live:
            message["live"] = True
        for ws in list(clients):
            await send(ws, message)

    def current_presentations() -> dict:
        if upstream is not None:
            name = remote["presentation"]
            return presentations_message([name] if name else [], name)
        return presentations_message(ctrl.names, ctrl.active_name)

    async def follow_powerpoint() -> None:
        last = None
        while True:
            try:
                state = powerpoint.poll()
            except Exception:
                logging.getLogger(__name__).exception(tr('No se pudo consultar PowerPoint; se reintentará.'))
                state = None
            if state is not None:
                signature = (state.deck, state.index)
                if signature != last:
                    last = signature
                    ctrl.follow(state.deck, state.index)
                    await broadcast_state()
            elif last is not None:
                last = None
                ctrl.clear()
                await broadcast_state()
            await asyncio.sleep(poll_interval)

    async def follow_remote() -> None:
        import websockets

        nonlocal remote
        while True:
            try:
                async with websockets.connect(upstream, open_timeout=5, close_timeout=1) as connection:
                    await connection.send(json.dumps({"type": "hello", "role": "display"}))
                    async for raw in connection:
                        try:
                            message = parse_slide(raw)
                        except ProtocolError:
                            continue
                        remote = message
                        await broadcast_state()
            except (OSError, websockets.WebSocketException):
                pass
            remote = slide_message(None, 0, 0, "")
            await broadcast_state()
            await asyncio.sleep(reconnect_interval)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        nonlocal task
        app.state.loop = asyncio.get_running_loop()
        if role == "master" and ctrl.active_name:
            slide = ctrl.current_message()
            if slide["total"]:
                try:
                    store.remember_presentation(slide["presentation"], slide["total"])
                except (OSError, ValueError):
                    pass
        if powerpoint is not None:
            task = asyncio.create_task(follow_powerpoint())
        elif upstream is not None:
            task = asyncio.create_task(follow_remote())
        try:
            yield
        finally:
            await stop_following()

    app = FastAPI(title="notes-prompter", version=__version__, lifespan=lifespan,
                  docs_url="/docs" if role == "master" else None,
                  redoc_url="/redoc" if role == "master" else None,
                  openapi_url="/openapi.json" if role == "master" else None)
    app.state.role = role
    app.state.presentation_name = lambda: current_message()["presentation"]
    app.state.source_error = lambda: getattr(powerpoint, "error", None) if powerpoint is not None else None
    app.state.source_id = lambda: active_source_id
    app.state.select_source = select_source
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def fresh_master_panel(request: Request, call_next):
        path = request.url.path
        if role == "agent" and (path in {"/", "/admin", "/control", "/display", "/api/display-settings"}
                                or path.startswith(("/api/admin", "/static/"))):
            response = JSONResponse(status_code=403, content={"detail":
                tr('Este equipo es un agente y solo entrega notas. Abre el panel en el receptor, en modo Escuchar.')})
        else:
            response = await call_next(request)
        response.headers["X-Notes-Prompter-Version"] = __version__
        response.headers["X-Notes-Prompter-Role"] = role
        if request.url.path in {"/", "/admin", "/control", "/display"} or request.url.path.startswith(("/static/", "/api/")):
            response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @app.get("/api/agent/state")
    async def agent_state():
        current = current_message()
        return {"version": __version__, "role": role, "computer": socket.gethostname(),
                "presentation": current["presentation"], "index": current["index"],
                "total": current["total"]}

    @app.get("/")
    async def master_page() -> HTMLResponse:
        return html_page("admin.html")

    @app.get("/control")
    async def control_page() -> HTMLResponse:
        return html_page("control.html")

    @app.get("/display")
    async def display_page() -> HTMLResponse:
        return html_page("display.html")

    @app.get("/admin")
    async def admin_page() -> HTMLResponse:
        return html_page("admin.html")

    @app.get("/api/display-settings")
    async def display_settings():
        return effective_settings()

    @app.get("/api/admin/state")
    async def admin_state():
        return {"version": __version__, "role": role, "language": i18n.get_language(), "settings_error":store.load_error, "features": ["presets", "slide_rules", "master_dashboard"],
                "computer": socket.gethostname(), "source_enabled": peers_fn is not None,
                "source": active_source_id, "sources": source_options() if peers_fn else [],
                "slide": current_message(), "display_settings": store.value.model_dump(),
                "presets": [preset.model_dump(mode="json") for preset in store.document.presets],
                "active_preset_id": store.document.active_preset_id,
                "effective_preset_id": store.effective_preset_id(current_message()["presentation"]),
                "auto_select_presentation": store.document.auto_select_presentation,
                "presentations": [info.model_dump() for info in store.document.presentations.values()],
                "live_adjustment": bool(live_values) if live_scope == current_scope() else False,
                "effective_display_settings": effective_settings(),
                "programmed_display_settings": store.effective(current_message()["presentation"], current_message()["index"]).model_dump(),
                "font_size_limits": {"min": 24, "max": 600},
                "speed_limits": {"min": -200, "max": 200},
                "playback": playback_state(),
                "source_error": app.state.source_error(),
                "reading_context": store.context(current_message()["presentation"], current_message()["index"])}

    def require_same_origin(request: Request):
        # Evita cambios desde páginas de otra web; la LAN continúa sin autenticación.
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.headers.get("host"):
            raise HTTPException(403, tr('El cambio debe enviarse desde el panel de este agente.'))

    @app.post("/api/admin/source")
    async def update_source(payload: SourceRequest, request: Request):
        require_same_origin(request)
        await select_source(payload.source)
        return await admin_state()

    @app.put("/api/admin/display-settings")
    async def update_display_settings(payload: DisplaySettings, request: Request):
        nonlocal live_scope, live_values
        require_same_origin(request)
        current = current_message()
        before = store.effective(current["presentation"], current["index"])
        try:
            store.update(payload)
        except OSError as exc:
            raise HTTPException(503, tr('No se pudieron guardar las preferencias de lectura.')) from exc
        if before != store.effective(current["presentation"], current["index"]):
            live_scope, live_values = None, {}
        await broadcast_settings()
        return store.value.model_dump()

    def persist_preset(operation):
        try:
            return operation()
        except KeyError as exc:
            raise HTTPException(404, exc.args[0]) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except OSError as exc:
            raise HTTPException(503, tr('No se pudo guardar el preset. Los ajustes anteriores se conservan.')) from exc

    @app.post("/api/admin/presentations", status_code=201)
    async def register_presentation(request: Request):
        require_same_origin(request)
        limit = 256 * 1024 * 1024
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > limit:
                raise HTTPException(413, tr('El archivo supera 256 MB. Usa el PowerPoint abierto para detectar sus diapositivas.'))
        filename = unquote(request.headers.get("x-presentation-name", ""))
        try:
            name, total = await asyncio.to_thread(presentation_metadata, bytes(data), filename)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return persist_preset(lambda: store.remember_presentation(name, total)).model_dump()

    @app.put("/api/admin/automatic-preset")
    async def automatic_preset(payload: AutomaticSelection, request: Request):
        nonlocal live_scope, live_values
        require_same_origin(request)
        persist_preset(lambda: store.set_automatic(payload.enabled))
        live_scope, live_values = None, {}
        await broadcast_settings(restart=True)
        return await admin_state()

    @app.put("/api/admin/live-settings")
    async def update_live_settings(payload: LiveAdjustment, request: Request):
        nonlocal live_scope, live_values
        require_same_origin(request)
        check_scope(payload)
        values = payload.model_dump(exclude={"source", "presentation", "index"}, exclude_none=True)
        if not values:
            raise HTTPException(422, tr('Indica un ajuste de letra, velocidad o desplazamiento.'))
        merged = {**effective_settings(), **values}
        try:
            DisplaySettings.model_validate(merged)
        except ValueError as exc:
            raise HTTPException(422, tr('Revisa el tamaño de letra y la velocidad.')) from exc
        live_scope = current_scope()
        live_values = {**live_values, **values}
        await broadcast_settings(live=True)
        return await admin_state()

    @app.post("/api/admin/playback")
    async def update_playback(payload: PlaybackRequest, request: Request):
        nonlocal playback_paused, restart_id, playback_revision
        require_same_origin(request)
        check_scope(payload)
        playback_state()  # Reset a previous slide's pause before applying this action.
        if payload.action == "restart":
            restart_id += 1
        else:
            playback_paused = payload.action == "pause"
        playback_revision += 1
        message = {"type": "playback", **playback_state()}
        for ws in list(clients):
            await send(ws, message)
        return await admin_state()

    @app.post("/api/admin/live-settings/reset")
    async def reset_live_settings(payload: SlideScope, request: Request):
        nonlocal live_scope, live_values
        require_same_origin(request)
        check_scope(payload)
        live_scope, live_values = None, {}
        await broadcast_settings(live=True)
        return await admin_state()

    @app.post("/api/admin/live-settings/save")
    async def save_live_settings(payload: SlideScope, request: Request):
        nonlocal live_scope, live_values
        require_same_origin(request)
        check_scope(payload)
        preset = store.selected_preset(payload.presentation)
        if preset is None or not preset.presentation or not store.matches(preset, payload.presentation):
            raise HTTPException(409, tr('Vincula y activa un preset para este PowerPoint antes de guardar la diapositiva.'))
        rules = {**preset.rules, payload.index: DisplaySettings.model_validate(effective_settings())}
        replacement = PresetInput(**{**preset.model_dump(exclude={"id"}), "rules": rules})
        persist_preset(lambda: store.replace_preset(preset.id, replacement))
        live_scope, live_values = None, {}
        await broadcast_settings(live=True)
        return await admin_state()

    @app.post("/api/admin/presets", status_code=201)
    async def create_preset(payload: PresetCreateRequest, request: Request):
        require_same_origin(request)
        preset = persist_preset(lambda: store.create_preset(payload.name, payload.copy_from))
        return preset.model_dump(mode="json")

    @app.put("/api/admin/active-preset")
    async def activate_preset(payload: PresetSelection, request: Request):
        nonlocal live_scope, live_values
        require_same_origin(request)
        persist_preset(lambda: store.activate(payload.preset_id))
        live_scope, live_values = None, {}
        await broadcast_settings(restart=True)
        return await admin_state()

    @app.put("/api/admin/presets/{preset_id}")
    async def save_preset(preset_id: str, payload: PresetInput, request: Request):
        nonlocal live_scope, live_values
        require_same_origin(request)
        previous = effective_settings()
        current = current_message()
        before = (store.effective_preset_id(current["presentation"]),
                  store.effective(current["presentation"], current["index"]))
        preset = persist_preset(lambda: store.replace_preset(preset_id, payload))
        after = (store.effective_preset_id(current["presentation"]),
                 store.effective(current["presentation"], current["index"]))
        # An explicit change to the current programmed reading supersedes an
        # earlier temporary adjustment. Editing a future/inactive rule must not
        # disturb the slide that is being read.
        if before != after:
            live_scope, live_values = None, {}
        if previous != effective_settings():
            await broadcast_settings(restart=True)
        return preset.model_dump(mode="json")

    @app.delete("/api/admin/presets/{preset_id}")
    async def delete_preset(preset_id: str, request: Request):
        nonlocal live_scope, live_values
        require_same_origin(request)
        was_active = store.effective_preset_id(current_message()["presentation"]) == preset_id
        persist_preset(lambda: store.delete_preset(preset_id))
        if was_active:
            live_scope, live_values = None, {}
            await broadcast_settings(restart=True)
        return await admin_state()

    async def send(ws: WebSocket, message: dict) -> None:
        try:
            await ws.send_json(message)
        except Exception:
            # Cliente caído: se limpia; el bucle de su conexión acabará solo.
            clients.pop(ws, None)

    async def broadcast_state() -> None:
        current = current_message()
        if role == "master" and current["presentation"] and current["total"]:
            try:
                store.remember_presentation(current["presentation"], current["total"])
            except (OSError, ValueError):
                logging.getLogger(__name__).warning(tr('No se pudo registrar el número de diapositivas del PowerPoint.'))
        slide = wire_slide()
        presentations = current_presentations()
        for ws, client_role in list(clients.items()):
            await send(ws, slide)
            if client_role == CONTROL_ROLE:
                await send(ws, presentations)

    async def handle_command(ws: WebSocket, role: str | None, msg: dict) -> None:
        if app.state.role == "agent":
            await send(ws, error_message(tr('El agente solo entrega notas; la presentación se controla desde PowerPoint.')))
            return
        if role != CONTROL_ROLE:
            await send(ws, error_message(tr('solo el control puede enviar comandos')))
            return
        if upstream is not None or powerpoint is not None:
            await send(ws, error_message(tr('la diapositiva la controla la entrada del agente')))
            return
        kind = msg["type"]
        try:
            if kind == "goto":
                ctrl.goto(msg["index"])
            elif kind == "next":
                ctrl.next()
            elif kind == "prev":
                ctrl.prev()
            elif kind == "select":
                ctrl.select(msg["presentation"])
            elif kind == "load":
                # Se capturan todos los errores: python-pptx lanza varias excepciones
                # distintas ante un .pptx corrupto, y el operador debe verlas en pantalla.
                ctrl.load(msg["path"])
        except Exception as exc:
            await send(ws, error_message(str(exc)))
            return
        await broadcast_state()

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        role: str | None = None
        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = parse_command(raw)
                except ProtocolError as exc:
                    await send(ws, error_message(str(exc)))
                    continue

                if msg["type"] == "hello":
                    role = msg["role"]
                    clients[ws] = role
                    await send(ws, wire_slide())
                    if role == CONTROL_ROLE:
                        await send(ws, current_presentations())
                    continue

                if role is None:
                    await send(ws, error_message(tr('envía primero un mensaje hello')))
                    continue
                await handle_command(ws, role, msg)
        except WebSocketDisconnect:
            pass
        finally:
            clients.pop(ws, None)

    return app
