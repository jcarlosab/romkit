import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

spec = importlib.util.spec_from_file_location("scraper_core", Path(__file__).parents[1] / "scraper_core.py")
core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = core
spec.loader.exec_module(core)
PNG = b"\x89PNG\r\n\x1a\nexample"


def test_ambiguous_regions_and_hacks():
    candidates = [core.Candidate("Metroid (USA)", "https://example.com/a", "test"), core.Candidate("Metroid (Europe)", "https://example.com/b", "test")]
    assert core.automatic("Metroid", candidates) == candidates[0]
    assert core.automatic("Metroid (USA)", candidates) == candidates[0]
    assert core.automatic("Metroid [hack]", candidates[:1]) is None
    assert core.search("metroid", candidates) == candidates


def test_dump_names_and_region_preference():
    candidates = [core.Candidate("Pokemon - Emerald Version (Europe) (En,Fr,De,Es,It)", "https://example.com/e", "test"), core.Candidate("Pokemon - Emerald Version (USA)", "https://example.com/u", "test")]
    assert core.automatic("1986 - Pokémon - Emerald Version [!]", candidates, "Europe") == candidates[0]
    assert core.automatic("Pokemon - Emerald Version (USA) [!]", candidates, "Europe") == candidates[1]
    assert core.normalized("Legend of Zelda, The (Europe) (Rev 1)") == core.normalized("The Legend of Zelda")
    assert core.automatic("Pokemon - Emerald Version [hack]", candidates, "Europe") is None


def test_same_title_variants_choose_region_then_closest_name():
    variants = [core.Candidate(name, f"https://example.com/{index}", "test") for index, name in enumerate((
        "Game (USA)", "Game (Europe) (Rev 2)", "Game (Europe) (Rev 1)", "Game 2 (Europe)"))]
    assert core.automatic("Game (Europe) (Rev 1) [!]", variants) == variants[2]
    assert core.automatic("Game", variants, "Europe") in variants[1:3]
    assert core.automatic("Game (U)", variants, "Europe") == variants[0]
    assert core.automatic("Game (Japan)", variants) in variants[:3]
    assert core.automatic("Game", variants, "Europe") == core.automatic("Game", list(reversed(variants)), "Europe")
    assert core.automatic("Game 3", variants) is None
    assert core.automatic("Game [hack]", variants) is None


def test_disc_metadata_does_not_prevent_same_game_match():
    candidate = core.Candidate("Final Fantasy VII (Europe)", "https://example.com/art", "test")
    assert core.automatic("Final Fantasy VII (Europe) (Disc 1)", [candidate]) == candidate
    assert core.automatic("Final Fantasy VIII (Europe) (Disc 1)", [candidate]) is None


def test_indexed_matching_keeps_region_and_sanitized_names():
    candidates = [core.Candidate(name, f"https://example.com/{i}", "Libretro") for i, name in enumerate((
        "Game (Europe) (Rev 1)", "Game (USA)", "R_D (USA)", "Other Game"))]
    index = core.index_candidates(candidates)
    for stem in ("Game", "Game (Europe) (Disc 1)", "R&D (USA)", "Missing"):
        assert core.automatic(stem, candidates, "Europe") == core.automatic(stem, core.indexed_candidates(stem, index), "Europe")


def test_steamgriddb_auto_ranks_matching_portraits_by_rating():
    variants = [core.Candidate("Game · 600×900 · Artist", f"https://example.com/{index}", "SteamGridDB", score=score)
                for index, score in enumerate((None, 2, 20))]
    variants.append(core.Candidate("Game 2 · 600×900 · Artist", "https://example.com/sequel", "SteamGridDB", score=100))
    assert core.automatic_steamgriddb("Game (USA)", variants).url == variants[2].url


