"""Read the verified little-endian CCM 0x10001 layout used by Poka Poka.

Field reference: SoulsFormats/Formats/CCM.cs (JKAnderson/SoulsFormats).
No texture edits or font substitutions are activated by this reader.
"""
from dataclasses import dataclass
import math
import struct


@dataclass(frozen=True)
class Glyph:
    code: int
    record: int
    texture: int
    uv: tuple[float, float, float, float]
    before: int
    width: int
    advance: int

    def rectangle(self, width, height):
        if width<=0 or height<=0:
            raise ValueError('Dimensiones de atlas inválidas')
        x1,y1,x2,y2=self.uv
        rectangle=tuple(round(v*dimension) for v,dimension in zip(self.uv,(width,height,width,height)))
        if not (0<=rectangle[0]<rectangle[2]<=width and 0<=rectangle[1]<rectangle[3]<=height):
            raise ValueError('Rectángulo CCM fuera del atlas')
        return rectangle


def read_ccm(data):
    if len(data)<32 or len(data)>32*1024*1024:
        raise ValueError('CCM truncado o demasiado grande')
    version,size=struct.unpack_from('<II',data)
    groups,count=struct.unpack_from('<HH',data,16)
    group_at,glyph_at=struct.unpack_from('<II',data,20)
    pages=data[30]
    if (version!=0x10001 or size!=len(data) or group_at!=32 or not pages or pages>32
            or glyph_at!=32+groups*12 or glyph_at+count*24!=len(data)):
        raise ValueError('Variante o tablas CCM no compatibles')
    rows=[]
    for n in range(count):
        position=glyph_at+n*24
        x1,y1,x2,y2,before,width,advance,texture=struct.unpack_from('<4f4h',data,position)
        if (not all(math.isfinite(v) for v in (x1,y1,x2,y2)) or not 0<=x1<x2<=1 or not 0<=y1<y2<=1
                or not 0<=texture<pages or not 0<=width<=4096 or not -4096<=advance<=4096):
            raise ValueError('Glifo CCM fuera de límites')
        rows.append((position,texture,(x1,y1,x2,y2),before,width,advance))
    glyphs={};used=set()
    for n in range(groups):
        start,end,index=struct.unpack_from('<III',data,32+n*12)
        if end<start or end>0xffff or index+end-start>=count:
            raise ValueError('Grupo CCM fuera de límites')
        for code in range(start,end+1):
            row=index+code-start
            if code in glyphs or row in used:
                raise ValueError('Códigos o filas CCM duplicados')
            used.add(row);glyphs[code]=Glyph(code,*rows[row])
    if len(used)!=count:
        raise ValueError('Filas CCM sin correspondencia')
    return glyphs


def candidate_codes(fonts, texts):
    """Return common CP932 glyph codes absent from all supplied source text.

    This only proves absence in that corpus, not in runtime player input or
    other resources. A caller must not activate candidates as a verified map.
    """
    occupied=set()
    for text in texts:
        for char in text:
            try:
                raw=char.encode('cp932')
            except UnicodeEncodeError:
                continue
            occupied.add(int.from_bytes(raw,'big'))
    common=set.intersection(*(set(font) for font in fonts)) if fonts else set()
    candidates=[]
    for code in sorted(common-occupied):
        if code<=0xff:
            continue
        raw=code.to_bytes(2,'big')
        try:
            char=raw.decode('cp932')
        except UnicodeDecodeError:
            continue
        if len(char)==1 and char.encode('cp932')==raw:
            candidates.append(code)
    return candidates
