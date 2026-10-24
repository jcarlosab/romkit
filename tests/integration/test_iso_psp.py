import hashlib
from pathlib import Path

import pytest

from iso_builder import make_iso
from romkit_core.analysis.inventory import inventory
from romkit_core.errors import PlatformError
from romkit_core.image import ImageService
from romkit_core.platforms import PlatformImage, PlatformRegistry
from romkit_core.platforms.iso9660 import Iso9660Reader, IsoEntry, normalize_iso_path
from romkit_core.platforms.psp import PspBackend

pytestmark = pytest.mark.integration


def test_iso_read_extract_psp_identity_and_inventory(tmp_path):
    original = tmp_path / "fixture.iso"
    files = make_iso(original)
    before = original.read_bytes(), original.stat().st_mtime_ns
    reader = Iso9660Reader()
    with reader.open(original) as iso:
        entries = list(reader.walk(iso))
        assert {entry.logical_path for entry in entries if not entry.is_directory} == set(files)
        reader.extract_all(iso, tmp_path / "plain")
    for path, data in files.items():
        assert (tmp_path / "plain" / path).read_bytes() == data
    assert (tmp_path / "plain/PSP_GAME/EMPTY").is_dir()
    backend = PspBackend()
    assert backend.probe(original).confidence >= 0.9
    registry = PlatformRegistry()
    registry.register(backend)
    values = []
    inspection = ImageService(registry).inspect(original, progress=values.append)
    assert inspection.image.sha256 == hashlib.sha256(before[0]).hexdigest()
    assert inspection.image.detected_platform == "psp"
    image = ImageService(registry).select_platform(inspection, "psp")
    result = backend.extract(PlatformImage("psp", image), tmp_path / "extracted")
    assert len(result.resources) == len(files)
    assert list(result.resources) == inventory(tmp_path / "extracted")
    assert any(r.type_status == "known" and r.detected_type == "elf" for r in result.resources)
    assert any(r.type_status == "unknown" for r in result.resources)
    assert (original.read_bytes(), original.stat().st_mtime_ns) == before
    assert values[-1].completed == values[-1].total


def test_generic_iso_and_manual_platform(tmp_path):
    original = tmp_path / "generic.iso"
    make_iso(original, psp=False)
    registry = PlatformRegistry()
    registry.register(PspBackend())
    service = ImageService(registry)
    result = service.inspect(original)
    assert result.candidates == () and result.image.detected_platform is None
    assert service.select_platform(result, "psp").selected_platform == "psp"


@pytest.mark.parametrize("path", ["../evil", "/DIR/../evil", "C:/evil", "DIR\\evil", "/NUL.TXT;1", "/a//b"])
def test_unsafe_iso_names(path):
    with pytest.raises(PlatformError):
        normalize_iso_path(path)


def test_manipulated_entry_and_existing_original_are_protected(tmp_path):
    path = tmp_path / "fixture.iso"
    make_iso(path)
    reader = Iso9660Reader()
    with reader.open(path) as image:
        with pytest.raises(PlatformError):
            reader.extract_file(image, IsoEntry("../escape", "/README.TXT;1", 10), tmp_path / "output")
        with pytest.raises(PlatformError, match="original"):
            reader.extract_file(image, IsoEntry("fixture.iso", "/README.TXT;1", 10), tmp_path)


def test_stream_hash_large_file_and_changed_input(tmp_path):
    path = tmp_path / "large.bin"
    path.write_bytes(b"fixture" * 400000)
    result = ImageService(PlatformRegistry()).inspect(path)
    assert result.image.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
