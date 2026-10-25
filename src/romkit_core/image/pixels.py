"""Lossless fixed-palette PSP pixel encoding. No palette mutation or resizing."""
from PySide6.QtGui import QImage, QImageReader
from romkit_core.analysis.gim import _color, MAX_PIXELS


def png_rgba(content):
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    buffer = QBuffer()
    buffer.setData(QByteArray(content))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer, b'png')
    size = reader.size()
    if not size.isValid() or size.width() * size.height() > MAX_PIXELS:
        raise ValueError('Dimensiones PNG inválidas o demasiado grandes')
    image = reader.read().convertToFormat(QImage.Format.Format_RGBA8888)
    if image.isNull():
        raise ValueError('PNG no válido')
    rgba = b''.join(bytes(image.constBits()[y*image.bytesPerLine():y*image.bytesPerLine()+image.width()*4]) for y in range(image.height()))
    return image.width(), image.height(), rgba


def encode_pixels(rgba, width, height, fmt, stride, original, palette=None, *, flip=False):
    output = bytearray(original)
    lookup = {bytes(color): i for i, color in reversed(list(enumerate(palette or [])))}
    cache = {}
    for y in range(height):
        row = (height - 1 - y if flip else y) * stride
        for x in range(width):
            color = bytes(rgba[(y*width+x)*4:(y*width+x+1)*4])
            if fmt >= 4:
                if color not in lookup:
                    raise ValueError('El PNG usa colores ajenos a la paleta original; conserva la paleta RGBA y su transparencia')
                value = lookup[color]
                if fmt == 4:
                    if value > 15:
                        raise ValueError('Color fuera de la paleta de 16 colores')
                    at, shift = row + x//2, (x%2)*4
                    output[at] = (output[at] & ~(15 << shift)) | (value << shift)
                    continue
                step = {5:1, 6:2, 7:4}[fmt]
            else:
                step = 4 if fmt == 3 else 2
                if color not in cache:
                    r,g,b,a = color
                    value = (int.from_bytes(color,'little') if fmt == 3 else
                             (r>>3)|((g>>2)<<5)|((b>>3)<<11) if fmt == 0 else
                             (r>>3)|((g>>3)<<5)|((b>>3)<<10)|((a>>7)<<15) if fmt == 1 else
                             (r>>4)|((g>>4)<<4)|((b>>4)<<8)|((a>>4)<<12))
                    if _color(value,fmt) != color:
                        raise ValueError(f'El PNG contiene colores no representables sin pérdida en el formato PSP {fmt}')
                    cache[color] = value
                value = cache[color]
            at = row + x*step
            output[at:at+step] = value.to_bytes(step,'little')
    return bytes(output)


def unswizzle(raw, stride, rows):
    if stride % 16 or rows % 8 or len(raw) != stride*rows:
        raise ValueError('Dimensiones de swizzle inválidas')
    linear = bytearray(raw)
    for y in range(rows):
        for x in range(0,stride,16):
            at = ((y//8)*(stride//16)+x//16)*128 + y%8*16
            linear[y*stride+x:y*stride+x+16] = raw[at:at+16]
    return bytes(linear)


def swizzle(linear, stride, rows):
    output = bytearray(linear)
    for y in range(rows):
        for x in range(0,stride,16):
            at = ((y//8)*(stride//16)+x//16)*128 + y%8*16
            output[at:at+16] = linear[y*stride+x:y*stride+x+16]
    return bytes(output)
