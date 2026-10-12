import importlib.util
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location("scraper_config", Path(__file__).parents[1] / "scraper_config.py")
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


def test_preferences_round_trip(tmp_path):
    store = config.ConfigStore(tmp_path / "config.json")
    preferences = {"roms": "G:/ROMs", "platform": "Sony PlayStation 2"}
    store.save(preferences, {})
    assert config.ConfigStore(store.path).load() == (preferences, {})


def test_executable_configuration_stays_beside_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "executable", str(tmp_path / "ROMKitScraper.exe"))
    store = config.ConfigStore()
    assert store.path == tmp_path / "scraper_config.json"
    store.save({"source": "Libretro"}, {})
    assert config.ConfigStore().load() == ({"source": "Libretro"}, {})


def test_corrupt_configuration_is_backed_up(tmp_path):
    store = config.ConfigStore(tmp_path / "config.json")
    store.path.write_text("broken")
    assert store.load() == ({}, {})
    assert store.warning
    store.save({"source": "Libretro"}, {})
    assert next(tmp_path.glob("*.bak")).read_text() == "broken"


def test_windows_credentials_are_encrypted_and_can_be_cleared(tmp_path):
    import pytest
    if os.name != "nt":
        pytest.skip("Windows DPAPI")
    store = config.ConfigStore(tmp_path / "config.json")
    secrets = {"steamgriddb": "private-api-key", "sspassword": "private-password"}
    store.save({"source": "SteamGridDB"}, secrets)
    saved = store.path.read_text()
    assert "private-api-key" not in saved
    assert "private-password" not in saved
    loaded = config.ConfigStore(store.path)
    assert loaded.load()[1] == secrets
    loaded.save({}, {})
    assert config.ConfigStore(store.path).load()[1] == {}
