from dataclasses import replace
import struct
import time

import pytest
from iso_builder import make_iso
from romkit_core.analysis.btx import scan_arcv_text
from romkit_core.errors import ValidationError
from romkit_core.image import ImageService
from romkit_core.platforms import PlatformRegistry
from romkit_core.platforms.psp import PspBackend
from romkit_core.platforms.iso9660 import Iso9660Reader
from romkit_core.project import write_jsonl, read_jsonl
from romkit_core.project.generator import ProjectGenerator
from romkit_core.project.rebuild import rebuild_project
from romkit_core.tasks import TaskCancelled
from romkit_core.workspace import WorkspaceManager


@pytest.fixture
def context(tmp_path, request):
    texts = ["Hello, <n1001>!", "Good morning", "Pending"]
    raw = bytearray(24 + 8 * len(texts))
    raw[:4] = b"BTX "
    struct.pack_into("<II", raw, 4, 1, 16)
    struct.pack_into("<II", raw, 16, 1, len(texts))
    for row, text in enumerate(texts):
        pos = 24 + row * 8
        struct.pack_into("<II", raw, pos, row, len(raw) - pos)
        raw.extend(text.encode("utf-16-le") + b"\0\0")
    tutorial = getattr(request, 'param', '').startswith('tutorial')
    if tutorial:
        raw = bytearray(24 + len(texts)*8)
        raw[4:8] = b'BTX '
        struct.pack_into('<II',raw,8,1,12)
        struct.pack_into('<II',raw,16,1,len(texts))
        for row,text in enumerate(texts):
            raw.extend(bytes((-len(raw)) % 4))
            pos = 24 + row*8
            struct.pack_into('<II',raw,pos,row,len(raw)-pos)
            raw.extend(text.encode('utf-16-le')+b'\0\0')
        raw.extend(bytes((-len(raw)) % 4))
        struct.pack_into('<I',raw,0,len(raw))
        raw.extend(bytes(range(len(texts)*12)))
    else:
        raw.extend(b"opaque metadata retained")
    name = b"Keep/dialog.res\0"
    index = bytearray(56) + name
    index[:4] = b"VCRA"
    struct.pack_into("<III", index, 4, 0x101, 1, 2048)
    struct.pack_into("<6I", index, 32, len(raw), 0, 56, 1, 0, 0)
    volume = b"untouched prefix".ljust(2048,b"\xff") + raw + b"untouched suffix"
    if tutorial:
        padding = bytearray(2048-len(raw))
        if request.param == 'tutorial-dirty':
            padding[0] = 1
        volume = b'untouched prefix'.ljust(2048,b'\xff') + raw + padding + b'untouched suffix'
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "ARCVINFO.BIN").write_bytes(index)
    (archive / "ARCV0.BIN").write_bytes(volume)
    files = {"PSP_GAME/USRDIR/ARCVINFO.BIN": bytes(index), "PSP_GAME/USRDIR/ARCV0.BIN": volume}
    source = tmp_path / "original.iso"
    make_iso(source, extra_files=files)
    registry = PlatformRegistry()
    registry.register(PspBackend())
    service = ImageService(registry)
    image = service.select_platform(service.inspect(source), "psp")
    workspace = WorkspaceManager(tmp_path / "workspace")
    workspace.register_source(image)
    candidates, origins = scan_arcv_text(archive / "ARCVINFO.BIN", "PSP_GAME/USRDIR/ARCVINFO.BIN")
    # Metadata already exported before write support was added must still work.
    for origin in origins:
        origin["reinsert_supported"] = False
    workspace.write_metadata("archive_resources.json", {"resources": origins})
    project = tmp_path / "project"
    generated = ProjectGenerator().generate(project, image, "psp", candidates, workspace=workspace, source_language="en")
    units = list(generated.units)
    units[0] = replace(units[0], target="Hola, <n1001>!", status="translated")
    units[1] = replace(units[1], target="", status="reviewed")
    write_jsonl(project / "text/main.jsonl", units)
    return project, workspace, image, tmp_path / "output.iso", files


def test_roundtrip_only_changes_selected_btx_bytes(context, tmp_path):
    project, workspace, image, output, files = context
    original = image.path.read_bytes()
    result = rebuild_project(project, workspace, image, output)
    assert (result.translated,result.skipped,result.tables) == (2,1,1)
    assert image.path.read_bytes() == original and output.stat().st_size == len(original)
    reader = Iso9660Reader()
    with reader.open(image.path) as before, reader.open(output) as after:
        entries = list(reader.walk(before))
        assert entries == list(reader.walk(after))
        for entry in entries:
            assert before._handle.get_record(iso_path=entry.iso_path).extent_location() == after._handle.get_record(iso_path=entry.iso_path).extent_location()
            if not entry.is_directory and not entry.logical_path.endswith("ARCV0.BIN"):
                assert b"".join(reader.read_chunks(before,entry)) == b"".join(reader.read_chunks(after,entry))
        reader.extract_all(after,tmp_path / "rebuilt")
    directory = tmp_path / "rebuilt/PSP_GAME/USRDIR"
    found,_ = scan_arcv_text(directory / "ARCVINFO.BIN", "PSP_GAME/USRDIR/ARCVINFO.BIN")
    assert [c.text for c in found] == ["Hola, <n1001>!", "Pending"]
    volume = (directory / "ARCV0.BIN").read_bytes()
    assert volume[:2048] == files["PSP_GAME/USRDIR/ARCV0.BIN"][:2048]
    assert volume.endswith(b"opaque metadata retaineduntouched suffix")


