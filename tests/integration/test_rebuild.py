from dataclasses import replace
import struct
import time

import pytest

from iso_builder import make_iso
from pokapoka_builder import make_archive, make_fmg
from romkit_core.analysis.pokapoka import scan_archive
from romkit_core.errors import ValidationError
from romkit_core.image import ImageService
from romkit_core.platforms import PlatformRegistry
from romkit_core.platforms.iso9660 import Iso9660Reader
from romkit_core.platforms.psp import PspBackend
from romkit_core.project import read_jsonl, write_jsonl
from romkit_core.project.generator import ProjectGenerator
from romkit_core.project.rebuild import rebuild_project, _compress
from romkit_core.tasks import TaskCancelled
from romkit_core.workspace import WorkspaceManager


@pytest.fixture
def build_context(tmp_path, request):
    archive = tmp_path / "archive"
    make_archive(archive, make_fmg(["Hello traveller", "Good morning", "Pending source"]),
                 compressed=getattr(request, "param", True))
    # Real archive slots are aligned and padded; allow compression growth in the slot.
    bnd = archive / "POKAPOKA.BND"
    bnd.write_bytes(bnd.read_bytes().ljust(2048, b"\0"))
    bhd = bytearray((archive / "POKAPOKA.BHD").read_bytes())
    struct.pack_into("<I", bhd, 12, 2048)
    (archive / "POKAPOKA.BHD").write_bytes(bhd)
    files = {f"PSP_GAME/USRDIR/{path.name}": path.read_bytes() for path in archive.iterdir()}
    source = tmp_path / "original.iso"
    make_iso(source, extra_files=files)
    registry = PlatformRegistry()
    registry.register(PspBackend())
    service = ImageService(registry)
    image = service.select_platform(service.inspect(source), "psp")
    workspace = WorkspaceManager(tmp_path / "workspace")
    workspace.register_source(image)
    candidates, origins = scan_archive(archive, "PSP_GAME/USRDIR")
    workspace.write_metadata("archive_resources.json", {"resources": origins})
    project = tmp_path / "translated"
    generated = ProjectGenerator().generate(project, image, "psp", candidates, workspace=workspace, source_language="en")
    units = list(generated.units)
    units[0] = replace(units[0], target="Hola viajero", status="translated")
    units[1] = replace(units[1], target="", status="reviewed")
    write_jsonl(project / "text/main.jsonl", units)
    return project, workspace, image, tmp_path / "translated.iso"


@pytest.mark.parametrize("build_context", [True, False], indirect=True)
def test_rebuild_roundtrip_preserves_iso_layout_source_and_pending_text(build_context, tmp_path):
    project, workspace, image, output = build_context
    original = image.path.read_bytes()
    result = rebuild_project(project, workspace, image, output)
    assert (result.translated, result.skipped, result.tables) == (2, 1, 1)
    assert image.path.read_bytes() == original
    assert output.stat().st_size == len(original)
    reader = Iso9660Reader()
    extracted = tmp_path / "rebuilt"
    with reader.open(image.path) as first, reader.open(output) as second:
        before = list(reader.walk(first))
        after = list(reader.walk(second))
        assert before == after
        for entry in before:
            assert first._handle.get_record(iso_path=entry.iso_path).extent_location() == second._handle.get_record(iso_path=entry.iso_path).extent_location()
            if not entry.is_directory and not entry.logical_path.endswith(("POKAPOKA.BHD", "POKAPOKA.BND")):
                assert b"".join(reader.read_chunks(first, entry)) == b"".join(reader.read_chunks(second, entry))
        reader.extract_all(second, extracted)
    found, _ = scan_archive(extracted / "PSP_GAME/USRDIR", "PSP_GAME/USRDIR")
    assert [candidate.text for candidate in found] == ["Hola viajero", "Pending source"]


@pytest.mark.parametrize("target", ["X" * 100, "Hola 🌍", "bad\0text"])
def test_invalid_translation_produces_no_output(build_context, target):
    project, workspace, image, output = build_context
    path = project / "text/main.jsonl"
    units = read_jsonl(path)
    units[0] = replace(units[0], target=target)
    write_jsonl(path, units)
    with pytest.raises(ValidationError):
        rebuild_project(project, workspace, image, output)
    assert not output.exists()


