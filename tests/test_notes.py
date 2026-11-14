from __future__ import annotations

import hashlib

import pytest

from notes_prompter.notes import load_deck, read_notes


def test_reads_notes_in_slide_order(make_pptx):
    path = make_pptx("charla", ["primera", "segunda", "tercera"])
    assert read_notes(path) == ["primera", "segunda", "tercera"]


def test_multiline_notes_keep_line_breaks(make_pptx):
    path = make_pptx("charla", ["línea uno\nlínea dos"])
    assert read_notes(path) == ["línea uno\nlínea dos"]


def test_slides_without_notes_yield_empty_string(make_pptx):
    path = make_pptx("charla", ["a", None, "c", None])
    assert read_notes(path) == ["a", "", "c", ""]


def test_presentation_without_slides(make_pptx):
    path = make_pptx("vacia", [])
    deck = load_deck(path)
    assert deck.total == 0
    assert deck.notes == ()


def test_reading_does_not_modify_file(make_pptx):
    path = make_pptx("charla", ["a", None])
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    read_notes(path)
    load_deck(path)
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    assert before == after


def test_deck_name_is_file_stem_and_path_is_absolute(make_pptx):
    path = make_pptx("mi charla", ["x"])
    deck = load_deck(path)
    assert deck.name == "mi charla"
    assert deck.path == str(path.resolve())
    assert deck.total == 1


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_deck(tmp_path / "no-existe.pptx")


def test_rejects_non_pptx_extension(tmp_path):
    path = tmp_path / "notas.txt"
    path.write_text("hola")
    with pytest.raises(ValueError, match=".pptx"):
        load_deck(path)
