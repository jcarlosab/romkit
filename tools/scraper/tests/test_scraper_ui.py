import gc
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import romkit_scraper as ui


@pytest.fixture(scope="module")
def root():
    window = tk.Tk()
    window.withdraw()
    yield window
    window.destroy()


@pytest.fixture
def app(monkeypatch, root):
    class EmptyConfig:
        warning = ""
        def load(self):
            return {}, {}
    monkeypatch.setattr(ui, "ConfigStore", EmptyConfig)
    monkeypatch.setattr(ui, "fetch", lambda url: b"\x89PNG\r\n\x1a\nexample")
    monkeypatch.setattr(ui.App, "make_image", lambda self, *args: tk.PhotoImage(master=self.root, width=1, height=1))
    # Release previous Tk images between fixtures, outside widget creation.
    gc.collect()
    # Icon file decoding is checked in the executable smoke test, not UI fixtures.
    photo_image = tk.PhotoImage
    def fixture_image(*args, **kwargs):
        if kwargs.pop("file", None) is not None:
            kwargs.update(width=64, height=64)
        return photo_image(*args, **kwargs)
    monkeypatch.setattr(tk, "PhotoImage", fixture_image)
    instance = ui.App(root)
    yield instance
    instance.stop.set()
    for callback in root.tk.call("after", "info"):
        root.after_cancel(callback)
    for child in root.winfo_children():
        child.destroy()


