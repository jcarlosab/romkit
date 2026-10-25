import hashlib
import json
import struct

import pytest
from PySide6.QtGui import QImage
from graphics_builder import make_gim, make_bnd
from pokapoka_builder import make_archive
from iso_builder import make_iso
from romkit_core.analysis.images import export_images
from romkit_core.analysis.inventory import inventory
from romkit_core.analysis.gim import decode_gim
from romkit_core.adapters.pokapoka.images import replace_gim
from romkit_core.image.pixels import png_rgba
from romkit_core.image import ImageService
from romkit_core.platforms import PlatformRegistry
from romkit_core.platforms.psp import PspBackend
from romkit_core.platforms.iso9660 import Iso9660Reader
from romkit_core.project.image_rebuild import rebuild_images
from romkit_core.errors import ValidationError
from romkit_core.tasks import TaskCancelled
from romkit_core.workspace import WorkspaceManager


def context(tmp_path, game, nested=False):
    archive=tmp_path/'archive';archive.mkdir()
    if game=='pokapoka':
        raw=make_gim()
        make_archive(archive,make_bnd('texture.gim',raw) if nested else raw,name='texture.bnd' if nested else 'texture.gim')
        bundle=archive/'POKAPOKA.BND';bundle.write_bytes(bundle.read_bytes().ljust(2048,b'\0'))
        bhd=bytearray((archive/'POKAPOKA.BHD').read_bytes());struct.pack_into('<I',bhd,12,2048);(archive/'POKAPOKA.BHD').write_bytes(bhd)
    else:
        raw=bytearray(80+128);raw[:4]=b'GMIO';struct.pack_into('<I',raw,4,5)
        struct.pack_into('<HH',raw,20,2,2);struct.pack_into('<4I',raw,36,3,0,1,24)
        struct.pack_into('<HH',raw,52,1,20);struct.pack_into('<H',raw,70,4)
        raw[80:88]=b'\xff\0\0\xff'*2;raw[96:104]=b'\0\xff\0\xff'*2
        index=bytearray(88)+b'tx/test.img\0';index[:4]=b'VCRA';struct.pack_into('<III',index,4,0x101,1,2048)
        struct.pack_into('<6I',index,32,len(raw),0,88,0,56,0)
        index[56:60]=b'MARV';struct.pack_into('<7I',index,60,1,76,0,len(raw)-80,16,1,0)
        (archive/'ARCVINFO.BIN').write_bytes(index);(archive/'ARCV0.BIN').write_bytes(raw)
    source=tmp_path/'original.iso'
    make_iso(source,extra_files={f'PSP_GAME/USRDIR/{p.name}':p.read_bytes() for p in archive.iterdir()})
    registry=PlatformRegistry();registry.register(PspBackend());service=ImageService(registry)
    image=service.select_platform(service.inspect(source),'psp')
    workspace=WorkspaceManager(tmp_path/'workspace');workspace.register_source(image)
    reader=Iso9660Reader()
    with reader.open(source) as iso:reader.extract_all(iso,workspace.layout.area('extracted'))
    destination=tmp_path/'export';destination.mkdir()
    exported=export_images(inventory(workspace.layout.area('extracted')),workspace,destination)
    return workspace,image,exported.path


def edit_export(root):
    manifest=json.loads((root/'imagenes.json').read_text(encoding='utf-8'))
    entry=manifest['images'][0];path=root/entry['file'];image=QImage(str(path))
    image.setPixelColor(0,0,'blue');assert image.save(str(path),'PNG')
    return entry,path