def test_steamgriddb_search_and_auth(monkeypatch):
    import json
    calls = []
    def fake_fetch(url, headers):
        calls.append((url, headers))
        data = [{"id": 123, "name": "Pokémon Unbound"}] if "autocomplete" in url else [
            {"id": 456, "url": "https://cdn.example.com/art.png", "mime": "image/png", "width": 600, "height": 900, "author": {"name": "Artist"}},
            {"id": 457, "url": "https://cdn.example.com/other.png", "mime": "image/png", "nsfw": True},
        ]
        return json.dumps({"success": True, "data": data}).encode()
    monkeypatch.setattr(core, "fetch", fake_fetch)
    results = core.steamgriddb("Pokémon Unbound", "example-key")
    assert len(results) == 1
    assert results[0].page == "https://www.steamgriddb.com/grid/456"
    assert calls[0][1]["Authorization"] == "Bearer example-key"
    assert "example-key" not in calls[0][0]


def test_steamgriddb_requires_key():
    import pytest
    with pytest.raises(ValueError, match="clave API"):
        core.steamgriddb("Game", "")


def test_steamgriddb_filters_titles_before_downloading_art(monkeypatch):
    import json
    calls = []
    def fetch(url, headers):
        calls.append(url)
        data = [{"id": 1, "name": "Wrong Game"}, {"id": 2, "name": "Game"}] if "autocomplete" in url else [{"id": 10, "url": "https://example.com/art", "width": 600, "height": 900}]
        return json.dumps({"success": True, "data": data}).encode()
    monkeypatch.setattr(core, "fetch", fetch)
    results = core.steamgriddb("Game", "key", {core.normalized("Game (Europe)")})
    assert len(results) == 1 and results[0].name.startswith("Game ·")
    assert not any("grids/game/1?" in url for url in calls)
    assert any("grids/game/2?" in url for url in calls)


def test_steamgriddb_ranks_scores_before_limiting_artwork(monkeypatch):
    import json
    grids = [{"id": index, "url": f"https://example.com/{index}", "score": index, "width": 600, "height": 900} for index in range(15)]
    grids.append({"id": 99, "url": "https://example.com/99", "score": 1000, "nsfw": True})
    def fake_fetch(url, headers):
        data = [{"id": 1, "name": "Game"}] if "autocomplete" in url else grids
        return json.dumps({"success": True, "data": data}).encode()
    monkeypatch.setattr(core, "fetch", fake_fetch)
    results = core.steamgriddb("Game", "key")
    assert len(results) == 12
    assert [candidate.score for candidate in results] == list(range(14, 2, -1))
    assert core.automatic_steamgriddb("Game", results).url == "https://example.com/14"
    grids[:] = [
        {"id": 1, "url": "https://example.com/missing"},
        {"id": 2, "url": "https://example.com/negative", "score": -2},
        {"id": 3, "url": "https://example.com/invalid", "score": "unknown"},
        {"id": 4, "url": "https://example.com/best", "score": "20"},
    ]
    results = core.steamgriddb("Game", "key")
    assert [candidate.score for candidate in results] == [20, -2, None, None]


def test_steamgriddb_automatic_prefers_portrait_and_rejects_other_games():
    candidates = [core.Candidate("Pokémon Unbound · 920×430 · Artist", "https://example.com/wide", "SteamGridDB"), core.Candidate("Pokémon Unbound · 600×900 · Artist", "https://example.com/portrait", "SteamGridDB")]
    match = core.automatic_steamgriddb("Pokemon Unbound (USA)", candidates)
    assert match.url == "https://example.com/portrait"
    assert match.name == "Pokémon Unbound"
    assert core.automatic_steamgriddb("Pokemon Unbound [hack v2]", candidates) is None
    assert core.automatic_steamgriddb("Pokemon Radical Red", candidates) is None


def test_frontend_exports_and_preservation(tmp_path):
    roms = tmp_path / "roms"
    roms.mkdir()
    rom = roms / "Game [v1].gba"
    rom.write_bytes(b"ROM")
    candidate = core.Candidate("Game & Friends", "https://example.com/a", "test")
    for frontend in core.FRONTENDS:
        export = core.Export(frontend, tmp_path / frontend.replace("/", "-"), roms, "GBA", "gba")
        image = export.save(rom, candidate, PNG)
        assert image.read_bytes() == PNG
        assert export.existing(rom) == image
        export.save(rom, candidate, PNG + b"new")
        assert image.read_bytes() == PNG
        xml = export.xml_path()
        if xml:
            tree = ET.parse(xml)
            assert tree.findtext("game/path") == "./Game [v1].gba"
            assert tree.findtext("game/name") == "Game & Friends"
            assert tree.findtext("game/image") == (None if frontend == "ES-DE" else "./images/Game [v1].png")
            assert xml.with_suffix(".xml.bak").exists()


