import struct
import pytest
from romkit_core.adapters.pokapoka.fonts import read_ccm,candidate_codes


def ccm():
    data=bytearray(44+24)
    struct.pack_into('<II',data,0,0x10001,len(data))
    struct.pack_into('<HHII',data,16,1,1,32,44);data[30]=1
    struct.pack_into('<III',data,32,0x8341,0x8341,0)
    struct.pack_into('<4f4h',data,44,0.25,0.25,0.5,0.5,0,8,9,0)
    return data


def test_ccm_codes_uv_and_absence_in_corpus():
    font=read_ccm(ccm());glyph=font[0x8341]
    assert glyph.rectangle(256,128)==(64,32,128,64)
    assert candidate_codes([font,font],['ABC'])==[0x8341]
    assert candidate_codes([font],['ア'])==[]


@pytest.mark.parametrize('mutation',['truncated','version','page','range','nan','rows'])
def test_ccm_rejects_unverified_layouts(mutation):
    data=ccm()
    if mutation=='truncated':data=data[:-1]
    if mutation=='version':struct.pack_into('<I',data,0,0x20000)
    if mutation=='page':struct.pack_into('<h',data,66,1)
    if mutation=='range':struct.pack_into('<I',data,36,0x8342)
    if mutation=='nan':struct.pack_into('<f',data,44,float('nan'))
    if mutation=='rows':struct.pack_into('<I',data,40,1)
    with pytest.raises(ValueError):read_ccm(data)
