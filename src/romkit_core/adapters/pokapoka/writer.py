"""Poka Poka FMG/BND fixed-extent writer."""
import hashlib
import struct
import zlib
from romkit_core.errors import ValidationError
from romkit_core.tasks import report
from .reader import fmg_candidates, scan_archive, MAX_TABLE_BYTES
from .repack import grow_fmg, indexed_strings

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
    verified_tables = {}
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
            if experimental:
                output = grow_fmg(raw, changes[logical], logical)
            else:
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
            verified_tables[logical] = indexed_strings(output, logical)
            next_offset = min(next((offset for offset in offsets if offset > origin["offset"]), bnd_path.stat().st_size), bnd_path.stat().st_size)
            capacity = next_offset - origin["offset"]
            if capacity < origin["stored_size"]:
                raise ValidationError("Las entradas del contenedor se solapan")
            if origin["compression"] == "zlib":
                try:
                    stored = _compress(output, capacity)
                except ValidationError as exc:
                    raise ValidationError(f'{logical} · modo {"pruebas" if experimental else "normal"}: {exc}. La reubicación fuera de esta asignación no está implementada') from exc
                struct.pack_into("<I", bhd, 28 + origin["slot"] * 40 + 12, len(stored))
            else:
                stored = bytes(output)
                if len(stored) > capacity:
                    raise ValidationError(f"{logical}: tabla requiere {len(stored)} bytes y dispone de {capacity}; ampliación fuera de la asignación no implementada")
            if len(stored) > origin["stored_size"]:
                bundle.seek(origin["offset"] + origin["stored_size"])
                padding = bundle.read(len(stored) - origin["stored_size"])
                if any(padding) or len(padding) != len(stored) - origin["stored_size"]:
                    raise ValidationError(f'{logical}: requiere {len(stored)} bytes, disponibles {origin["stored_size"]}; relleno ocupado, no se puede ampliar')
            # Reject aliases and overlapping members, including resources not selected for translation.
            for position in range(28, len(bhd), 40):
                if position == 28 + origin["slot"] * 40:
                    continue
                sector, raw_length, compressed_length = struct.unpack_from('<3I', bhd, position + 4)
                start = sector * 1024
                length = compressed_length or raw_length
                if length and start < origin["offset"] + max(len(stored), origin["stored_size"]) and start + length > origin["offset"]:
                    raise ValidationError(f'{logical}: otro recurso comparte la asignación BHD')
            struct.pack_into('<I', bhd, 28 + origin["slot"] * 40 + 8, len(output))
            bundle.seek(origin["offset"])
            bundle.write(stored)
            table_count += 1
    bhd_path.write_bytes(bhd)
    # Re-read the complete archive before publishing any image.
    from .reader import iter_archive_members
    checked = set()
    for _, _, raw, origin in iter_archive_members(directory, parent, progress=progress, suffixes={'.fmg'}):
        logical = origin['logical_path']
        if logical in verified_tables:
            if indexed_strings(raw, logical) != verified_tables[logical]:
                raise ValidationError(f'{logical}: la verificación por índice del texto reconstruido ha fallado')
            checked.add(logical)
        elif origin != fresh[logical]:
            raise ValidationError(f'{logical}: se ha alterado una tabla no seleccionada')
    if checked != set(logicals):
        raise ValidationError('Faltan tablas en la verificación del contenedor')
    replacements[f"{parent}/POKAPOKA.BHD"] = bhd_path
    replacements[archive] = bnd_path
    return replacements, table_count