def test_existing_xml_metadata_is_retained(tmp_path):
    rom = tmp_path / "game.gba"
    export = core.Export("EmulationStation / RetroPie", tmp_path, tmp_path, "GBA", "gba")
    xml = export.xml_path()
    xml.parent.mkdir()
    xml.write_text('<gameList><game><path>./game.gba</path><name>Custom</name><favorite>true</favorite><desc>My description</desc></game></gameList>')
    export.save(rom, core.Candidate("Other", "https://example.com", "test"), PNG)
    tree = ET.parse(xml)
    assert tree.findtext("game/name") == "Custom"
    assert tree.findtext("game/favorite") == "true"
    assert tree.findtext("game/desc") == "My description"


def test_rejects_non_images():
    import pytest
    with pytest.raises(ValueError):
        core.image_extension(b"<html>Error</html>")


def test_invalid_xml_does_not_write_art(tmp_path):
    import pytest
    export = core.Export("ES-DE", tmp_path, tmp_path, "GBA", "gba")
    xml = export.xml_path()
    xml.parent.mkdir(parents=True)
    xml.write_text("<broken>")
    with pytest.raises(ET.ParseError):
        export.save(tmp_path / "game.gba", core.Candidate("Game", "https://example.com", "test"), PNG)
    assert not export.directory().exists()
    assert xml.read_text() == "<broken>"



def test_global_migration_all_frontends_without_roms(tmp_path):
    import json
    for origin in core.FRONTENDS:
        source_root = tmp_path / ("source-" + origin.replace("/", "-"))
        for system, tag in (("gba", "GBA"), ("ps2", "PS2"), ("custom-console", "custom-console")):
            folder = tag if origin == "Cannoli" else system
            source = core.Export(origin, source_root, source_root, folder, folder)
            source.directory().mkdir(parents=True)
            image = source.directory() / "Game.png"
            image.write_bytes(PNG)
            image.with_suffix(".png.source.json").write_text(json.dumps({"source": "Libretro", "license": "Example"}))
        for target in core.FRONTENDS:
            if origin == target:
                continue
            target_root = tmp_path / (origin + target).replace("/", "-")
            result = core.migrate_covers(origin, source_root, target, target_root)
            assert (result["copied"], result["systems"], result["errors"]) == (3, 3, [])
            for system, tag in (("gba", "GBA"), ("ps2", "PS2"), ("custom-console", "custom-console")):
                folder = tag if target == "Cannoli" else system
                destination = core.Export(target, target_root, target_root, folder, folder)
                image = destination.directory() / "Game.png"
                assert image.read_bytes() == PNG
                assert json.loads(image.with_suffix(".png.source.json").read_text())["license"] == "Example"
                assert not (target_root / folder / "Game.gba").exists()
            assert core.migrate_covers(origin, source_root, target, target_root)["existing"] == 3


