"""Write one GIM surface, preserving every header, palette and other surface."""
import struct
from romkit_core.analysis.gim import decode_gim, _plane, _palette, gim_end
from romkit_core.image.pixels import png_rgba, encode_pixels, swizzle


def replace_gim(data, index, png):
    images = decode_gim(data)
    if not 0 <= index < len(images):
        raise ValueError('Imagen GIM fuera de límites')
    width,height,rgba = png_rgba(png)
    if (width,height) != (images[index].width,images[index].height):
        raise ValueError('Conserva las dimensiones originales del GIM')
    planes = []
    def visit(start,end):
        while start < end:
            kind,_,size,_,body = struct.unpack_from('<HHIII',data,start)
            if kind == 2:
                visit(start+body,start+size)
            elif kind == 3:
                cursor, children = start+body, []
                while cursor < start+size:
                    k,_,s,_,b = struct.unpack_from('<HHIII',data,cursor)
                    children.append((k,cursor,s,b));cursor += s
                palette = next((_palette(_plane(data,p,s,b)) for k,p,s,b in children if k==5),None)
                planes.extend((p,s,b,palette) for k,p,s,b in children if k==4)
            start += size
    visit(16,gim_end(data,0))
    pos,size,body,palette = planes[index]
    base = pos+body
    if struct.unpack_from('<4H',data,base+40) != (1,1,3,1):
        raise ValueError('GIM con múltiples niveles o frames: escritura no implementada')
    fmt,w,h,stride,linear = _plane(data,pos,size,body)
    encoded = encode_pixels(rgba,w,h,fmt,stride,linear,palette)
    order = struct.unpack_from('<H',data,base+6)[0]
    if order:
        encoded = swizzle(encoded,stride,(h+7)//8*8)
    at = base + struct.unpack_from('<I',data,base+28)[0]
    output = bytearray(data);output[at:at+len(encoded)] = encoded
    after = decode_gim(output)
    for n,item in enumerate(after):
        expected = rgba if n==index else png_rgba(images[n].png)[2]
        if png_rgba(item.png)[2] != expected:
            raise ValueError('La verificación de GIM afectó a otra superficie o no coincide')
    return bytes(output)
