import struct
import pytest
from romkit_core.analysis.gmio import decode_gmio
from romkit_core.analysis.arcv import iter_arcv
from romkit_core.analysis.images import export_images
from romkit_core.analysis.inventory import inventory
from romkit_core.workspace import WorkspaceManager
from PySide6.QtGui import QImage


def texture():
    data=bytearray(80+16*8)
    data[:4]=b'GMIO'
    struct.pack_into('<I',data,4,5)
    struct.pack_into('<HH',data,20,2,2)
    struct.pack_into('<4I',data,36,3,0,1,24)
    struct.pack_into('<HH',data,52,1,20)
    struct.pack_into('<H',data,70,4)
    # Four-pixel pitch; logical width two. Swizzled rows in a single block.
    data[80:88]=b'\xff\x00\x00\xff'*2
    data[96:104]=b'\x00\xff\x00\xff'*2
    return bytes(data)


def test_gmio_swizzle_pitch_crop_and_orientation():
    image=decode_gmio(texture(),0,80,76)
    png=QImage.fromData(image.png)
    assert (png.width(),png.height())==(2,2)
    assert png.pixelColor(0,0).getRgb()==(0,255,0,255)
    assert png.pixelColor(1,1).getRgb()==(255,0,0,255)


def test_gmio_rejects_truncated_extras_and_pixels():
    with pytest.raises(ValueError):decode_gmio(texture(),0,80,60)
    with pytest.raises(ValueError):decode_gmio(texture()[:-1],0,80,76)


def test_gmio_indexed_palette_relative_to_pixel_data():
    data=bytearray(128+128+8)
    data[:4]=b'GMIO'
    struct.pack_into('<I',data,4,5)
    struct.pack_into('<HH',data,20,2,2)
    struct.pack_into('<4I',data,36,5,0,2,76)
    struct.pack_into('<HH',data,52,2,48)
    data[56:60]=b'TTPO'
    struct.pack_into('<I',data,68,128)
    struct.pack_into('<I',data,80,2)
    struct.pack_into('<I',data,92,3)
    struct.pack_into('<HH',data,104,1,20)
    struct.pack_into('<H',data,122,16)
    data[128:130]=b'\x00\x00'
    data[144:146]=b'\x01\x01'
    data[256:264]=b'\xff\x00\x00\xff\x00\xff\x00\xff'
    image=decode_gmio(data,0,128,128)
    png=QImage.fromData(image.png)
    assert png.pixelColor(0,0).getRgb()==(0,255,0,255)
    assert png.pixelColor(0,1).getRgb()==(255,0,0,255)
    data[128]=3
    with pytest.raises(ValueError):decode_gmio(data,0,128,128)


def archive(directory):
    directory.mkdir(parents=True,exist_ok=True)
    raw=texture(); name=b'tx/test.img\x00'; index=bytearray(88+len(name))
    index[:4]=b'VCRA';struct.pack_into('<III',index,4,0x101,1,2048)
    struct.pack_into('<6I',index,32,len(raw),0,88,0,56,0)
    index[56:60]=b'MARV';struct.pack_into('<7I',index,60,1,76,0,len(raw)-80,16,1,0)
    index[88:]=name
    (directory/'ARCVINFO.BIN').write_bytes(index)
    (directory/'ARCV0.BIN').write_bytes(raw)
    return directory/'ARCVINFO.BIN'


def test_arcv_bounds_and_export(tmp_path):
    workspace=WorkspaceManager(tmp_path/'workspace')
    index=archive(workspace.layout.area('extracted')/'PSP_GAME'/'USRDIR')
    assert list(iter_arcv(index))[0][2:]==(80,76)
    out=tmp_path/'out';out.mkdir()
    result=export_images(inventory(workspace.layout.area('extracted')),workspace,out)
    assert result.count==1 and result.warnings==0
    (index.parent/'ARCV0.BIN').write_bytes(b'bad')
    with pytest.raises(ValueError):list(iter_arcv(index))
