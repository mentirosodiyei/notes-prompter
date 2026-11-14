"""Lectura de las notas del orador de un .pptx sin modificar el archivo."""

from __future__ import annotations

from .i18n import tr

from dataclasses import dataclass
from pathlib import Path

from pptx import Presentation


@dataclass(frozen=True)
class Deck:
    """Presentación cargada: nombre (nombre del archivo sin extensión) y notas por diapositiva."""

    name: str
    path: str
    notes: tuple[str, ...]

    @property
    def total(self) -> int:
        return len(self.notes)


def read_notes(path: str | Path) -> list[str]:
    """Devuelve la nota de cada diapositiva, en orden. Vacía si no tiene notas.

    No se llama a ``notes_slide`` sin comprobar ``has_notes_slide``: así no se crea
    ninguna diapositiva de notas en memoria. Nunca se guarda el archivo.
    """
    prs = Presentation(str(path))
    notes: list[str] = []
    for slide in prs.slides:
        text = ""
        if slide.has_notes_slide:
            frame = slide.notes_slide.notes_text_frame
            if frame is not None:
                text = frame.text
        notes.append(text)
    return notes


def load_deck(path: str | Path) -> Deck:
    """Carga un .pptx existente. Lanza FileNotFoundError o ValueError si no es válido."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(tr('no existe el archivo: {0}', f'{p}'))
    if p.suffix.lower() != ".pptx":
        raise ValueError(tr('solo se admiten archivos .pptx'))
    return Deck(name=p.stem, path=str(p.resolve()), notes=tuple(read_notes(p)))


def presentation_metadata(data: bytes, filename: str) -> tuple[str, int]:
    """Inspect only slide IDs in an uploaded Office ZIP; never load or save slides."""
    from io import BytesIO
    from zipfile import ZipFile, BadZipFile
    from lxml import etree

    name = Path(filename.replace("\\", "/")).name
    if Path(name).suffix.casefold() not in {".pptx", ".pptm"}:
        raise ValueError(tr('Selecciona un archivo .pptx o .pptm.'))
    try:
        with ZipFile(BytesIO(data)) as archive:
            entry = archive.getinfo("ppt/presentation.xml")
            if entry.file_size > 2 * 1024 * 1024:
                raise ValueError(tr('Los metadatos del PowerPoint son demasiado grandes.'))
            xml = archive.read(entry)
        if b"<!DOCTYPE" in xml.upper():
            raise ValueError(tr('El PowerPoint contiene metadatos no admitidos.'))
        tree = etree.fromstring(xml, etree.XMLParser(resolve_entities=False, no_network=True))
        total = len(tree.findall("{http://schemas.openxmlformats.org/presentationml/2006/main}sldIdLst/{http://schemas.openxmlformats.org/presentationml/2006/main}sldId"))
        if not 1 <= total <= 99999:
            raise ValueError(tr('El PowerPoint no contiene diapositivas válidas.'))
        return Path(name).stem, total
    except (BadZipFile, KeyError, etree.XMLSyntaxError, RuntimeError) as exc:
        raise ValueError(tr('No se pudo leer el número de diapositivas del PowerPoint.')) from exc
