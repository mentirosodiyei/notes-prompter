from __future__ import annotations

from pathlib import Path

import pytest
from pptx import Presentation


@pytest.fixture
def make_pptx(tmp_path: Path):
    """Crea un .pptx de prueba. Cada elemento de `notes` es el texto de la nota
    de una diapositiva; None significa diapositiva sin notas."""

    def _make(name: str, notes: list[str | None]) -> Path:
        prs = Presentation()
        layout = prs.slide_layouts[1]
        for note in notes:
            slide = prs.slides.add_slide(layout)
            if note is not None:
                slide.notes_slide.notes_text_frame.text = note
        path = tmp_path / f"{name}.pptx"
        prs.save(path)
        return path

    return _make


@pytest.fixture(autouse=True)
def original_spanish_messages(monkeypatch, request):
    if request.node.get_closest_marker('system_language'):
        return
    from notes_prompter import i18n
    monkeypatch.setattr(i18n, 'get_language', lambda: 'es')
