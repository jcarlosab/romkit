import struct
import hashlib

import pytest

from romkit_core.analysis.btx import btx_candidates, scan_arcv_text
from romkit_core.analysis.inventory import inventory
from romkit_core.errors import ValidationError
from romkit_core.models import InputImage
from romkit_core.project import read_jsonl
from romkit_core.project.generator import ProjectGenerator
from romkit_core.workspace import WorkspaceManager
from romkit_core.project.arcv_rebuild import patch_btx_resource
from romkit_studio.services.controller import StudioController


def table(texts, header=16):
    raw = bytearray(header + 8 + len(texts) * 8)
    raw[:4] = b"BTX "
    struct.pack_into("<II", raw, 4, 1, header)
    struct.pack_into("<II", raw, header, 1, len(texts))
    for row, text in enumerate(texts):
        pos = header + 8 + row * 8
        struct.pack_into("<II", raw, pos, row, len(raw) - pos)
        raw.extend(text.encode("utf-16-le") + b"\0\0")
    return raw


@pytest.mark.parametrize("header", [12, 16])
def test_btx_recovers_short_strings_controls_and_exact_offsets(header):
    texts = ["", "Hi", "はい", "Hello, <n1001>!\nReady?"]
    raw = table(texts, header)
    candidates = btx_candidates(raw, "dialog.bin")
    assert [c.text for c in candidates] == texts[1:]
    for candidate in candidates:
        assert raw[candidate.offset:candidate.offset + candidate.length_bytes] == candidate.text.encode("utf-16-le")
        assert candidate.terminator == b"\0\0" and candidate.confidence == 1


def test_btx_checks_pointer_table_utf16_and_terminators():
    raw = table(["Hello"])
    with pytest.raises(ValidationError):
        btx_candidates(raw[:-2], "dialog.bin")
    struct.pack_into("<I", raw, 28, 0xffffffff)
    with pytest.raises(ValidationError):
        btx_candidates(raw, "dialog.bin")


def test_btx_writer_rejects_shared_tails_and_tampered_source():
    raw = table(["Hello", "World"])
    # Second record points into the first string rather than its own storage.
    first = 24 + struct.unpack_from("<I", raw, 28)[0]
    struct.pack_into("<I", raw, 36, first + 2 - 32)
    candidate = btx_candidates(raw, "dialog.bin")[0]
    with pytest.raises(ValidationError, match="comparte"):
        patch_btx_resource(raw, "dialog.bin", None, [(candidate, "Hola".encode("utf-16-le"))])
    from dataclasses import replace
    with pytest.raises(ValidationError, match="original"):
        patch_btx_resource(raw, "dialog.bin", None, [(replace(candidate, text="Other"), b"H\0")])
    raw = table(["Hello"])
    raw[32:34] = b"\x00\xd8"
    with pytest.raises(ValidationError):
        btx_candidates(raw, "dialog.bin")


def test_standalone_tutorial_grows_and_relocates_opaque_metadata():
    raw = bytearray(4) + table(['Hi', 'Bye'], header=12)
    raw.extend(bytes((-len(raw)) % 4))
    metadata = len(raw)
    opaque = bytes(range(24))
    struct.pack_into('<I', raw, 0, metadata)
    raw.extend(opaque)
    candidate = btx_candidates(raw, 'tutorial.bin', 4)[0]
    target = 'Hello traveller'.encode('utf-16-le')
    output = patch_btx_resource(raw, 'tutorial.bin', None, [(candidate,target)], experimental=True, capacity=2048)
    new_metadata = struct.unpack_from('<I',output)[0]
    assert len(output) > len(raw) and new_metadata > metadata
    assert output[new_metadata:] == opaque
    assert [c.text for c in btx_candidates(output,'tutorial.bin',4)] == ['Hello traveller','Bye']
    with pytest.raises(ValidationError,match='bloque BTX'):
        patch_btx_resource(raw, 'tutorial.bin', None, [(candidate,target)], experimental=True, capacity=len(raw))


def make_arcv(directory):
    directory.mkdir(parents=True)
    # BTX table in the structure section, text in the shared data section.
    btx = table(["Yes", "Let's start, <n1001>!"])
    structure = 32 + 24 + 16
    raw = bytearray(32) + btx
    raw[:4] = b"KCAP"
    struct.pack_into("<II", raw, 4, 1, structure)
    index = bytearray(88)
    index[:4] = b"VCRA"
    struct.pack_into("<III", index, 4, 0x101, 1, 2048)
    struct.pack_into("<6I", index, 32, len(raw), 0, 88, 0, 56, 0)
    index[56:60] = b"MARV"
    struct.pack_into("<7I", index, 60, 1, structure, 0, len(raw) - structure, 1, 1, 0)
    index.extend(b"Keep/LanguageKeep_jp.res\0")
    path = directory / "ARCVINFO.BIN"
    path.write_bytes(index)
    (directory / "ARCV0.BIN").write_bytes(raw)
    return path


def test_studio_analyzes_arcv_and_exports_to_translator(tmp_path):
    workspace = WorkspaceManager(tmp_path / "workspace")
    index = make_arcv(workspace.layout.area("extracted") / "PSP_GAME/USRDIR")
    logical = "PSP_GAME/USRDIR/ARCVINFO.BIN"
    found, origins = scan_arcv_text(index, logical)
    assert len(found) == 2 and origins[0]["reinsert_supported"] is True
    resources = inventory(workspace.layout.area("extracted"))
    _, candidates = StudioController._analyze(None, resources, workspace, progress=None)
    assert candidates == found
    source = tmp_path / "game.iso"
    source.write_bytes(b"synthetic ISO")
    image = InputImage(source, source.stat().st_size, hashlib.sha256(source.read_bytes()).hexdigest())
    destination = tmp_path / "project"
    ProjectGenerator().generate(destination, image, "psp", candidates, source_language="en", workspace=workspace)
    units = read_jsonl(destination / "text/main.jsonl")
    assert [unit.source for unit in units] == ["Yes", "Let's start, <n1001>!"]
    assert all(unit.encoding == "utf-16-le" for unit in units)
