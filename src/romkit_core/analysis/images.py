"""Export common image files and structurally verified embedded PNG streams."""
from dataclasses import dataclass
import hashlib
import json
import mmap
from pathlib import Path
import struct
import tempfile
from uuid import uuid4
import zlib

from romkit_core.tasks import report
from romkit_core.analysis.containers import Traversal, walk_payloads
from romkit_core.analysis.gim import MAGIC as GIM_MAGIC, gim_end, decode_gim
from romkit_core.adapters.registry import enabled_adapters

PNG = b"\x89PNG\r\n\x1a\n"
MAX_IMAGE_BYTES = 64 * 1024 * 1024


def png_end(data, start):
    offset, first = start + 8, True
    has_image_data = False
    limit = min(len(data), start + MAX_IMAGE_BYTES)
    while offset + 12 <= limit:
        size = struct.unpack_from(">I", data, offset)[0]
        end = offset + 12 + size
        if end > limit:
            return None
        kind = bytes(data[offset + 4:offset + 8])
        if first and (kind != b"IHDR" or size != 13):
            return None
        if first:
            width, height = struct.unpack_from(">II", data, offset + 8)
            if not width or not height or width * height > 100_000_000:
                return None
        if zlib.crc32(data[offset + 4:end - 4]) & 0xffffffff != struct.unpack_from(">I", data, end - 4)[0]:
            return None
        if kind == b"IEND":
            return end if size == 0 and has_image_data else None
        if kind == b"IDAT":
            has_image_data = True
        first, offset = False, end
    return None


def image_ranges(data):
    offset = 0
    while (start := data.find(PNG, offset)) >= 0:
        end = png_end(data, start)
        if end is not None:
            yield start, end, "png"
        offset = end if end is not None else start + 8
    if not 0 < len(data) <= MAX_IMAGE_BYTES:
        return
    head = bytes(data[:16])
    if head.startswith(b"\xff\xd8\xff") and data[-2:] == b"\xff\xd9":
        yield 0, len(data), "jpg"
    elif head.startswith((b"GIF87a", b"GIF89a")) and data[-1] == 0x3b:
        yield 0, len(data), "gif"
    elif head.startswith(b"BM") and len(data) >= 26 and struct.unpack_from("<I", data, 2)[0] == len(data):
        yield 0, len(data), "bmp"
    elif len(head) >= 16 and head[:4] == b"RIFF" and head[8:12] == b"WEBP" and struct.unpack_from("<I", data, 4)[0] + 8 == len(data):
        yield 0, len(data), "webp"


@dataclass(frozen=True)
class ImageExport:
    path: Path
    count: int
    containers: int = 0
    duplicates: int = 0
    warnings: int = 0


def gim_ranges(data):
    offset = 0
    while (start := data.find(GIM_MAGIC, offset)) >= 0:
        end = gim_end(data, start)
        if end is not None:
            yield start, end, "gim"
        offset = end if end is not None else start + len(GIM_MAGIC)


