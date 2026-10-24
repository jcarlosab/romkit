"""Poka Poka FMG/BND fixed-extent writer."""
import hashlib
import struct
import zlib
from romkit_core.errors import ValidationError
from romkit_core.tasks import report
from .reader import fmg_candidates, scan_archive, MAX_TABLE_BYTES

def _compress(raw, capacity):
    choices = []
    for strategy in (zlib.Z_DEFAULT_STRATEGY, zlib.Z_FILTERED, zlib.Z_RLE, zlib.Z_HUFFMAN_ONLY, zlib.Z_FIXED):
        encoder = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS, 9, strategy)
        choices.append(encoder.compress(raw) + encoder.flush())
    stored = min(choices, key=len)
    if len(stored) > capacity:
        raise ValidationError(f"La tabla comprimida ocupa {len(stored)} bytes y solo caben {capacity}. Acorta las traducciones")
    return stored



def rebuild_pokapoka(reader, iso, iso_entries, staging, archive, logicals, origins, changes, *, progress=None, experimental=False):
    table_count, replacements = 0, {}
    parent = archive.rsplit("/", 1)[0]
    for suffix in ("FAT", "BHD", "BND"):
        logical = f"{parent}/POKAPOKA.{suffix}"
        if logical not in iso_entries:
            raise ValidationError(f"Falta {logical} en la ISO")
        reader.extract_file(iso, iso_entries[logical], staging)
    directory = staging / parent
    _, fresh_origins = scan_archive(directory, parent, progress=progress)
    fresh = {entry["logical_path"]: entry for entry in fresh_origins}
    bhd_path, bnd_path = directory / "POKAPOKA.BHD", directory / "POKAPOKA.BND"
    bhd = bytearray(bhd_path.read_bytes())
    offsets = sorted({struct.unpack_from("<I", bhd, position + 4)[0] * 1024
                      for position in range(28, len(bhd), 40)})
    with bnd_path.open("r+b") as bundle:
        for logical in logicals:
            report(progress, table_count, len(changes), f"Reinsertando · {logical.rsplit('/', 1)[-1]}")
            origin = origins[logical]
            if fresh.get(logical) != origin:
                raise ValidationError("La tabla original no coincide con la metadata exportada")
            if origin["raw_size"] > MAX_TABLE_BYTES:
                raise ValidationError("Tabla demasiado grande")
            bundle.seek(origin["offset"])
            stored = bundle.read(origin["stored_size"])
            raw = zlib.decompress(stored) if origin["compression"] == "zlib" else stored
            if hashlib.sha256(raw).hexdigest() != origin["sha256"]:
                raise ValidationError("Hash de tabla incorrecto")
            valid = {candidate.offset: candidate for candidate in fmg_candidates(raw, logical)}
            output = bytearray(raw)
            end = 0
            for candidate, target in sorted(changes[logical], key=lambda change: change[0].offset):
                expected = valid.get(candidate.offset)
                if (expected is None or expected.text != candidate.text or expected.length_bytes != candidate.length_bytes
                        or candidate.offset < end):
                    raise ValidationError("Texto original modificado, no indexado o solapado")
                end = candidate.offset + candidate.length_bytes + 1
                if any(candidate.offset < offset < end for offset in valid):
                    raise ValidationError("El texto comparte bytes con otra cadena indexada; no puede sustituirse de forma aislada")
                output[candidate.offset:end] = target + bytes(end - candidate.offset - len(target))
            # Keep FMG offsets and raw length unchanged; shorter targets are NUL padded.
            fmg_candidates(output, logical)
            next_offset = next((offset for offset in offsets if offset > origin["offset"]), bnd_path.stat().st_size)
            capacity = next_offset - origin["offset"]
            if capacity < origin["stored_size"]:
                raise ValidationError("Las entradas del contenedor se solapan")
            if origin["compression"] == "zlib":
                stored = _compress(output, capacity)
                struct.pack_into("<I", bhd, 28 + origin["slot"] * 40 + 12, len(stored))
            else:
                stored = bytes(output)
                if len(stored) > capacity:
                    raise ValidationError("La tabla no cabe en el contenedor")
            bundle.seek(origin["offset"])
            bundle.write(stored)
            table_count += 1
    bhd_path.write_bytes(bhd)
    # Re-read the complete archive before publishing any image.
    rebuilt, _ = scan_archive(directory, parent, progress=progress)
    rebuilt_by_offset = {(c.logical_path, c.offset): c.text for c in rebuilt}
    for logical in logicals:
        for candidate, target in changes[logical]:
            if rebuilt_by_offset.get((logical, candidate.offset), "") != target.decode("cp932"):
                raise ValidationError("La verificación del texto reconstruido ha fallado")
    replacements[f"{parent}/POKAPOKA.BHD"] = bhd_path
    replacements[archive] = bnd_path
    return replacements, table_count