def pump(app, predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        app.root.update()
        time.sleep(.01)
    assert predicate()


def test_thumbnails_fit_actual_card_after_tab_becomes_visible(app, monkeypatch):
    sizes = []
    def make_image(data, width, height):
        sizes.append((width, height))
        return tk.PhotoImage(master=app.root, width=1, height=1)
    monkeypatch.setattr(app, "make_image", make_image)
    monkeypatch.setattr(app, "image_data", lambda candidate: b"artwork")
    app.results = [ui.Candidate("Game", "https://example.com/art", "Libretro")]
    app.render_grid()
    pump(app, lambda: hasattr(app.thumbnail_labels[0], "cover_data"))
    app.workspace_tabs.select(app.gallery_tab)
    app.root.deiconify()
    try:
        pump(app, lambda: sizes and sizes[-1][0] > 100 and sizes[-1][1] > 100)
        target = app.thumbnail_labels[0]
        assert sizes[-1] == (target.winfo_width() - 4, target.winfo_height() - 4)
    finally:
        app.root.withdraw()


def test_migration_dialog_copies_without_analysis(app, tmp_path):
    source_root = tmp_path / "source"
    image = source_root / "Art/GBA/Game.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"\x89PNG\r\n\x1a\nexample")
    app.output.set(str(source_root))
    app.open_migration()
    dialog = app.migration_window
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    widgets = list(descendants(dialog))
    entries = [w for w in widgets if w.winfo_class() == "TEntry"]
    assert len(entries) == 2
    app.root.setvar(entries[1].cget("textvariable"), str(tmp_path / "destination"))
    start = next(w for w in widgets if w.winfo_class() == "TButton" and w.cget("text") == "Copiar carátulas")
    start.invoke()
    pump(app, lambda: not app.busy and str(start.cget("state")) == "normal")
    assert (tmp_path / "destination/gba/images/Game.png").read_bytes() == b"\x89PNG\r\n\x1a\nexample"
    assert "1 copiadas" in app.status.get()
    assert image.exists()
    dialog.destroy()


def test_second_click_deselects_and_double_click_preserves_choice(app):
    rom = Path("Game.gba")
    candidate = ui.Candidate("Game", "https://example.com/art", "test")
    app.files = [rom]
    app.games.insert("", "end", iid="0", text=rom.name)
    app.games.selection_set("0")
    app.suggestions[rom] = [candidate]
    app.base_states[rom] = "Coincidencia"
    app.select_rom()
    app.select_cover(0)
    assert app.pending_covers[rom] == candidate
    app.select_cover(0)
    assert not app.pending_covers and app.result_index is None
    assert app.games.set("0", "state") == "Coincidencia"
    assert "Seleccionada" not in app.card_captions[0].cget("text")
    app.select_cover(0)
    app.select_cover(0, toggle=False)
    assert app.pending_covers[rom] == candidate


def test_manual_search_uses_current_platform_and_rejects_stale_results(app, monkeypatch):
    app.library_system = ui.SYSTEMS["GBA"][0]
    app.platform.set("Sony PlayStation 2")
    app.query.set("Game")
    calls = []
    result = ui.Candidate("Game", "https://example.com/ps2", "Libretro")
    monkeypatch.setattr(ui, "libretro", lambda system: calls.append(system) or [result])
    app.find()
    pump(app, lambda: not app.busy)
    assert calls == [ui.SYSTEMS["PS2"][0]]
    assert app.results == [result]
    app.events.put(("results", (None, [], ui.SYSTEMS["GBA"][0])))
    app.poll()
    assert app.results == [result]


def test_platform_switch_does_not_assign_new_art_to_old_library(app):
    rom = Path("Game.gba")
    app.files = [rom]
    app.library_system = ui.SYSTEMS["GBA"][0]
    app.games.insert("", "end", iid="0", text=rom.name)
    app.games.selection_set("0")
    app.platform.set("Sony PlayStation 2")
    assert app.selected_rom() is None
    app.results = [ui.Candidate("Game", "https://example.com/ps2", "SteamGridDB")]
    app.select_cover(0)
    assert not app.pending_covers


def test_manual_steam_search_passes_console_catalog_and_can_disable_filter(app, monkeypatch):
    app.platform.set("Sony PlayStation 2")
    app.source.set("SteamGridDB")
    app.query.set("Game")
    catalog_calls, queries = [], []
    monkeypatch.setattr(ui, "libretro", lambda system: catalog_calls.append(system) or [ui.Candidate("Game (USA)", "https://example.com/art", "Libretro")])
    monkeypatch.setattr(ui, "steamgriddb", lambda query, key, titles: queries.append(titles) or [])
    app.find()
    pump(app, lambda: not app.busy)
    assert catalog_calls == [ui.SYSTEMS["PS2"][0]]
    assert queries == [{"game"}]
    app.platform_filter.set("No")
    app.find()
    pump(app, lambda: not app.busy)
    assert queries[-1] is None and len(catalog_calls) == 1


def test_image_downloads_share_one_request_and_cache(app, monkeypatch):
    started, release = threading.Event(), threading.Event()
    calls, results = [], []
    def fetch(url):
        calls.append(url)
        started.set()
        assert release.wait(2)
        return b"image"
    monkeypatch.setattr(ui, "fetch", fetch)
    candidate = ui.Candidate("Game", "https://example.com/art", "test")
    threads = [threading.Thread(target=lambda: results.append(app.image_data(candidate))) for _ in range(2)]
    threads[0].start()
    assert started.wait(2)
    threads[1].start()
    release.set()
    for thread in threads:
        thread.join(2)
        assert not thread.is_alive()
    assert results == [b"image", b"image"]
    assert app.image_data(candidate) == b"image"
    assert calls == [candidate.url]


def test_gallery_downloads_images_in_parallel(app, monkeypatch):
    started = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    calls = []
    def load(candidate):
        with lock:
            calls.append(candidate.url)
            if len(calls) == 3:
                started.set()
        assert release.wait(2)
        return b"image"
    monkeypatch.setattr(app, "image_data", load)
    app.results = [ui.Candidate("Game", f"https://example.com/{i}", "test") for i in range(3)]
    app.render_grid()
    try:
        assert started.wait(2)
    finally:
        release.set()


def test_rendered_thumbnails_are_reused(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app, "image_data", lambda candidate: b"image")
    def make_image(data, width, height):
        calls.append((width, height))
        return tk.PhotoImage(master=app.root, width=1, height=1)
    monkeypatch.setattr(app, "make_image", make_image)
    app.results = [ui.Candidate("Game", "https://example.com/art", "test")]
    app.workspace_tabs.select(app.gallery_tab)
    app.root.deiconify()
    try:
        app.render_grid()
        pump(app, lambda: 0 in app.thumbnail_images)
        app.root.update()
        before = len(calls)
        app.render_grid()
        pump(app, lambda: 0 in app.thumbnail_images)
        assert len(calls) == before
    finally:
        app.root.withdraw()


def test_progressive_analysis_selection_and_bulk_retry(app, monkeypatch, tmp_path):
    roms = tmp_path / "roms"
    roms.mkdir()
    for name in ("Alpha", "Beta"):
        (roms / (name + ".gba")).touch()
    second_started, release_second = threading.Event(), threading.Event()
    def provider(name, key, platform_titles=None):
        if name == "Beta":
            second_started.set()
            assert release_second.wait(5)
        return [ui.Candidate(name, "https://example.com/" + name, "SteamGridDB")]
    app.platform_filter.set("No")
    monkeypatch.setattr(ui, "steamgriddb", provider)
    app.roms.set(str(roms))
    app.output.set(str(tmp_path / "output"))
    app.analysis_source.set("SteamGridDB")
    app.api_key.set("test")
    app.analyze()
    try:
        pump(app, lambda: second_started.is_set() and app.analyzed_count == 1)
        assert app.busy
        assert app.games.set("0", "state") == "Coincidencia"
        assert app.games.set("1", "state") == "Pendiente"
        app.games.selection_set("0")
        app.select_rom()
        app.select_cover(0)
        alpha = app.pending_covers[app.files[0]]
        assert not app.export.directory().exists()
    finally:
        release_second.set()
    pump(app, lambda: not app.busy)
    app.games.selection_set("1")
    app.select_rom()
    app.select_cover(0)
    app.games.selection_set("0")
    app.select_rom()
    assert app.selected_result() == alpha
    assert len(app.pending_covers) == 2
    def fail_beta(url):
        if url.endswith("Beta"):
            raise OSError("Download failed")
        return b"\x89PNG\r\n\x1a\nexample"
    monkeypatch.setattr(app, "image_data", lambda candidate: fail_beta(candidate.url))
    app.use()
    pump(app, lambda: not app.busy)
    assert app.export.existing(app.files[0])
    assert not app.export.existing(app.files[1])
    assert list(app.pending_covers) == [app.files[1]]
    monkeypatch.setattr(app, "image_data", lambda candidate: b"\x89PNG\r\n\x1a\nexample")
    app.use()
    pump(app, lambda: not app.busy)
    assert app.export.existing(app.files[1])
    assert not app.pending_covers


def test_manual_libretro_loads_catalog_after_other_source(app, monkeypatch):
    app.active_analysis_source = "SteamGridDB"
    app.library_system = ui.SYSTEMS["GBA"][0]
    app.files = [Path("Alpha.gba")]
    app.games.insert("", "end", iid="0", text="Alpha")
    app.games.selection_set("0")
    app.root.update()
    calls = []
    candidate = ui.Candidate("Alpha", "https://example.com/a", "Libretro")
    def load(system):
        calls.append(system)
        return [candidate]
    monkeypatch.setattr(ui, "libretro", load)
    app.source.set("Libretro")
    app.query.set("Alpha")
    app.find()
    pump(app, lambda: not app.busy)
    assert app.results == [candidate]
    assert calls == [ui.SYSTEMS["GBA"][0]]
    app.find()
    pump(app, lambda: not app.busy)
    assert len(calls) == 1


def test_saved_cover_is_first_and_local_preview_works(app, tmp_path):
    rom = tmp_path / "Alpha.gba"
    rom.touch()
    app.files = [rom]
    app.games.insert("", "end", iid="0", text=rom.name)
    app.games.selection_set("0")
    app.export = ui.Export("Cannoli", tmp_path / "output", tmp_path, "GBA", "GBA")
    remote = ui.Candidate("Alpha", "https://example.com/a", "Libretro")
    data = b"\x89PNG\r\n\x1a\nexample"
    destination = app.export.save(rom, remote, data)
    app.suggestions[rom] = [remote]
    app.select_rom()
    saved = app.selected_result()
    assert saved.source == "Imagen guardada"
    assert saved.url == str(destination)
    assert app.image_data(saved) == data
    assert app.results[1] == remote
    app.events.put(("results", (rom, [remote])))
    app.poll()
    assert app.selected_result() == saved
    app.select_cover(0)
    assert not app.pending_covers


def test_chosen_cover_moves_to_first_after_switching_or_searching(app):
    rom = Path("Alpha.gba")
    app.files = [rom]
    app.games.insert("", "end", iid="0", text=rom.name)
    app.games.selection_set("0")
    found = [ui.Candidate("Alpha", f"https://example.com/{index}", "test") for index in range(5)]
    app.suggestions[rom] = found
    app.select_rom()
    app.select_cover(4)
    app.select_rom()
    assert app.results[0] == found[4]
    assert app.result_page == 0
    assert len(app.results) == 5
    app.events.put(("results", (rom, found)))
    app.poll()
    assert app.results[0] == found[4]
    assert app.pending_covers[rom] == found[4]


def test_search_results_stay_with_original_rom(app):
    app.files = [Path("Alpha.gba"), Path("Beta.gba")]
    for index, rom in enumerate(app.files):
        app.games.insert("", "end", iid=str(index), text=rom.name)
    app.games.selection_set("1")
    candidate = ui.Candidate("Alpha", "https://example.com/a", "test")
    app.events.put(("results", (app.files[0], [candidate])))
    app.poll()
    assert app.suggestions[app.files[0]] == [candidate]
    assert not app.results
    app.games.selection_set("0")
    app.select_rom()
    assert app.selected_result() == candidate
    assert not app.pending_covers


def test_long_cover_details_do_not_move_or_clip_analysis_bar(app):
    rom = Path("Alpha.gba")
    app.files = [rom]
    app.games.insert("", "end", iid="0", text=rom.name)
    app.games.selection_set("0")
    app.workspace_tabs.select(app.gallery_tab)
    app.results = [ui.Candidate("Long artwork title " * 30, "https://example.com/a", "SteamGridDB", score=20)]
    app.root.update_idletasks()
    original = (app.progress.winfo_rooty(), app.progress.winfo_height())
    app.select_cover(0)
    app.root.update_idletasks()
    assert (app.progress.winfo_rooty(), app.progress.winfo_height()) == original
    assert app.progress.winfo_height() >= 20
    assert app.progress.winfo_rooty() + app.progress.winfo_height() <= app.root.winfo_rooty() + app.root.winfo_height()


def test_old_provider_preferences_fall_back_without_losing_steam_key(app, monkeypatch):
    legacy_preferences = {"source": "ScreenScraper", "analysis_source": "ScreenScraper"}
    legacy_secrets = {"steamgriddb": "saved-key", "devid": "old-id", "devpassword": "old-password"}
    monkeypatch.setattr(app.config_store, "load", lambda: (legacy_preferences, legacy_secrets))
    app.restore_config()
    assert app.source.get() == "Libretro"
    assert app.analysis_source.get() == "Libretro"
    assert app.api_key.get() == "saved-key"
    saved = []
    monkeypatch.setattr(app.config_store, "save", lambda preferences, secrets: saved.append((preferences, secrets)), raising=False)
    app.save_config()
    assert saved[0][1] == {"steamgriddb": "saved-key"}


def test_stop_analysis_keeps_completed_results_and_skips_next_rom(app, monkeypatch, tmp_path):
    roms = tmp_path / "roms"
    roms.mkdir()
    for name in ("Alpha", "Beta"):
        (roms / (name + ".gba")).touch()
    started, release = threading.Event(), threading.Event()
    calls = []
    def provider(name, key, platform_titles=None):
        calls.append(name)
        started.set()
        assert release.wait(5)
        return [ui.Candidate(name, "https://example.com/a", "SteamGridDB")]
    app.platform_filter.set("No")
    monkeypatch.setattr(ui, "steamgriddb", provider)
    app.roms.set(str(roms))
    app.output.set(str(tmp_path / "output"))
    app.analysis_source.set("SteamGridDB")
    app.api_key.set("test")
    app.analyze()
    try:
        pump(app, lambda: started.is_set() and len(app.files) == 2)
        assert app.stop_analysis_button.instate(["!disabled"])
        app.stop_analysis_button.invoke()
        assert app.stop.is_set()
        assert app.stop_analysis_button.instate(["disabled"])
    finally:
        release.set()
    pump(app, lambda: not app.busy)
    assert calls == ["Alpha"]
    assert app.analyzed_count == 1
    assert app.games.set("0", "state") == "Coincidencia"
    assert app.games.set("1", "state") == "Pendiente"
    assert app.export is not None
    assert app.status.get() == "Análisis cancelado."


def test_preview_arrows_ignore_late_images_and_preserve_choice(app, monkeypatch):
    rom = Path("Alpha.gba")
    app.results = [ui.Candidate(f"Cover {index}", f"https://example.com/{index}", "test") for index in range(8)]
    app.result_index = 5
    app.pending_covers[rom] = app.results[5]
    first_started, release_first = threading.Event(), threading.Event()
    def data(candidate):
        if candidate == app.results[5]:
            first_started.set()
            assert release_first.wait(5)
        return candidate.url.encode()
    received = []
    def make_image(*args):
        received.append(args[0])
        return tk.PhotoImage(master=app.root, width=1, height=1)
    monkeypatch.setattr(app, "image_data", data)
    monkeypatch.setattr(app, "make_image", make_image)
    dialog = app.large_preview()
    controls = dialog.winfo_children()[1]
    buttons = {widget.cget("text"): widget for widget in controls.winfo_children() if widget.winfo_class() == "TButton"}
    try:
        assert first_started.wait(1)
        buttons["›"].invoke()
        pump(app, lambda: bool(received))
        assert dialog.preview_index == 6
        assert received == [app.results[6].url.encode()]
        release_first.set()
        pump(app, lambda: not app.events.empty())
        app.poll()
        assert received == [app.results[6].url.encode()]
        buttons["›"].invoke()
        assert dialog.preview_index == 7
        assert buttons["›"].instate(["disabled"])
        buttons["‹"].invoke()
        assert dialog.preview_index == 6
        assert app.result_index == 5
        assert app.pending_covers[rom] == app.results[5]
    finally:
        release_first.set()
        dialog.destroy()
