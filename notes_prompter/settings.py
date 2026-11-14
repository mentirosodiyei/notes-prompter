"""Preferencias y presets de ensayo con reglas por diapositiva."""
from __future__ import annotations

from .i18n import tr

import os
import sys
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DisplaySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_scroll: bool = Field(default=True, strict=True)
    font_mode: Literal["auto", "fixed"] = "auto"
    min_font_px: int = Field(default=48, ge=24, le=600, strict=True)
    speed_px_s: float = Field(default=24, ge=-200, le=200, allow_inf_nan=False, strict=True)
    start_delay_s: float = Field(default=3, ge=0, le=30, allow_inf_nan=False, strict=True)


SlideNumber = Annotated[int, Field(ge=1, le=99999)]


class PresetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    presentation: str | None = Field(default=None, max_length=255)
    presentation_total: int | None = Field(default=None, ge=1, le=99999)
    defaults: DisplaySettings = Field(default_factory=DisplaySettings)
    rules: dict[SlideNumber, DisplaySettings] = Field(default_factory=dict, max_length=2000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError(tr('El preset necesita un nombre.'))
        return value

    @field_validator("presentation")
    @classmethod
    def clean_presentation(cls, value):
        return (value.strip() or None) if value is not None else None


class Preset(PresetInput):
    id: str = Field(min_length=1, max_length=64)


def presentation_key(name: str) -> str:
    value = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    for suffix in (".pptx", ".pptm", ".ppt"):
        if value.casefold().endswith(suffix):
            value = value[:-len(suffix)]
            break
    return value.casefold()


class PresentationInfo(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    total: int = Field(ge=1, le=99999)


class StoredSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[3] = 3
    auto_select_presentation: bool = True
    presentations: dict[str, PresentationInfo] = Field(default_factory=dict, max_length=200)
    presentation_presets: dict[str, str] = Field(default_factory=dict, max_length=200)
    display_settings: DisplaySettings = Field(default_factory=DisplaySettings)
    presets: list[Preset] = Field(default_factory=list, max_length=200)
    active_preset_id: str | None = None

    @model_validator(mode="after")
    def unique_presets(self):
        ids = [preset.id for preset in self.presets]
        names = [preset.name.casefold() for preset in self.presets]
        if len(set(ids)) != len(ids) or len(set(names)) != len(names):
            raise ValueError(tr('Hay presets duplicados.'))
        if self.active_preset_id is not None and self.active_preset_id not in ids:
            raise ValueError(tr('No existe el preset activo.'))
        return self


class SettingsStore:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.document = StoredSettings()
        self.load_error = None
        if path is not None and path.is_file():
            try:
                import json
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "version" in data:
                    self.document = decode_settings(data)
                    if data.get("version") == 2:
                        backup = path.with_suffix(".v2-backup.json")
                        if not backup.exists():
                            try:
                                backup.write_bytes(path.read_bytes())
                            except OSError:
                                pass
                else:
                    self.document = StoredSettings(display_settings=DisplaySettings.model_validate(data))
            except (OSError, ValueError):
                self.load_error = tr("No se pudo leer la configuración. El archivo se conserva; restaura una copia válida antes de guardar.")

    @property
    def value(self):
        return self.document.display_settings

    def _commit(self, document: StoredSettings):
        if self.load_error:
            raise OSError(self.load_error)
        document = StoredSettings.model_validate(document.model_dump())
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(document.model_dump_json(indent=2), encoding="utf-8")
            os.replace(temporary, self.path)
        self.document = document

    def update(self, value: DisplaySettings) -> None:
        document = self.document.model_copy(deep=True)
        document.display_settings = value
        self._commit(document)

    def get_preset(self, preset_id: str) -> Preset:
        for preset in self.document.presets:
            if preset.id == preset_id:
                return preset.model_copy(deep=True)
        raise KeyError(tr('El preset ya no existe.'))

    def _check_name(self, name: str, excluding: str | None = None):
        if any(p.id != excluding and p.name.casefold() == name.casefold() for p in self.document.presets):
            raise ValueError(tr('Ya existe un preset con ese nombre.'))

    def create_preset(self, name: str | None = None, copy_from: str | None = None):
        if len(self.document.presets) >= 200:
            raise ValueError(tr('Se ha alcanzado el límite de 200 presets.'))
        source = self.get_preset(copy_from) if copy_from is not None else None
        if name is None:
            base = f"{source.name[:60]} {tr('(copia)')}" if source else tr('Nuevo preset')
            name = base
            number = 2
            while any(p.name.casefold() == name.casefold() for p in self.document.presets):
                name = f"{base} {number}"
                number += 1
        payload = PresetInput(name=name, presentation=source.presentation if source else None,
                              presentation_total=source.presentation_total if source else None,
                              defaults=source.defaults if source else self.value,
                              rules=source.rules if source else {})
        self._check_name(payload.name)
        preset = Preset(id=uuid4().hex, **payload.model_dump())
        document = self.document.model_copy(deep=True)
        document.presets.append(preset)
        self._commit(document)
        return preset.model_copy(deep=True)

    def replace_preset(self, preset_id: str, payload: PresetInput):
        previous = self.get_preset(preset_id)
        self._check_name(payload.name, excluding=preset_id)
        if payload.presentation:
            known = self.document.presentations.get(presentation_key(payload.presentation))
            total = known.total if known else payload.presentation_total
            if total is not None and any(index > total and (index not in previous.rules or rule != previous.rules[index])
                                         for index, rule in payload.rules.items()):
                raise ValueError(tr('Este PowerPoint tiene {0} diapositivas. Revisa las reglas fuera de rango.', f'{total}'))
            payload = payload.model_copy(update={"presentation_total": total})
        replacement = Preset(id=preset_id, **payload.model_dump())
        document = self.document.model_copy(deep=True)
        document.presets = [replacement if p.id == preset_id else p for p in document.presets]
        key = presentation_key(replacement.presentation) if replacement.presentation else None
        document.presentation_presets = {k: v for k, v in document.presentation_presets.items()
                                         if v != preset_id or k == key}
        if key:
            document.presentation_presets.setdefault(key, preset_id)
        self._commit(document)
        return replacement.model_copy(deep=True)

    def activate(self, preset_id: str | None):
        if preset_id is not None:
            self.get_preset(preset_id)
        document = self.document.model_copy(deep=True)
        document.active_preset_id = preset_id
        if preset_id is None:
            document.auto_select_presentation = False
        else:
            preset = self.get_preset(preset_id)
            if preset.presentation:
                document.presentation_presets[presentation_key(preset.presentation)] = preset_id
        self._commit(document)

    def delete_preset(self, preset_id: str):
        self.get_preset(preset_id)
        document = self.document.model_copy(deep=True)
        document.presets = [p for p in document.presets if p.id != preset_id]
        document.presentation_presets = {k: v for k, v in document.presentation_presets.items() if v != preset_id}
        if document.active_preset_id == preset_id:
            document.active_preset_id = None
        self._commit(document)

    def remember_presentation(self, name: str, total: int):
        info = PresentationInfo(name=name, total=total)
        key = presentation_key(name)
        if self.document.presentations.get(key) != info:
            if key not in self.document.presentations and len(self.document.presentations) >= 200:
                raise ValueError(tr('Se ha alcanzado el límite de 200 PowerPoint registrados.'))
            document = self.document.model_copy(deep=True)
            document.presentations[key] = info
            self._commit(document)
        return info

    def set_automatic(self, enabled: bool):
        document = self.document.model_copy(deep=True)
        document.auto_select_presentation = enabled
        self._commit(document)

    def selected_preset(self, presentation: str | None) -> Preset | None:
        if self.document.auto_select_presentation and presentation:
            key = presentation_key(presentation)
            matches = [p for p in self.document.presets if p.presentation and presentation_key(p.presentation) == key]
            preferred = self.document.presentation_presets.get(key)
            if matches:
                return next((p for p in matches if p.id == preferred), matches[0]).model_copy(deep=True)
        return self.get_preset(self.document.active_preset_id) if self.document.active_preset_id else None

    def matches(self, preset: Preset, presentation: str | None):
        return preset.presentation is None or bool(presentation and presentation_key(preset.presentation) == presentation_key(presentation))

    def effective_preset_id(self, presentation: str | None):
        preset = self.selected_preset(presentation)
        return preset.id if preset and self.matches(preset, presentation) else None

    def effective(self, presentation: str | None, index: int) -> DisplaySettings:
        preset = self.selected_preset(presentation)
        if preset is None or not self.matches(preset, presentation):
            return self.value
        return preset.rules.get(index, preset.defaults)

    def context(self, presentation: str | None, index: int) -> dict:
        preset = self.selected_preset(presentation)
        if preset is None:
            return {"preset": None, "matches": True, "rule_slide": None}
        matches = self.matches(preset, presentation)
        return {"preset": preset.name, "matches": matches,
                "rule_slide": index if matches and index in preset.rules else None}


def decode_settings(data):
    if isinstance(data, dict) and data.get("version") == 2:
        data = {**data, "version": 3}
    return StoredSettings.model_validate(data)


def default_settings_path() -> Path:
    override = os.environ.get("NOTES_PROMPTER_CONFIG")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        destination = Path.home() / "Library/Application Support/NotesPrompter/settings.json"
        legacy = Path.home() / ".config/NotesPrompter/settings.json"
        if not destination.exists() and legacy.is_file():
            # Validate before migrating; keep the old file untouched.
            import json
            try:
                data = json.loads(legacy.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "version" in data:
                    document = decode_settings(data)
                else:
                    document = StoredSettings(display_settings=DisplaySettings.model_validate(data))
                SettingsStore(destination)._commit(document)
            except (OSError, ValueError):
                # An unreadable legacy file must not prevent the application opening.
                pass
        return destination
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".config"))) / "NotesPrompter" / "settings.json"