def test_changed_source_text_and_offsets_are_rejected(build_context):
    project, workspace, image, output = build_context
    path = project / "text/main.jsonl"
    units = read_jsonl(path)
    units[0] = replace(units[0], source="Tampered source")
    write_jsonl(path, units)
    with pytest.raises(ValidationError, match="original"):
        rebuild_project(project, workspace, image, output)
    assert not output.exists()


def test_no_translations_and_wrong_image_are_rejected(build_context):
    project, workspace, image, output = build_context
    with pytest.raises(ValidationError, match="corresponden"):
        rebuild_project(project, workspace, replace(image, sha256="ab" * 32), output)
    path = project / "text/main.jsonl"
    write_jsonl(path, [replace(unit, status="untranslated") for unit in read_jsonl(path)])
    with pytest.raises(ValidationError, match="No hay textos"):
        rebuild_project(project, workspace, image, output)
    assert not output.exists()


def test_existing_output_and_original_never_overwritten(build_context):
    project, workspace, image, output = build_context
    output.write_bytes(b"keep me")
    with pytest.raises(ValidationError):
        rebuild_project(project, workspace, image, output)
    assert output.read_bytes() == b"keep me"
    with pytest.raises(ValidationError):
        rebuild_project(project, workspace, image, image.path)


def test_cancellation_during_iso_copy_leaves_no_output_or_temporary(build_context):
    project, workspace, image, output = build_context
    def cancel(progress):
        if progress.message == "Copiando imagen original":
            raise TaskCancelled()
    with pytest.raises(TaskCancelled):
        rebuild_project(project, workspace, image, output, progress=cancel)
    assert not output.exists()
    assert not list(output.parent.glob(".romkit-*.iso"))


def test_compressed_slot_overflow_is_explicit():
    with pytest.raises(ValidationError, match="Acorta"):
        _compress(b"Some text", 1)


def test_studio_import_action_builds_and_reports_new_iso(build_context, qapp):
    from PySide6.QtTest import QSignalSpy
    from romkit_studio.windows.main_window import MainWindow
    from romkit_studio.services.controller import StudioController
    project, workspace, image, output = build_context
    class Choices:
        def choose_translation(self, parent, current_workspace):
            return project
        def choose_output_iso(self, parent, current_image):
            return output
    window = MainWindow()
    window.session.open_image(image, workspace.layout.project_root, [])
    controller = StudioController(window, dialogs=Choices())
    window.controller = controller
    errors = QSignalSpy(controller.runner.error)
    assert window.import_translation_action.isEnabled()
    window.import_translation_action.trigger()
    assert not window.import_translation_action.isEnabled()
    deadline = time.monotonic() + 10
    while controller.runner.busy and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(.005)
    assert not controller.runner.busy
    assert errors.count() == 0
    assert output.is_file()
    assert "ISO traducida creada" in window.log_panel.toPlainText()
    assert controller._build_dialog.isVisible()
    controller._build_dialog.close()
    window.close()


def test_studio_import_cancel_preserves_session(build_context, qapp):
    from romkit_studio.windows.main_window import MainWindow
    from romkit_studio.services.controller import StudioController
    project, workspace, image, output = build_context
    class Choices:
        def choose_translation(self, parent, current_workspace):
            return None
    window = MainWindow()
    window.session.open_image(image, workspace.layout.project_root, [])
    controller = StudioController(window, dialogs=Choices())
    window.controller = controller
    window.import_translation_action.trigger()
    assert not controller.runner.busy
    assert window.session.state.image == image
    assert not output.exists()
    window.close()


def test_original_changed_since_export_is_rejected(build_context):
    project, workspace, image, output = build_context
    with image.path.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValidationError, match="imagen original ha cambiado"):
        rebuild_project(project, workspace, image, output)
    assert not output.exists()


def test_iso_copy_rejects_source_changed_after_validation(build_context):
    project, workspace, image, output = build_context
    reader = Iso9660Reader()
    from romkit_core.errors import PlatformError
    with pytest.raises(PlatformError, match="cambió mientras se copiaba"):
        reader.patch_copy(image.path, output, {}, expected_sha256="00" * 32)
    assert not output.exists()
    assert not list(output.parent.glob(".romkit-*.iso"))


def test_modified_archive_origin_is_rejected(build_context):
    project, workspace, image, output = build_context
    data = workspace.read_metadata("reinsert.json")
    data["archive_resources"][0]["sha256"] = "ab" * 32
    workspace.write_metadata("reinsert.json", data)
    with pytest.raises(ValidationError, match="tabla original no coincide"):
        rebuild_project(project, workspace, image, output)
    assert not output.exists()