def test_no_change_roundtrip_is_byte_identical(context):
    project, workspace, image, output,_ = context
    path = project / "text/main.jsonl"
    write_jsonl(path,[replace(u,target=u.source,status="reviewed") for u in read_jsonl(path)])
    rebuild_project(project,workspace,image,output)
    assert output.read_bytes() == image.path.read_bytes()


@pytest.mark.parametrize('context',['tutorial','tutorial-dirty'],indirect=True)
def test_tutorial_sector_growth_updates_index_and_preserves_metadata(context,tmp_path,request):
    project,workspace,image,output,files = context
    path = project / 'text/main.jsonl'
    units = read_jsonl(path)
    units[0] = replace(units[0],target=units[0].source+' extended tutorial sentence '*8)
    write_jsonl(path,units)
    if request.node.callspec.params['context'] == 'tutorial-dirty':
        with pytest.raises(ValidationError,match='relleno ARCV'):
            rebuild_project(project,workspace,image,output,experimental=True)
        assert not output.exists()
        return
    rebuild_project(project,workspace,image,output,experimental=True)
    reader = Iso9660Reader()
    with reader.open(output) as iso:
        reader.extract_all(iso,tmp_path/'grown')
    directory = tmp_path/'grown/PSP_GAME/USRDIR'
    index = (directory/'ARCVINFO.BIN').read_bytes()
    old_index = files['PSP_GAME/USRDIR/ARCVINFO.BIN']
    old_size = struct.unpack_from('<I',old_index,32)[0]
    new_size = struct.unpack_from('<I',index,32)[0]
    assert new_size>old_size and index[:32]==old_index[:32] and index[36:]==old_index[36:]
    old = files['PSP_GAME/USRDIR/ARCV0.BIN']
    volume = (directory/'ARCV0.BIN').read_bytes()
    old_raw, new_raw = old[2048:2048+old_size],volume[2048:2048+new_size]
    assert new_raw[struct.unpack_from('<I',new_raw)[0]:] == old_raw[struct.unpack_from('<I',old_raw)[0]:]
    assert volume[:2048] == old[:2048] and volume[4096:] == old[4096:]
    found,_ = scan_arcv_text(directory/'ARCVINFO.BIN','PSP_GAME/USRDIR/ARCVINFO.BIN')
    assert [c.text for c in found] == [units[0].target,'Pending']
    assert output.stat().st_size == image.size_bytes


def test_experimental_redistributes_space_without_growing_resource(context, tmp_path):
    project, workspace, image, output,_ = context
    path = project / 'text/main.jsonl'
    units = read_jsonl(path)
    units[0] = replace(units[0],target='Hola amigo, <n1001>!')
    write_jsonl(path,units)
    with pytest.raises(ValidationError):
        rebuild_project(project,workspace,image,output)
    rebuild_project(project,workspace,image,output,experimental=True)
    reader = Iso9660Reader()
    with reader.open(output) as iso:
        reader.extract_all(iso,tmp_path/'experimental')
    found,_ = scan_arcv_text(tmp_path/'experimental/PSP_GAME/USRDIR/ARCVINFO.BIN','PSP_GAME/USRDIR/ARCVINFO.BIN')
    assert [c.text for c in found] == ['Hola amigo, <n1001>!', 'Pending']
    assert output.stat().st_size == image.size_bytes


def test_experimental_still_rejects_pool_overflow(context):
    project, workspace, image, output,_ = context
    path = project / 'text/main.jsonl'
    units = read_jsonl(path)
    units[0] = replace(units[0],target='X'*500+'<n1001>')
    write_jsonl(path,units)
    with pytest.raises(ValidationError,match='bloque BTX'):
        rebuild_project(project,workspace,image,output,experimental=True)
    assert not output.exists()


@pytest.mark.parametrize("target", ["X" * 100, "missing token", "bad\0<n1001>"])
def test_bad_translation_never_publishes_iso(context,target):
    project, workspace, image, output,_ = context
    path = project / "text/main.jsonl"
    units = read_jsonl(path)
    units[0] = replace(units[0],target=target)
    write_jsonl(path,units)
    with pytest.raises(ValidationError):
        rebuild_project(project,workspace,image,output)
    assert not output.exists()


def test_wrong_origin_hash_and_cancellation(context):
    project, workspace, image, output,_ = context
    def cancel(value):
        if value.message == "Copiando imagen original":
            raise TaskCancelled()
    with pytest.raises(TaskCancelled):
        rebuild_project(project,workspace,image,output,progress=cancel)
    assert not output.exists()

    metadata = workspace.read_metadata("reinsert.json")
    metadata["archive_resources"][0]["sha256"] = "00" * 32
    workspace.write_metadata("reinsert.json",metadata)
    with pytest.raises(ValidationError,match="metadata"):
        rebuild_project(project,workspace,image,output)
    assert not output.exists()


def test_studio_delta_action_creates_verified_patch(context, qapp):
    from romkit_studio.windows.main_window import MainWindow
    from romkit_studio.services.controller import StudioController
    project, workspace, image, output,_ = context
    rebuild_project(project,workspace,image,output)
    patch = output.with_suffix('.bps')
    class Choices:
        def choose_delta_target(self,parent,current):
            return output
        def choose_delta_output(self,parent,target):
            return patch
    window = MainWindow()
    controller = StudioController(window,dialogs=Choices())
    window.session.open_image(image,workspace.layout.project_root,[])
    window.show()
    window.workflow_buttons[window.create_delta_action].click()
    deadline = time.monotonic()+10
    while controller.runner.busy and time.monotonic()<deadline:
        qapp.processEvents()
        time.sleep(.005)
    qapp.processEvents()
    assert patch.read_bytes().startswith(b'BPS1')
    controller._delta_dialog.close()
    window.close()