@pytest.mark.parametrize('game,nested',[('pokapoka',False),('pokapoka',True),('digimon',False)])
def test_image_iso_roundtrip_and_original_preserved(tmp_path,game,nested):
    workspace,image,root=context(tmp_path,game,nested)
    before=image.path.read_bytes()
    unchanged=tmp_path/'unchanged.iso';result=rebuild_images(root,workspace,image,unchanged)
    assert result.images==0 and unchanged.read_bytes()==before
    entry,path=edit_export(root)
    output=tmp_path/'edited.iso';result=rebuild_images(root,workspace,image,output)
    assert result.images==1 and image.path.read_bytes()==before and output.stat().st_size==len(before)
    reader=Iso9660Reader();rebuilt=WorkspaceManager(tmp_path/'rebuilt')
    with reader.open(output) as iso:reader.extract_all(iso,rebuilt.layout.area('extracted'))
    exported=export_images(inventory(rebuilt.layout.area('extracted')),rebuilt,tmp_path/'export')
    fresh=json.loads((exported.path/'imagenes.json').read_text(encoding='utf-8'))
    assert png_rgba((exported.path/fresh['images'][0]['file']).read_bytes())==png_rgba(path.read_bytes())


@pytest.mark.parametrize('failure',['hash','dimensions','old','cancel','escape','capacity'])
def test_image_failure_never_publishes(tmp_path,failure):
    workspace,image,root=context(tmp_path,'pokapoka')
    entry,path=edit_export(root);manifest=json.loads((root/'imagenes.json').read_text(encoding='utf-8'))
    progress=None
    if failure=='hash':manifest['source_sha256']='0'*64
    if failure=='old':manifest['schema_version']=1
    if failure=='escape':manifest['images'][0]['file']='../outside.png'
    if failure=='dimensions':
        wrong=QImage(3,1,QImage.Format.Format_RGBA8888);wrong.fill(0);wrong.save(str(path),'PNG')
    if failure=='capacity':
        manifest['images'][0]['origin']['stored_size']=1
    if failure=='cancel':
        def progress(_):raise TaskCancelled()
    (root/'imagenes.json').write_text(json.dumps(manifest),encoding='utf-8')
    output=tmp_path/'failed.iso'
    with pytest.raises((ValidationError,ValueError,TaskCancelled)):
        rebuild_images(root,workspace,image,output,progress=progress)
    assert not output.exists()


def test_indexed_gim_keeps_palette_and_rejects_new_colors():
    raw=make_gim(4,width=2,height=1,pixels=b'\x10',palette=[b'\xff\0\0\xff',b'\0\xff\0\xff'])
    image=decode_gim(raw)[0]
    # An unchanged write remains visually exact.
    assert png_rgba(decode_gim(replace_gim(raw,0,image.png))[0].png)==png_rgba(image.png)
    from romkit_core.analysis.gim import rgba_png
    with pytest.raises(ValueError,match='paleta'):
        replace_gim(raw,0,rgba_png(2,1,b'\0\0\xff\xff'*2))


def test_shared_gmio_view_cannot_change_without_selecting_all_views():
    from romkit_core.adapters.digimon.images import decode_gmio
    from romkit_core.analysis.gim import rgba_png
    from romkit_core.project.image_rebuild import _edit_resource
    raw=bytearray(160+128)
    for at in (0,80):
        raw[at:at+4]=b'GMIO';struct.pack_into('<I',raw,at+4,5)
        struct.pack_into('<HH',raw,at+20,2,2);struct.pack_into('<4I',raw,at+36,3,0,1,24)
        struct.pack_into('<HH',raw,at+52,1,20);struct.pack_into('<H',raw,at+70,4)
    raw[160:168]=b'\xff\0\0\xff'*2;raw[176:184]=b'\0\xff\0\xff'*2
    image=decode_gmio(raw,0,160,156)
    edited=rgba_png(2,2,b'\0\0\xff\xff'*4)
    entry={'source_format':'gmio','offset':0,'sha256':hashlib.sha256(image.png).hexdigest()}
    origin={'adapter':'digimon','base':160,'structure':156}
    with pytest.raises(ValidationError,match='compartidos'):
        _edit_resource(bytes(raw),'shared',[(entry,edited)],origin)
    output=_edit_resource(bytes(raw),'shared',[(entry,edited),({**entry,'offset':80},edited)],origin)
    assert png_rgba(decode_gmio(output,80,160,156).png)[2]==png_rgba(edited)[2]


def test_capacity_error_reports_required_and_available_bytes():
    from romkit_core.project.image_rebuild import _compress
    with pytest.raises(ValidationError,match=r'necesita \d+ bytes y dispone de 1'):
        _compress(bytes(range(256)),1)
