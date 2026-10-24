"""PSP little-endian GIM, first frame/mipmap, converted to lossless RGBA PNG.

Format reference: https://github.com/jeffangelion/gimconv_v (GIM structure)
Pixel layouts: https://dev.ppsspp.org/docs/psp-hardware/gpu/image-formats/
"""
from dataclasses import dataclass
import struct
import zlib

MAGIC = b"MIG.00.1PSP\x00"
MAX_PIXELS = 4_194_304
MAX_BYTES = 64 * 1024 * 1024


def gim_end(data, offset):
    if data[offset:offset + len(MAGIC)] != MAGIC or offset + 32 > len(data):
        return None
    kind, _, size, following, body = struct.unpack_from("<HHIII", data, offset + 16)
    end = offset + 16 + size
    if kind != 2 or size < 16 or size > MAX_BYTES or not 16 <= body <= size or end > len(data):
        return None
    return end


def _chunks(data, start, end, depth=0):
    if depth > 12:
        raise ValueError("Demasiados niveles GIM")
    blocks = 0
    while start < end:
        if start + 16 > end or blocks > 512:
            raise ValueError("Bloque GIM truncado")
        kind, _, size, following, body = struct.unpack_from("<HHIII", data, start)
        if size < 16 or start + size > end or not 16 <= body <= size:
            raise ValueError("Tamaño de bloque GIM inválido")
        if kind in (2, 3):
            yield kind, list(_chunks(data, start + body, start + size, depth + 1))
        elif kind in (4, 5):
            yield kind, _plane(data, start, size, body)
        start += size
        blocks += 1


def _plane(data, start, size, body):
    base = start + body
    if base + 48 > start + size:
        raise ValueError("Cabecera de imagen GIM truncada")
    _, _, fmt, order, width, height, bpp, pitch, height_align = struct.unpack_from("<9H", data, base)
    bits = {0: 16, 1: 16, 2: 16, 3: 32, 4: 4, 5: 8, 6: 16, 7: 32}.get(fmt)
    if bits is None:
        raise ValueError(f"Formato GIM no compatible: {fmt}")
    if not width or not height or width * height > MAX_PIXELS or order not in (0, 1):
        raise ValueError("Dimensiones u orden GIM inválidos")
    if bpp != bits or not pitch or pitch > 4096 or pitch & (pitch - 1):
        raise ValueError("Paso de fila GIM inválido")
    plane_start, plane_end = struct.unpack_from("<II", data, base + 28)
    if not 48 <= plane_start <= plane_end <= size - body:
        raise ValueError("Datos GIM fuera del bloque")
    row_bytes = (width * bits + 7) // 8
    stride = (row_bytes + pitch - 1) // pitch * pitch
    rows = (height + 7) // 8 * 8 if order else height
    required = rows * stride
    if required > MAX_BYTES or required > plane_end - plane_start:
        raise ValueError("Datos de píxeles GIM truncados")
    pixels = bytes(data[base + plane_start:base + plane_start + required])
    if order:
        if stride % 16:
            raise ValueError("Swizzle GIM requiere bloques de 16 bytes")
        linear = bytearray(required)
        for y in range(rows):
            for x in range(0, stride, 16):
                block = ((y // 8) * (stride // 16) + x // 16) * 128 + (y % 8) * 16
                linear[y * stride + x:y * stride + x + 16] = pixels[block:block + 16]
        pixels = linear
    return fmt, width, height, stride, pixels


def _color(value, fmt):
    if fmt == 0:
        r, g, b = value & 31, (value >> 5) & 63, (value >> 11) & 31
        return bytes(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2), 255))
    if fmt == 1:
        values = [(value >> shift) & 31 for shift in (0, 5, 10)]
        return bytes([((v << 3) | (v >> 2)) for v in values] + [255 if value & 0x8000 else 0])
    if fmt == 2:
        return bytes(((value >> shift) & 15) * 17 for shift in (0, 4, 8, 12))
    return value.to_bytes(4, "little")


def _palette(plane):
    fmt, width, height, stride, pixels = plane
    if fmt > 3 or width * height > 65536:
        raise ValueError("Paleta GIM no compatible")
    byte_count = 4 if fmt == 3 else 2
    return [_color(int.from_bytes(pixels[y * stride + x * byte_count:y * stride + (x + 1) * byte_count], "little"), fmt)
            for y in range(height) for x in range(width)]


def _rgba(plane, palette):
    fmt, width, height, stride, pixels = plane
    rows = []
    for y in range(height):
        row = pixels[y * stride:(y + 1) * stride]
        if fmt == 3:
            rows.append(bytes(row[:width * 4]))
            continue
        colors = []
        for x in range(width):
            if fmt < 3:
                color = _color(int.from_bytes(row[x * 2:x * 2 + 2], "little"), fmt)
            else:
                if not palette:
                    raise ValueError("GIM indexado sin paleta")
                if fmt == 4:
                    index = (row[x // 2] >> ((x % 2) * 4)) & 15
                else:
                    length = {5: 1, 6: 2, 7: 4}[fmt]
                    index = int.from_bytes(row[x * length:(x + 1) * length], "little")
                if index >= len(palette):
                    raise ValueError("Índice GIM fuera de la paleta")
                color = palette[index]
            colors.append(color)
        rows.append(b"".join(colors))
    return b"".join(rows)


def rgba_png(width, height, rgba):
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    rows = b"".join(b"\0" + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


@dataclass(frozen=True)
class GimImage:
    width: int
    height: int
    png: bytes


def decode_gim(data):
    end = gim_end(data, 0)
    if end is None:
        raise ValueError("Cabecera GIM inválida")
    roots = list(_chunks(data, 16, end))
    def pictures(nodes):
        for kind, body in nodes:
            if kind == 3:
                palette = next((_palette(plane) for t, plane in body if t == 5), None)
                for t, plane in body:
                    if t == 4:
                        rgba = _rgba(plane, palette)
                        yield GimImage(plane[1], plane[2], rgba_png(plane[1], plane[2], rgba))
            elif kind == 2:
                yield from pictures(body)
    images = list(pictures(roots))
    if not images:
        raise ValueError("GIM sin imagen")
    return images
