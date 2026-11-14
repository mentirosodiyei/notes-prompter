from __future__ import annotations

from types import SimpleNamespace

import pytest

from notes_prompter.powerpoint import PowerPointWatcher, read_deck


class FakeCollection:
    """Imita las colecciones de COM: Count y acceso por índice base 1 con llamada."""

    def __init__(self, items):
        self._items = list(items)

    @property
    def Count(self):
        return len(self._items)

    def __call__(self, index):
        return self._items[index - 1]


def fake_slide(text):
    body = SimpleNamespace(PlaceholderFormat=SimpleNamespace(Type=2), TextFrame=SimpleNamespace(TextRange=SimpleNamespace(Text=text)))
    notes_page = SimpleNamespace(Shapes=SimpleNamespace(Placeholders=FakeCollection([body])))
    return SimpleNamespace(NotesPage=notes_page)


def fake_presentation(name, notes, path=None):
    slides = FakeCollection(fake_slide(n) for n in notes)
    return SimpleNamespace(Name=f"{name}.pptx", FullName=path or f"C:\\charlas\\{name}.pptx", Slides=slides)


def fake_app(presentation, edit_index=1, show=None):
    """`show` = (presentación, posición) si hay proyección en curso."""
    shows = FakeCollection([])
    if show is not None:
        pres, position = show
        view = SimpleNamespace(CurrentShowPosition=position, Slide=SimpleNamespace(SlideIndex=position))
        shows = FakeCollection([SimpleNamespace(Presentation=pres, View=view)])
    window = SimpleNamespace(View=SimpleNamespace(Slide=SimpleNamespace(SlideIndex=edit_index)))
    return SimpleNamespace(ActivePresentation=presentation, SlideShowWindows=shows, ActiveWindow=window)


def test_read_deck_takes_notes_name_and_path():
    pres = fake_presentation("charla", ["uno", "dos"])
    deck = read_deck(pres)
    assert deck.name == "charla"
    assert deck.path == "C:\\charlas\\charla.pptx"
    assert deck.notes == ("uno", "dos")


def test_read_deck_normalizes_paragraph_and_line_breaks():
    pres = fake_presentation("charla", ["a\rb\x0bc\r\nd"])
    assert read_deck(pres).notes == ("a\nb\nc\nd",)


def test_slide_without_notes_body_is_empty():
    broken = SimpleNamespace(NotesPage=SimpleNamespace(Shapes=SimpleNamespace(
        Placeholders=lambda i: (_ for _ in ()).throw(IndexError()))))
    pres = SimpleNamespace(Name="x.pptx", FullName="x.pptx", Slides=FakeCollection([broken]))
    assert read_deck(pres).notes == ("",)


def test_edit_mode_follows_selected_slide():
    pres = fake_presentation("charla", ["uno", "dos", "tres"])
    watcher = PowerPointWatcher(app=fake_app(pres, edit_index=2))
    state = watcher.poll()
    assert state.index == 2
    assert state.deck.notes == ("uno", "dos", "tres")


def test_slideshow_position_wins_over_edit_window():
    pres = fake_presentation("charla", ["uno", "dos", "tres"])
    watcher = PowerPointWatcher(app=fake_app(pres, edit_index=1, show=(pres, 3)))
    state = watcher.poll()
    assert (state.index, state.deck.notes[state.index - 1]) == (3, "tres")


class AppWithoutPresentation:
    @property
    def ActivePresentation(self):
        raise RuntimeError("PowerPoint abierto sin presentación")


def test_no_presentation_open_returns_none():
    assert PowerPointWatcher(app=AppWithoutPresentation()).poll() is None


def test_deck_is_cached_while_slide_count_is_unchanged():
    pres = fake_presentation("charla", ["uno", "dos"])
    watcher = PowerPointWatcher(app=fake_app(pres, edit_index=1))
    first = watcher.poll().deck
    second = watcher.poll().deck
    assert first is second