def test_global_migration_adapts_xml_and_preserves_destination_metadata(tmp_path):
    source_root = tmp_path / "source"
    source = core.Export("EmulationStation / RetroPie", source_root, source_root, "gba", "gba")
    source.directory().mkdir(parents=True)
    image = source.directory() / "custom-box.png"
    image.write_bytes(PNG)
    source.xml_path().write_text('<gameList><game><path>./First.zip</path><name>Source name</name><desc>Description</desc><image>./images/custom-box.png</image><video>old-video.mp4</video></game></gameList>')
    target_root = tmp_path / "target"
    destination = core.Export("EmulationStation / RetroPie", target_root, target_root, "gba", "gba")
    destination.directory().mkdir(parents=True)
    destination.xml_path().write_text('<gameList><game><path>First.zip</path><name>Custom destination</name><favorite>true</favorite></game></gameList>')
    existing = destination.directory() / "First.jpg"
    existing.write_bytes(b"existing artwork")
    result = core.migrate_covers(source.frontend, source_root, destination.frontend, target_root)
    assert (result["copied"], result["existing"], result["unlinked"]) == (0, 1, 0)
    assert existing.read_bytes() == b"existing artwork"
    assert image.read_bytes() == PNG
    tree = ET.parse(destination.xml_path())
    assert len(tree.findall("game")) == 1
    assert tree.findtext("game/name") == "Custom destination"
    assert tree.findtext("game/favorite") == "true"
    assert tree.findtext("game/image") == "./images/First.jpg"
    assert destination.xml_path().with_suffix(".xml.bak").exists()
    esde_root = tmp_path / "esde"
    result = core.migrate_covers(source.frontend, source_root, "ES-DE", esde_root)
    assert result["copied"] == 1
    tree = ET.parse(esde_root / "gamelists/gba/gamelist.xml")
    assert tree.findtext("game/path") == "./First.zip"
    assert tree.findtext("game/desc") == "Description"
    assert tree.findtext("game/image") is None
    assert tree.findtext("game/video") is None


def test_global_migration_stops_and_reports_bad_images(tmp_path):
    import threading
    source_root = tmp_path / "source"
    source = core.Export("Cannoli", source_root, source_root, "GBA", "GBA")
    source.directory().mkdir(parents=True)
    for name in ("Bad", "Good"):
        (source.directory() / (name + ".png")).write_bytes(b"invalid" if name == "Bad" else PNG)
    stop = threading.Event()
    result = core.migrate_covers("Cannoli", source_root, "ES-DE", tmp_path / "target", stop, lambda *_: stop.set())
    assert result["cancelled"] and result["processed"] == 1
    assert len(result["errors"]) == 1
    assert not (tmp_path / "target/downloaded_media/gba/covers/Good.png").exists()


def test_global_migration_no_fabricated_rom_paths_and_nested_art(tmp_path):
    source_root = tmp_path / "source"
    art = source_root / "Art/GBA/subfolder"
    art.mkdir(parents=True)
    (art / "Game.png").write_bytes(PNG)
    target_root = tmp_path / "target"
    result = core.migrate_covers("Cannoli", source_root, "EmulationStation / RetroPie", target_root)
    assert result["copied"] == result["unlinked"] == 1
    assert (target_root / "gba/images/subfolder/Game.png").read_bytes() == PNG
    assert not (target_root / "gba/gamelist.xml").exists()


def test_global_migration_rejects_same_root_and_handles_bad_xml(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="iguales"):
        core.migrate_covers("Cannoli", tmp_path, "Cannoli", tmp_path)
    source = tmp_path / "source"
    (source / "gba/images").mkdir(parents=True)
    (source / "gba/images/Game.png").write_bytes(PNG)
    (source / "gba/gamelist.xml").write_text('<broken>')
    result = core.migrate_covers("EmulationStation / RetroPie", source, "Cannoli", tmp_path / "target")
    assert result["copied"] == 1 and len(result["errors"]) == 1
    assert (tmp_path / "target/Art/GBA/Game.png").exists()


def test_commons_filters_formats_and_keeps_license(monkeypatch):
    import json
    result = {"query": {"pages": {
        "1": {"title": "File:Game cover.png", "imageinfo": [{"mime": "image/png", "url": "https://example.com/cover.png", "descriptionurl": "https://example.com/license", "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}}}]},
        "2": {"title": "File:Logo.svg", "imageinfo": [{"mime": "image/svg+xml"}]},
    }}}
    monkeypatch.setattr(core, "fetch", lambda url: json.dumps(result).encode())
    candidates = core.commons("Game")
    assert len(candidates) == 1
    assert candidates[0].license == "CC BY-SA 4.0"
    assert candidates[0].page == "https://example.com/license"
