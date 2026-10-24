"""Streaming BPS1 linear patches (SourceRead/TargetRead), no external binary.

Public-domain BPS specification by byuu, preserved in Flips/bps_spec.md.
Output is standard BPS; verification reconstructs the target stream in memory
blocks and compares it byte-for-byte, without making another complete ISO copy.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import struct
import tempfile
import zlib

from romkit_core.errors import ValidationError
from romkit_core.tasks import report

BLOCK = 65536


def number(value):
    data = bytearray()
    while True:
        digit, value = value & 127, value >> 7
        if not value:
            data.append(digit | 128)
            return bytes(data)
        data.append(digit)
        value -= 1


def read_number(stream):
    value, shift = 0, 1
    for _ in range(10):
        raw = stream.read(1)
        if not raw:
            raise ValidationError('Parche BPS truncado')
        digit = raw[0]
        value += (digit & 127) * shift
        if digit & 128:
            return value
        shift <<= 7
        value += shift
    raise ValidationError('Número BPS fuera de límites')


def verify_bps(patch, source, target, *, progress=None):
    size = patch.stat().st_size
    if size < 19:
        raise ValidationError('Parche BPS truncado')
    crc = 0
    with patch.open('rb') as stream:
        remaining = size - 4
        while remaining:
            block = stream.read(min(BLOCK, remaining))
            if not block:
                raise ValidationError('Parche BPS truncado durante la verificación')
            crc = zlib.crc32(block, crc)
            remaining -= len(block)
        if stream.read(4) != struct.pack('<I', crc & 0xffffffff):
            raise ValidationError('CRC del parche BPS incorrecto')
    with patch.open('rb') as stream, source.open('rb') as original, target.open('rb') as expected:
        if stream.read(4) != b'BPS1' or read_number(stream) != source.stat().st_size or read_number(stream) != target.stat().st_size:
            raise ValidationError('El parche BPS no corresponde a los archivos')
        metadata = read_number(stream)
        if metadata > size - stream.tell() - 12:
            raise ValidationError('Metadata BPS fuera de límites')
        stream.seek(metadata, 1)
        offset, target_crc, source_crc = 0, 0, 0
        while block := original.read(BLOCK):
            source_crc = zlib.crc32(block, source_crc)
        while stream.tell() < size - 12:
            command = read_number(stream)
            mode, remaining = command & 3, (command >> 2) + 1
            if mode not in (0, 1) or offset + remaining > target.stat().st_size:
                raise ValidationError('Acción BPS no válida para la verificación lineal')
            original.seek(offset)
            if mode == 0 and offset + remaining > source.stat().st_size:
                raise ValidationError('Lectura BPS fuera del original')
            while remaining:
                count = min(BLOCK, remaining)
                if mode == 1 and stream.tell() + count > size - 12:
                    raise ValidationError('Datos BPS truncados')
                block = original.read(count) if mode == 0 else stream.read(count)
                if len(block) != count or expected.read(count) != block:
                    raise ValidationError('El parche BPS no reconstruye exactamente la imagen traducida')
                target_crc = zlib.crc32(block, target_crc)
                remaining -= count
                offset += count
                report(progress, offset, target.stat().st_size, 'Verificando parche BPS')
        footer = stream.read(12)
        if offset != target.stat().st_size or len(footer) != 12 or struct.unpack('<II', footer[:8]) != (source_crc & 0xffffffff, target_crc & 0xffffffff):
            raise ValidationError('CRC o tamaño de los archivos BPS incorrecto')


@dataclass(frozen=True)
class DeltaResult:
    path: Path
    size: int
    source_sha256: str
    target_sha256: str


def create_bps(source, target, destination, *, progress=None, expected_source_sha256=None):
    source, target = Path(source).resolve(strict=True), Path(target).resolve(strict=True)
    destination = Path(destination).absolute()
    if source == target or destination.exists() or destination.is_symlink() or destination.resolve() in (source, target):
        raise ValidationError('Selecciona dos imágenes distintas y un nombre nuevo para el parche')
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_hash, target_hash = hashlib.sha256(), hashlib.sha256()
    with tempfile.TemporaryDirectory(prefix='.romkit-bps-', dir=destination.parent) as temporary:
        patch = Path(temporary) / 'patch.bps'
        with source.open('rb') as original, target.open('rb') as modified, patch.open('wb') as output:
            crc, source_crc, target_crc, offset, pending = 0, 0, 0, 0, 0
            def write(data):
                nonlocal crc
                output.write(data)
                crc = zlib.crc32(data, crc)
            write(b'BPS1' + number(source.stat().st_size) + number(target.stat().st_size) + number(0))
            while block := modified.read(BLOCK):
                before = original.read(len(block))
                source_hash.update(before)
                target_hash.update(block)
                source_crc = zlib.crc32(before, source_crc)
                target_crc = zlib.crc32(block, target_crc)
                pos = 0
                while pos < len(block):
                    same = pos < len(before) and before[pos] == block[pos]
                    end = pos + 1
                    if before == block:
                        end = len(block)
                    else:
                        while end < len(block) and (end < len(before) and before[end] == block[end]) == same:
                            end += 1
                    if same:
                        pending += end - pos
                    else:
                        if pending:
                            write(number((pending - 1) << 2))
                            pending = 0
                        write(number(((end - pos - 1) << 2) | 1))
                        write(block[pos:end])
                    pos = end
                offset += len(block)
                report(progress, offset, target.stat().st_size, 'Creando parche BPS')
            while block := original.read(BLOCK):
                source_hash.update(block)
                source_crc = zlib.crc32(block, source_crc)
            if pending:
                write(number((pending - 1) << 2))
            if expected_source_sha256 and source_hash.hexdigest() != expected_source_sha256:
                raise ValidationError('La imagen original no corresponde a la ISO abierta')
            write(struct.pack('<II', source_crc & 0xffffffff, target_crc & 0xffffffff))
            output.write(struct.pack('<I', crc & 0xffffffff))
            output.flush()
            os.fsync(output.fileno())
        verify_bps(patch, source, target, progress=progress)
        os.link(patch, destination)
    return DeltaResult(destination, destination.stat().st_size, source_hash.hexdigest(), target_hash.hexdigest())
