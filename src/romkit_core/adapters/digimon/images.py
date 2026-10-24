"""PSP GMIO v5 textures, including palettes embedded as TTPO extras.

Container field reference: https://github.com/SydMontague/DecodeTools
PSP pixel layouts use the same formats as GIM. Original alpha is retained.
"""
import struct
from romkit_core.analysis.gim import GimImage, _rgba, _color, rgba_png, MAX_PIXELS


def decode_gmio(data, at, base, structure):
    if not 0 <= at <= structure <= base <= len(data) or at + 52 > structure or data[at:at + 4] != b"GMIO" or struct.unpack_from("<I", data, at + 4)[0] != 5:
        raise ValueError("Cabecera GMIO no compatible")
    pointer = struct.unpack_from("<I", data, at + 12)[0]
    width, height = struct.unpack_from("<HH", data, at + 20)
    if not width or not height or pointer == 0xffffffff:
        return None
    fmt, _, count, length = struct.unpack_from("<4I", data, at + 36)
    bits = {0:16, 1:16, 2:16, 3:32, 4:4, 5:8}.get(fmt)
    if bits is None or width * height > MAX_PIXELS or count > 16 or at + 52 + length > structure:
        raise ValueError("Formato o dimensiones GMIO inválidos")
    cursor, finish = at + 52, at + 52 + length
    pitch, palette_info = width, None
    for _ in range(count):
        if cursor + 4 > finish:
            raise ValueError("Extra GMIO truncado")
        kind, size = struct.unpack_from("<HH", data, cursor)
        start = cursor + 4
        cursor = start + size
        if cursor > finish:
            raise ValueError("Extra GMIO fuera de límites")
        if kind == 1 and size >= 20:
            pitch = struct.unpack_from("<H", data, start + 14)[0]
        if kind == 2 and size >= 48 and data[start:start + 4] == b"TTPO":
            palette_info = struct.unpack_from("<I", data, start + 12)[0], struct.unpack_from("<I", data, start + 24)[0], struct.unpack_from("<I", data, start + 36)[0]
    if not width <= pitch <= 4096:
        raise ValueError("Paso GMIO inválido")
    stride = (pitch * bits + 7) // 8
    pixels_at = base + pointer
    required = stride * height
    if pixels_at < base or pixels_at + required > len(data):
        raise ValueError("Píxeles GMIO truncados")
    pixels = bytes(data[pixels_at:pixels_at + required])
    # PSP GMIO v5 stores surfaces in 16-byte by 8-row blocks.
    rows = (height + 7) // 8 * 8
    if stride % 16 or pixels_at + stride * rows > len(data):
        raise ValueError("Swizzle GMIO inválido")
    raw = data[pixels_at:pixels_at + stride * rows]
    pixels = bytearray(required)
    for y in range(height):
        for x in range(0, stride, 16):
            offset = ((y // 8) * (stride // 16) + x // 16) * 128 + y % 8 * 16
            pixels[y * stride + x:y * stride + x + 16] = raw[offset:offset + 16]
    palette = None
    if fmt >= 4:
        if palette_info is None:
            raise ValueError("GMIO sin paleta")
        offset, colors, pf = palette_info
        step = 4 if pf == 3 else 2
        begin = pixels_at + offset
        if pf > 3 or not 0 < colors <= 256 or begin + colors * step > len(data):
            raise ValueError("Paleta GMIO fuera de límites")
        palette = [_color(int.from_bytes(data[begin + n * step:begin + (n + 1) * step], "little"), pf) for n in range(colors)]
    rgba = _rgba((fmt, width, height, stride, pixels), palette)
    row = width * 4
    rgba = b"".join(rgba[y * row:(y + 1) * row] for y in reversed(range(height)))
    return GimImage(width, height, rgba_png(width, height, rgba))