def test_notes_body_can_be_first_placeholder():
    slide = fake_slide("nota correcta")
    body = slide.NotesPage.Shapes.Placeholders(1)
    footer = SimpleNamespace(PlaceholderFormat=SimpleNamespace(Type=15),
                             TextFrame=SimpleNamespace(TextRange=SimpleNamespace(Text="pie")))
    slide.NotesPage.Shapes.Placeholders = FakeCollection([footer, body])
    pres = fake_presentation("plantilla", [])
    pres.Slides = FakeCollection([slide])
    assert read_deck(pres).notes == ("nota correcta",)
    slide.NotesPage.Shapes.Placeholders = FakeCollection([body, footer])
    assert read_deck(pres).notes == ("nota correcta",)


def test_footer_is_never_used_as_notes():
    slide = fake_slide("pie de página")
    slide.NotesPage.Shapes.Placeholders(1).PlaceholderFormat.Type = 15
    pres = fake_presentation("sin cuerpo", [])
    pres.Slides = FakeCollection([slide])
    assert read_deck(pres).notes == ("",)


def test_slideshow_uses_slide_index_instead_of_show_position():
    pres = fake_presentation("personalizada", ["uno", "dos", "tres"])
    app = fake_app(pres, show=(pres, 3))
    app.SlideShowWindows(1).View.CurrentShowPosition = 1
    assert PowerPointWatcher(app).poll().index == 3


def test_show_does_not_need_active_presentation():
    pres = fake_presentation("proyección", ["uno"])
    app = fake_app(pres, show=(pres, 1))
    del app.ActivePresentation
    assert PowerPointWatcher(app).poll().deck.name == "proyección"


def test_disconnected_com_is_replaced_on_next_poll(monkeypatch):
    pres = fake_presentation("reabierta", ["uno"])
    watcher = PowerPointWatcher(AppWithoutPresentation())
    assert watcher.poll() is None
    assert watcher._app is None
    monkeypatch.setattr(watcher, "_connect", lambda: fake_app(pres))
    assert watcher.poll().deck.name == "reabierta"


def test_missing_edit_window_does_not_invent_slide_one():
    pres = fake_presentation("sin ventana", ["uno"])
    app = fake_app(pres)
    del app.ActiveWindow
    assert PowerPointWatcher(app).poll() is None


@pytest.mark.parametrize("slideshow", [False, True])
def test_unsaved_note_edits_are_read_on_same_slide_without_reopening(slideshow):
    pres = fake_presentation("charla", ["original", "siguiente"])
    app = fake_app(pres, show=(pres, 1) if slideshow else None)
    watcher = PowerPointWatcher(app)
    before = watcher.poll()
    pres.Slides(1).NotesPage.Shapes.Placeholders(1).TextFrame.TextRange.Text = "editada\rnueva línea"
    after = watcher.poll()
    assert after.index == before.index == 1
    assert after.deck.notes[0] == "editada\nnueva línea"
    assert before.deck.notes[0] == "original"  # broadcast comparison stays immutable
    pres.Slides(1).NotesPage.Shapes.Placeholders(1).TextFrame.TextRange.Text = ""
    assert watcher.poll().deck.notes[0] == ""
    assert watcher._app is app


def test_notes_edited_on_another_slide_are_fresh_when_selected():
    pres = fake_presentation("charla", ["primera", "original segunda"])
    app = fake_app(pres)
    watcher = PowerPointWatcher(app)
    watcher.poll()
    pres.Slides(2).NotesPage.Shapes.Placeholders(1).TextFrame.TextRange.Text = "segunda editada"
    app.ActiveWindow.View.Slide.SlideIndex = 2
    assert watcher.poll().deck.notes[1] == "segunda editada"


def test_steady_poll_only_reads_the_current_notes_page():
    pres = fake_presentation("larga", ["nota"] * 100)
    watcher = PowerPointWatcher(fake_app(pres, edit_index=60))
    watcher.poll()
    class Unreadable:
        @property
        def NotesPage(self):
            pytest.fail("No debe releer todas las diapositivas en cada sondeo")
    pres.Slides._items[0] = Unreadable()
    assert watcher.poll().deck.notes[59] == "nota"