def export_images(resources, workspace, destination, *, progress=None):
    destination = Path(destination).resolve(strict=True)
    output = destination / ("ROMKit-imagenes-" + uuid4().hex[:8])
    manifest, cached, files = [], {}, {}
    traversal = Traversal()
    enabled = {a.id for a in enabled_adapters()}
    paths = {resource.logical_path for resource in resources}
    bundles = {path for path in paths if "pokapoka" in enabled and path.endswith(".BND")
               and path[:-4] + ".FAT" in paths and path[:-4] + ".BHD" in paths}
    bundle_indexes = {path[:-4] + suffix for path in bundles for suffix in (".FAT", ".BHD")}
    arcv_indexes = {path for path in paths if "digimon" in enabled and path.endswith("/ARCVINFO.BIN")}
    arcv_volumes = {path for path in paths if any(path.rsplit("/", 1)[0] == index.rsplit("/", 1)[0]
        and path.rsplit("/", 1)[-1].startswith("ARCV") and path.endswith(".BIN") for index in arcv_indexes)}
    with tempfile.TemporaryDirectory(prefix=".romkit-images-", dir=destination) as temporary:
        staging = Path(temporary)
        def process(data, logical, index, base=None, structure=None, source_kind=None, source_offset=0):
            if base is not None and structure is not None:
                from romkit_core.adapters.digimon.images import decode_gmio
                offset = 0
                while (offset := data.find(b"GMIO", offset, structure)) >= 0:
                    report(progress, index, len(resources), f"Extrayendo textura · {logical}")
                    try:
                        image = decode_gmio(data, offset, base, structure)
                        if image is not None:
                            process(image.png, logical + f"!gmio/{offset:x}", index,
                                    source_kind="gmio", source_offset=offset)
                    except ValueError as exc:
                        traversal.warn(logical + f"@{offset:x}", exc)
                    offset += 4
            def visiting(name):
                report(progress, index, len(resources), f"Abriendo contenedor · {name}")
            for name, payload in walk_payloads(data, logical, traversal, progress=visiting):
                if bytes(payload[:len(GIM_MAGIC)]) == GIM_MAGIC and gim_end(payload, 0) is None:
                    traversal.warn(name, "Cabecera GIM truncada o inválida")
                for start, end, kind in (*image_ranges(payload), *gim_ranges(payload)):
                    report(progress, index, len(resources), f"Extrayendo imagen · {name}")
                    raw = bytes(payload[start:end])
                    key = kind + hashlib.sha256(raw).hexdigest()
                    if key not in cached:
                        try:
                            converted = [(image.png, "png", image.width, image.height) for image in decode_gim(raw)] if kind == "gim" else [(raw, kind, None, None)]
                        except ValueError as exc:
                            traversal.warn(name + f"@{start:x}", exc)
                            cached[key] = []
                            continue
                        cached[key] = []
                        for content, extension, width, height in converted:
                            digest = hashlib.sha256(content).hexdigest()
                            if digest not in files:
                                if len(files) >= 20000:
                                    traversal.warn(name, "Límite de 20000 imágenes alcanzado")
                                    continue
                                relative = f"imagenes/{len(files) + 1:05d}-{kind}.{extension}"
                                target = staging / relative
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_bytes(content)
                                files[digest] = relative
                            cached[key].append({"file": files[digest], "sha256": digest,
                                                "width": width, "height": height})
                    for image in cached[key]:
                        manifest.append({"source": name, "offset": source_offset if source_kind else start,
                                         "length_bytes": None if source_kind else end - start,
                                         "source_format": source_kind or kind, **image})
        for index, resource in enumerate(resources):
            if resource.logical_path in arcv_indexes:
                from romkit_core.adapters.digimon.archive import iter_arcv
                traversal.containers += 1
                source = workspace.layout.path("extracted", resource.logical_path)
                try:
                    for name, raw, base, structure in iter_arcv(source):
                        traversal.charge(len(raw))
                        process(raw, resource.logical_path + "!arcv/" + name, index, base, structure)
                except (ValueError, OSError) as exc:
                    traversal.warn(resource.logical_path, exc)
                continue
            if resource.logical_path in arcv_volumes:
                continue
            if resource.logical_path in bundle_indexes:
                continue
            report(progress, index, len(resources), f"Buscando imágenes · {resource.logical_path}")
            source = workspace.layout.path("extracted", resource.logical_path)
            if source.is_symlink() or not source.stat().st_size:
                continue
            if resource.logical_path in bundles:
                from romkit_core.adapters.pokapoka.reader import iter_archive_members
                traversal.containers += 1
                parent = resource.logical_path.rsplit("/", 1)[0]
                try:
                    for slot, name, raw, origin in iter_archive_members(source.parent, parent, stem=source.stem, on_error=traversal.warn):
                        traversal.charge(len(raw))
                        process(raw, origin["logical_path"], index)
                except ValueError as exc:
                    traversal.warn(resource.logical_path, exc)
                continue
            with source.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
                process(data, resource.logical_path, index)
        if not manifest and not traversal.warnings:
            return ImageExport(destination, 0)
        duplicates = len(manifest) - len(files)
        (staging / "imagenes.json").write_text(json.dumps({"images": manifest, "containers": traversal.containers,
            "duplicates": duplicates, "warnings": traversal.warnings}, ensure_ascii=False, indent=2), encoding="utf-8")
        report(progress, len(resources), len(resources), f"Guardando {len(files)} imágenes")
        staging.rename(output)
    return ImageExport(output, len(files), traversal.containers, duplicates, len(traversal.warnings))
