"""Fixed-capacity BTX writer: preserve ARCV, MARV and KCAP layouts exactly."""
import hashlib
import struct

from .archive import iter_arcv
from .text import resource_btx_candidates
from romkit_core.errors import ValidationError
from romkit_core.tasks import report


def patch_btx_resource(raw, logical, structure, changes, *, experimental=False, capacity=None):
    if experimental and any(len(target) > c.length_bytes for c, target in changes):
        from .repack import repack_resource
        return repack_resource(raw, logical, structure, changes, capacity=capacity)
    valid = resource_btx_candidates(raw, logical, structure)
    indexed = {candidate.offset: candidate for candidate in valid}
    output = bytearray(raw)
    previous_end = 0
    for candidate, target in sorted(changes, key=lambda pair: pair[0].offset):
        expected = indexed.get(candidate.offset)
        end = candidate.offset + candidate.length_bytes + 2
        if (expected is None or expected.text != candidate.text or expected.length_bytes != candidate.length_bytes
                or candidate.encoding != "utf-16-le" or candidate.terminator != b"\0\0"
                or candidate.offset < previous_end):
            raise ValidationError("Texto BTX original modificado, no indexado o solapado")
        if any(candidate.offset < other.offset < end for other in valid):
            raise ValidationError("El texto BTX comparte bytes con otra cadena indexada")
        if len(target) % 2 or len(target) > candidate.length_bytes:
            raise ValidationError("La traducción BTX supera su espacio original en bytes UTF-16LE")
        try:
            decoded = target.decode("utf-16-le", errors="strict")
        except UnicodeDecodeError as exc:
            raise ValidationError("Traducción BTX UTF-16LE inválida") from exc
        if "\0" in decoded:
            raise ValidationError("La traducción BTX contiene un terminador interno")
        output[candidate.offset:end] = target + bytes(end - candidate.offset - len(target))
        previous_end = end
    rebuilt = {c.offset: c.text for c in resource_btx_candidates(output, logical, structure)}
    targets = {c.offset: target.decode("utf-16-le") for c, target in changes}
    for original in valid:
        if rebuilt.get(original.offset, "") != targets.get(original.offset, original.text):
            raise ValidationError("La verificación del recurso BTX reconstruido ha fallado")
    if len(output) != len(raw):
        raise ValidationError("El recurso BTX cambió de tamaño")
    return bytes(output)


def rebuild_arcv(reader, iso, iso_entries, staging, archive, logicals, origins, changes, *, progress=None, experimental=False):
    parent = archive.rsplit("/", 1)[0]
    if archive not in iso_entries:
        raise ValidationError("Falta ARCVINFO.BIN en la ISO")
    reader.extract_file(iso, iso_entries[archive], staging)
    index_path = staging / archive
    index = index_path.read_bytes()
    updated_index = bytearray(index)
    if len(index) < 32 or index[:4] != b"VCRA":
        raise ValidationError("Índice ARCV inválido")
    version, count, sector_size = struct.unpack_from("<III", index, 4)
    if version != 0x101 or sector_size != 2048 or count > 50000 or 32 + count * 24 > len(index):
        raise ValidationError("Índice ARCV no compatible")
    volumes, ranges = set(), []
    for row in range(count):
        size, volume, _, sector = struct.unpack_from("<4I", index, 32 + row * 24)
        if volume > 99:
            raise ValidationError("Volumen ARCV inválido")
        volumes.add(volume)
        if size:
            ranges.append((volume, sector * 2048, sector * 2048 + size))
    ranges.sort()
    for previous, current in zip(ranges, ranges[1:]):
        if previous[0] == current[0] and previous[2] > current[1]:
            raise ValidationError("Las entradas ARCV comparten o solapan datos; no se pueden reinsertar de forma aislada")
    for volume in volumes:
        logical = f"{parent}/ARCV{volume}.BIN"
        if logical not in iso_entries:
            raise ValidationError(f"Falta {logical} en la ISO")
        reader.extract_file(iso, iso_entries[logical], staging)
    selected, patched, seen = set(logicals), {}, set()
    try:
        for name, raw, _, structure, location in iter_arcv(index_path, with_locations=True):
            logical = archive + ".contents/" + name
            if logical not in selected:
                continue
            if logical in seen:
                raise ValidationError("Nombre de recurso ARCV duplicado")
            seen.add(logical)
            origin = origins[logical]
            if (origin.get("archive") != archive or origin.get("member") != name
                    or origin.get("format") != "btx" or hashlib.sha256(raw).hexdigest() != origin.get("sha256")):
                raise ValidationError("El recurso BTX original no coincide con la metadata exportada")
            report(progress, len(seen), len(selected), f"Reinsertando BTX · {name}")
            volume = f"{parent}/ARCV{location['volume']}.BIN"
            path = staging / volume
            following = min((start for number,start,_ in ranges if number == location['volume']
                             and start > location['offset']), default=path.stat().st_size)
            capacity = min((len(raw) + 2047) // 2048 * 2048, following - location['offset'],
                           path.stat().st_size - location['offset'])
            if struct.unpack_from('<II', index, location['index_record'] + 16) != (0, 0):
                capacity = len(raw)  # Unknown/MARV descriptors may contain further sizes.
            output = patch_btx_resource(raw, logical, structure, changes[logical], experimental=experimental,
                                        capacity=capacity if experimental else len(raw))
            with path.open("r+b") as stream:
                if len(output) > len(raw):
                    stream.seek(location['offset'] + len(raw))
                    padding = stream.read(len(output) - len(raw))
                    if len(padding) != len(output) - len(raw) or any(padding):
                        raise ValidationError('El relleno ARCV contiene datos; no se puede ampliar el tutorial')
                    struct.pack_into('<I', updated_index, location['index_record'], len(output))
                stream.seek(location["offset"])
                stream.write(output)
                stream.flush()
                stream.seek(location["offset"])
                if stream.read(len(output)) != output:
                    raise ValidationError("La verificación del volumen ARCV ha fallado")
            patched[volume] = path
    except (ValueError, OSError) as exc:
        raise ValidationError(str(exc)) from exc
    if seen != selected:
        raise ValidationError("Faltan recursos BTX en el índice original")
    if index_path.read_bytes() != index:
        raise ValidationError("El índice ARCV cambió inesperadamente")
    if updated_index != index:
        index_path.write_bytes(updated_index)
        # Reopen through the index that will actually be installed in the ISO.
        for name, raw, _, structure in iter_arcv(index_path):
            logical = archive + '.contents/' + name
            if logical in selected:
                resource_btx_candidates(raw, logical, structure)
        patched[archive] = index_path
    return patched, len(seen)
