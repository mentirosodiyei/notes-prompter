"""Mac boundaries: live notes, bounded workers, migration and screen coordinates."""
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from notes_prompter.powerpoint_mac import MacPowerPointWatcher
from notes_prompter.screens import screen_from_cocoa
from notes_prompter.settings import default_settings_path, SettingsStore, DisplaySettings


def snapshot(**changes):
    return json.dumps({"name": "Ensayo.pptx", "path": "/presentación/Ensayo.pptx",
                       "index": 3, "total": 5, "notes": 'á\rnota\v"dos"\n', **changes})


def test_mac_uses_real_index_and_live_note_without_reading_disk():
    state = MacPowerPointWatcher.decode(snapshot())
    assert state.index == 3
    assert state.deck.total == 5
    assert state.deck.notes[2] == 'á\nnota\n"dos"\n'
    assert state.deck.name == "Ensayo"
    assert MacPowerPointWatcher.decode(snapshot(notes="edición sin guardar")).deck.notes[2] == "edición sin guardar"
    assert MacPowerPointWatcher.decode("{}") is None


@pytest.mark.parametrize("changes", [{"index": 0}, {"index": 6}, {"total": -1}, {"index": True}, {"notes": None}])
def test_mac_rejects_invalid_snapshot(changes):
    with pytest.raises(ValueError):
        MacPowerPointWatcher.decode(snapshot(**changes))


def test_poll_is_nonblocking_and_has_one_worker(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    watcher = MacPowerPointWatcher(interval=.01)
    def read():
        entered.set()
        release.wait(2)
        return MacPowerPointWatcher.decode(snapshot())
    monkeypatch.setattr(watcher, "_read", read)
    try:
        start = time.monotonic()
        assert watcher.poll() is None
        assert time.monotonic() - start < .1
        assert entered.wait(1)
        worker = watcher._thread
        for _ in range(20):
            watcher.poll()
            assert watcher._thread is worker
        release.set()
        deadline = time.monotonic() + 2
        while watcher.poll() is None and time.monotonic() < deadline:
            time.sleep(.01)
        assert watcher.poll().index == 3
    finally:
        release.set()
        watcher.close()
    assert not worker.is_alive()
    assert watcher.poll() is None


def test_worker_clears_state_on_failure_then_recovers(monkeypatch):
    watcher = MacPowerPointWatcher(interval=.01)
    failure = threading.Event()
    def read():
        if failure.is_set():
            raise RuntimeError("Permiso denegado")
        return MacPowerPointWatcher.decode(snapshot())
    monkeypatch.setattr(watcher, "_read", read)
    def wait_for(check):
        deadline = time.monotonic() + 3
        while not check() and time.monotonic() < deadline:
            time.sleep(.01)
        assert check()
    try:
        watcher.poll()
        wait_for(lambda: watcher.poll() is not None)
        failure.set()
        wait_for(lambda: watcher.error == "Permiso denegado")
        assert watcher.poll() is None
        failure.clear()
        wait_for(lambda: watcher.poll() is not None)
        assert watcher.error is None
    finally:
        watcher.close()


def test_cocoa_points_include_left_and_above_screens_without_retina_scaling():
    def frame(x,y,w,h):
        return SimpleNamespace(origin=SimpleNamespace(x=x,y=y),size=SimpleNamespace(width=w,height=h))
    main = screen_from_cocoa(0, frame(0,0,1512,982), 982)
    left = screen_from_cocoa(1, frame(-1920,0,1920,1080), 982)
    above = screen_from_cocoa(2, frame(0,982,1920,1080), 982)
    assert (main.x, main.y, main.width, main.primary) == (0,0,1512,True)
    assert (left.x, left.y, left.width) == (-1920,-98,1920)
    assert (above.x, above.y) == (0,-1080)


def test_mac_settings_migrate_presets_and_keep_legacy(monkeypatch, tmp_path):
    monkeypatch.setattr(sys,"platform","darwin")
    monkeypatch.delenv("NOTES_PROMPTER_CONFIG",raising=False)
    monkeypatch.setattr(Path,"home",lambda:tmp_path)
    legacy = tmp_path / ".config/NotesPrompter/settings.json"
    store = SettingsStore(legacy)
    preset = store.create_preset("Cliente")
    store.activate(preset.id)
    original = legacy.read_bytes()
    new = default_settings_path()
    assert new == tmp_path / "Library/Application Support/NotesPrompter/settings.json"
    assert SettingsStore(new).document.active_preset_id == preset.id
    assert legacy.read_bytes() == original
    SettingsStore(new).update(DisplaySettings(min_font_px=64))
    assert SettingsStore(default_settings_path()).value.min_font_px == 64
    override = tmp_path / "custom.json"
    monkeypatch.setenv("NOTES_PROMPTER_CONFIG",str(override))
    assert default_settings_path() == override


def test_bad_legacy_settings_do_not_block_startup(monkeypatch, tmp_path):
    monkeypatch.setattr(sys,"platform","darwin")
    monkeypatch.delenv("NOTES_PROMPTER_CONFIG",raising=False)
    monkeypatch.setattr(Path,"home",lambda:tmp_path)
    legacy=tmp_path / ".config/NotesPrompter/settings.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("broken")
    assert not default_settings_path().exists()
    assert legacy.read_text() == "broken"


def test_apple_events_permission_denial_is_actionable(monkeypatch):
    from notes_prompter import powerpoint_mac
    class Process:
        returncode=1
        def communicate(self, timeout):
            return "", "Not authorized (-1743)"
    monkeypatch.setattr(powerpoint_mac.subprocess,"Popen",lambda *a,**k:Process())
    with pytest.raises(RuntimeError,match="Automatización"):
        MacPowerPointWatcher()._read()


def test_timed_out_apple_events_process_is_killed(monkeypatch):
    from notes_prompter import powerpoint_mac
    class Process:
        killed=False
        calls=0
        def communicate(self, timeout=None):
            self.calls+=1
            if self.calls==1:
                raise powerpoint_mac.subprocess.TimeoutExpired("osascript",timeout)
            return "", ""
        def kill(self):
            self.killed=True
    process=Process()
    monkeypatch.setattr(powerpoint_mac.subprocess,"Popen",lambda *a,**k:process)
    watcher=MacPowerPointWatcher(timeout=.1)
    with pytest.raises(RuntimeError,match="no responde"):
        watcher._read()
    assert process.killed
    assert watcher._process is None


@pytest.mark.skipif(sys.platform != "darwin", reason="Cocoa solo está disponible en macOS")
@pytest.mark.skipif(sys.platform != "darwin", reason="Native Cocoa actions")
def test_native_actions_only_enqueue_without_calling_tk():
    import queue
    from notes_prompter.macos import MenuActions
    actions=MenuActions.alloc().init()
    actions.actions=queue.SimpleQueue()
    actions.show_(None)
    actions.admin_(None)
    actions.stop_(None)
    actions.quit_(None)
    assert [actions.actions.get_nowait() for _ in range(4)] == ['open','admin','stop','exit']
