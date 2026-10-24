"""Bounded reader for PSP VCRA 0x101 indexes (ARCVINFO/ARCVn)."""
import struct


def iter_arcv(index_path, *, with_locations=False):
    if index_path.is_symlink() or index_path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("Índice ARCV demasiado grande o enlazado")
    data = index_path.read_bytes()
    if len(data) < 32 or data[:4] != b"VCRA":
        raise ValueError("Índice ARCV inválido")
    version, count, sector_size = struct.unpack_from("<III", data, 4)
    if version != 0x101 or sector_size != 2048 or count > 50000 or 32 + count * 24 > len(data):
        raise ValueError("Versión o tabla ARCV no compatible")
    for n in range(count):
        size, volume, name_at, sector, descriptor, _ = struct.unpack_from("<6I", data, 32 + n * 24)
        if size > 64 * 1024 * 1024 or volume > 99 or not 32 + count * 24 <= name_at < len(data):
            raise ValueError("Entrada ARCV fuera de límites")
        end = data.find(b"\0", name_at, min(len(data), name_at + 1024))
        if end < 0:
            raise ValueError("Nombre ARCV truncado")
        name = data[name_at:end].decode("utf-8", errors="replace")
        source = index_path.parent / f"ARCV{volume}.BIN"
        if source.is_symlink() or sector * sector_size + size > source.stat().st_size:
            raise ValueError("Datos ARCV fuera del volumen")
        base = structure = None
        if descriptor:
            if descriptor + 32 > len(data) or data[descriptor:descriptor + 4] != b"MARV":
                raise ValueError("Descriptor MARV inválido")
            structure, _, length, alignment = struct.unpack_from("<4I", data, descriptor + 8)
            if not alignment or alignment > 4096 or alignment & (alignment - 1):
                raise ValueError("Alineación MARV inválida")
            base = (structure + alignment - 1) // alignment * alignment
            if base + length > size:
                raise ValueError("Datos MARV truncados")
        with source.open("rb") as stream:
            stream.seek(sector * sector_size)
            raw = stream.read(size)
        member = (name, raw, base, structure)
        if with_locations:
            yield (*member, {"volume": volume, "offset": sector * sector_size, "size": size,
                            "index_record": 32 + n * 24})
        else:
            yield member
