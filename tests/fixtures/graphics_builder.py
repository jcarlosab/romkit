import struct


def gim_plane(kind, fmt, width, height, pixels, *, order=0):
    bits = {0: 16, 1: 16, 2: 16, 3: 32, 4: 4, 5: 8, 6: 16, 7: 32}[fmt]
    stride = ((width * bits + 7) // 8 + 15) // 16 * 16
    height_stored = (height + 7) // 8 * 8 if order else height
    data = bytes(pixels).ljust(stride * height_stored, b"\0")
    header = bytearray(64)
    struct.pack_into("<9H", header, 0, 48, 0, fmt, order, width, height, bits, 16, 8 if order else 1)
    struct.pack_into("<III", header, 24, 48, 64, 64 + len(data))
    struct.pack_into("<4H", header, 40, 1, 1, 3, 1)
    struct.pack_into("<I", header, 48, 64)
    size = 16 + len(header) + len(data)
    return struct.pack("<HHIII", kind, 0, size, size, 16) + header + data


def make_gim(fmt=3, *, pixels=None, width=2, height=1, palette=None, order=0):
    if pixels is None:
        pixels = b"\xff\0\0\xff\0\xff\0\xff"
    children = gim_plane(4, fmt, width, height, pixels, order=order)
    if palette is not None:
        colors = b"".join(palette)
        children += gim_plane(5, 3, len(palette), 1, colors)
    picture = struct.pack("<HHIII", 3, 0, 16 + len(children), 16, 16) + children
    return (b"MIG.00.1PSP\0" + bytes(4)
            + struct.pack("<HHIII", 2, 0, 16 + len(picture), 16, 16) + picture)


def make_bnd(name, data):
    name_bytes = name.encode("ascii") + b"\0"
    offset = 48 + len(name_bytes)
    header = bytearray(32)
    header[:4] = b"BND\0"
    struct.pack_into("<II", header, 12, offset + len(data), 1)
    return bytes(header) + struct.pack("<4I", 0, offset, len(data), 48) + name_bytes + data
