from dataclasses import replace
import hashlib
import json
from pathlib import Path
import random

import pytest

from romkit_core.analysis.text_scanner import ScannerConfig, TextScanner
from romkit_core.errors import SerializationError, ValidationError
from romkit_core.models import InputImage, ResourceEntry, TextConstraints, TranslationUnit
from romkit_core.project import read_config, read_jsonl, write_jsonl
from romkit_core.project.generator import ProjectGenerator
from romkit_core.validation import validate_translation
from romkit_core.workspace import WorkspaceManager

pytestmark = pytest.mark.unit


def resource(data):
    return ResourceEntry("resource.1", "PSP_GAME/USRDIR/TEXT.BIN", len(data), hashlib.sha256(data).hexdigest())


@pytest.mark.parametrize("encoding,text", [("ascii", "Hello traveller!"), ("utf-8", "¡Hola viajero!"),
    ("utf-16-le", "Hello traveller!"), ("utf-16-be", "Hello traveller!"), ("shift_jis", "こんにちは世界"), ("cp932", "こんにちは世界")])
def test_scanner_exact_offset_bytes_and_terminator(encoding, text):
    prefix = b"\xff\xff\xff\xff\xff"
    raw = text.encode(encoding)
    terminator = b"\x00\x00" if encoding.startswith("utf-16") else b"\x00"
    data = prefix + raw + terminator + b"\xff\xff"
    config = ScannerConfig(encodings=(encoding,))
    candidates = TextScanner(config).scan(memoryview(data), resource(data))
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.offset == len(prefix)
    assert candidate.length_bytes == len(raw)
    assert candidate.text == text and candidate.terminator == terminator
    assert type(candidate).from_json(candidate.to_json()) == candidate
    assert data[candidate.offset:candidate.offset + candidate.length_bytes] == raw


def test_scanner_random_data_is_bounded_and_thresholds_configurable():
    data = random.Random(42).randbytes(65536)
    assert len(TextScanner().scan(data, resource(data))) == 0
    text = b"Hi\x00"
    assert TextScanner().scan(text, resource(text)) == []
    assert TextScanner(ScannerConfig(min_chars=2, encodings=("ascii",))).scan(text, resource(text))[0].text == "Hi"


@pytest.mark.parametrize("header", [b"\x89PNG\r\n\x1a\n", b"\x7fELF", b"PSMF", b"RIFF", b"MIG.00.1PSP", b"~PSP"])
def test_text_scanner_does_not_mistake_binary_assets_for_dialogue(tmp_path, header):
    data = header + b"\0Clear English dialogue\0" + "こんにちは世界".encode("cp932") + b"\0"
    path = tmp_path / "asset.bin"
    path.write_bytes(data)
    assert TextScanner().scan_file(path, resource(data)) == []


@pytest.mark.parametrize("text,encoding", [("偖堷偔扎苓偖堷", "utf-16-le"),
    ("IRIMJjB!I@4ﾅV", "cp932"), ("RNDMBDTXT", "ascii"), ("DEAD1234FF", "ascii")])
def test_raw_script_garbage_and_identifiers_are_rejected(text, encoding):
    data = text.encode(encoding) + (b"\0\0" if encoding.startswith("utf-16") else b"\0")
    assert TextScanner(ScannerConfig(encodings=(encoding,))).scan(data, resource(data)) == []


@pytest.mark.parametrize("data,text", [
    (b"Hello traveller!", "Hello traveller!"),
    (b"\x01Good morning!\x02", "Good morning!"),
    (b"Hello\r\ntraveller!\x00", "Hello\r\ntraveller!"),
    (b"Hello\ntraveller!", "Hello\ntraveller!"),
])
def test_default_scanner_finds_english_without_nul_and_with_line_breaks(data, text):
    candidates = TextScanner().scan(data, resource(data))
    found = next(candidate for candidate in candidates if candidate.text == text)
    assert data[found.offset:found.offset + found.length_bytes].decode(found.encoding) == text
    assert found.terminator == (b"\x00" if data.endswith(b"\x00") else b"")


def test_strict_scanner_can_still_require_nul():
    data = b"Hello traveller!"
    assert TextScanner(ScannerConfig(require_terminator=True)).scan(data, resource(data)) == []


def test_jsonl_reports_file_and_line_and_roundtrips_empty_translations(tmp_path):
    path = tmp_path / "main.jsonl"
    units = [TranslationUnit("t1", "Hello", "", "translated", notes="Vacía intencionadamente"), TranslationUnit("t2", "Goodbye")]
    write_jsonl(path, units)
    assert read_jsonl(path) == units
    first = path.read_bytes()
    write_jsonl(path, units)
    assert path.read_bytes() == first
    with path.open("a", encoding="utf-8") as stream:
        stream.write("{broken}\n")
    with pytest.raises(SerializationError, match="main.jsonl, línea 3"):
        read_jsonl(path)


def test_failed_atomic_save_keeps_original(tmp_path, monkeypatch):
    path = tmp_path / "main.jsonl"
    write_jsonl(path, [TranslationUnit("t", "Source")])
    before = path.read_bytes()
    import romkit_core.project.io as io
    def fail(*args):
        raise OSError("Simulated replacement failure")
    monkeypatch.setattr(io.os, "replace", fail)
    with pytest.raises(OSError):
        write_jsonl(path, [TranslationUnit("t", "Source", "Changed")])
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_generator_is_deterministic_preserves_edits_and_keeps_metadata_local(tmp_path):
    path = tmp_path / "original.iso"
    path.write_bytes(b"synthetic image")
    image = InputImage(path, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest(), selected_platform="psp")
    data = b"Hello traveller!\x00Good morning!\x00"
    candidates = TextScanner(ScannerConfig(encodings=("ascii",))).scan(data, resource(data))
    destination = tmp_path / "project"
    generator = ProjectGenerator()
    first = generator.generate(destination, image, "psp", list(reversed(candidates)))
    text_path = destination / "text/main.jsonl"
    original_text = text_path.read_bytes()
    second = generator.generate(destination, image, "psp", candidates)
    assert first.units == second.units and text_path.read_bytes() == original_text
    assert read_config(destination / "project.toml").source_sha256 == image.sha256
    metadata = WorkspaceManager(destination).read_metadata("reinsert.json")
    assert {entry["id"] for entry in metadata["entries"]} == {unit.id for unit in first.units}
    assert all("offset" not in unit.to_dict() for unit in first.units)
    assert not (destination / "fonts").exists() and not (destination / "graphics").exists()
    changed = replace(first.units[0], target="Hola", status="translated")
    write_jsonl(text_path, [changed, *first.units[1:]])
    third = generator.generate(destination, image, "psp", candidates)
    assert third.units[0] == changed


def test_translation_validates_bytes_encoding_and_token_counts():
    unit = TranslationUnit("t", "Hello {name} {name}", "¡Hola {name}!", "translated", encoding="ascii", constraints=TextConstraints(max_bytes=3), tokens=("{name}",))
    codes = {issue.code for issue in validate_translation(unit).issues}
    assert {"unencodable", "token"} <= codes
    result = validate_translation(replace(unit, target="Hello {name} {name}", encoding="utf-8"))
    assert result.encoded_bytes == len(unit.source.encode("utf-8"))
    assert any(issue.code == "max_bytes" for issue in result.issues)
    assert validate_translation(TranslationUnit("t", "Hello", "", "translated", encoding="ascii")).valid
