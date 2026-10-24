import struct
import zlib

import pytest

from romkit_core.analysis.pokapoka import fmg_candidates, scan_archive
from romkit_core.analysis.pokapoka import iter_archive_members
from romkit_core.errors import ValidationError


from pokapoka_builder import make_archive, make_fmg

@pytest.mark.parametrize("compressed", [True, False])
def test_archive_reads_indexed_english_short_labels_and_japanese(tmp_path, compressed):
    raw = make_fmg(["Hi", "Hello\ntraveller!", "こんにちは"])
    make_archive(tmp_path, raw, compressed=compressed)
    before = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    candidates, origins = scan_archive(tmp_path, "PSP_GAME/USRDIR")
    assert [candidate.text for candidate in candidates] == ["Hi", "Hello\ntraveller!", "こんにちは"]
    assert len(origins) == 1 and origins[0]["slot"] == 0
    for candidate in candidates:
        assert candidate.encoding == "cp932" and candidate.confidence == 1
        assert raw[candidate.offset:candidate.offset + candidate.length_bytes].decode("cp932") == candidate.text
        assert candidate.terminator == b"\x00"
    assert {path.name: path.read_bytes() for path in tmp_path.iterdir()} == before


def test_indexed_tables_are_not_limited_to_scanner_quota(tmp_path):
    raw = make_fmg([f"Menu {index}" for index in range(1200)])
    make_archive(tmp_path, raw)
    assert len(scan_archive(tmp_path, "PSP_GAME/USRDIR")[0]) == 1200


def test_repeated_fmg_pointer_is_returned_once():
    raw = bytearray(make_fmg(["First", "Second"]))
    raw[44:48] = raw[40:44]
    assert [c.text for c in fmg_candidates(raw, "Dialog.fmg")] == ["First"]


@pytest.mark.parametrize("offset,value", [(4, 1), (20, 0), (40, 1), (40, 99999)])
def test_invalid_fmg_bounds_are_rejected(offset, value):
    raw = bytearray(make_fmg(["English dialogue"]))
    struct.pack_into("<I", raw, offset, value)
    with pytest.raises(ValidationError):
        fmg_candidates(raw, "Dialog.fmg")


@pytest.mark.parametrize("file,offset,value", [("FAT", 36, 1), ("FAT", 40, 2),
    ("BHD", 32, 99999), ("BHD", 36, 1), ("BHD", 36, 0xFFFFFFFF)])
def test_corrupt_archive_indices_are_rejected(tmp_path, file, offset, value):
    make_archive(tmp_path, make_fmg(["English dialogue"]))
    path = tmp_path / f"POKAPOKA.{file}"
    data = bytearray(path.read_bytes())
    struct.pack_into("<I", data, offset, value)
    path.write_bytes(data)
    with pytest.raises(ValidationError):
        scan_archive(tmp_path, "PSP_GAME/USRDIR")


def test_truncated_compressed_data_is_rejected(tmp_path):
    make_archive(tmp_path, make_fmg(["English dialogue"]))
    path = tmp_path / "POKAPOKA.BND"
    data = bytearray(path.read_bytes())
    data[-1] ^= 0xFF
    path.write_bytes(data)
    with pytest.raises(ValidationError, match="Compresión"):
        scan_archive(tmp_path, "PSP_GAME/USRDIR")


def test_image_traversal_can_report_invalid_entries_without_weakening_strict_reader(tmp_path):
    make_archive(tmp_path, make_fmg(["English dialogue"]))
    path = tmp_path / "POKAPOKA.BHD"
    data = bytearray(path.read_bytes())
    struct.pack_into("<I", data, 32, 99999)
    path.write_bytes(data)
    warnings = []
    assert list(iter_archive_members(tmp_path, "PSP_GAME/USRDIR", on_error=lambda path, message: warnings.append((path, message)))) == []
    assert warnings and "fuera" in warnings[0][1]
    with pytest.raises(ValidationError):
        scan_archive(tmp_path, "PSP_GAME/USRDIR")
