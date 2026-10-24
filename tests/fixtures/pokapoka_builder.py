import struct
import zlib

def make_fmg(texts):
    table = 40
    offset = table + len(texts) * 4
    offsets, strings = [], bytearray()
    for text in texts:
        offsets.append(offset + len(strings))
        strings.extend(text.encode("cp932") + b"\x00")
    size = offset + len(strings)
    return (struct.pack("<7I", 0x10000, size, 0, 1, len(texts), table, 0)
            + struct.pack("<3I", 0, len(texts) - 1, 0)
            + struct.pack(f"<{len(offsets)}I", *offsets) + strings)


def make_archive(directory, raw, *, compressed=True, name="Dialog.fmg"):
    directory.mkdir(parents=True, exist_ok=True)
    stored = zlib.compress(raw) if compressed else raw
    fat = bytearray(44)
    struct.pack_into("<2I", fat, 0, 0x210, 44)
    struct.pack_into("<5I", fat, 16, 44, 0, 36, 0, 1)
    struct.pack_into("<2I", fat, 36, 44, 0)
    fat.extend(name.encode("ascii") + b"\x00")
    bhd = (b"LDMU" + struct.pack("<6I", 0x210, 1, len(stored), 0, 0, 0)
           + struct.pack("<4I", 111, 0, len(raw), len(stored) if compressed else 0) + bytes(24))
    for suffix, data in (("FAT", fat), ("BHD", bhd), ("BND", stored)):
        (directory / f"POKAPOKA.{suffix}").write_bytes(data)
