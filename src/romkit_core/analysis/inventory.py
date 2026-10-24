import hashlib
from pathlib import Path

from romkit_core.errors import ValidationError
from romkit_core.models import ResourceEntry
from romkit_core.tasks import ProgressCallback, report


def detect_type(header: bytes, extension: str) -> tuple[str, str]:
    for magic, name in ((b"\x89PNG\r\n\x1a\n", "png"), (b"\x7fELF", "elf"), (b"RIFF", "riff"), (b"PK\x03\x04", "zip"), (b"\xff\xd8\xff", "jpeg")):
        if header.startswith(magic):
            return "known", name
    if extension.lower() in {".txt", ".json", ".xml", ".csv", ".sfo", ".bin", ".dat"}:
        return "candidate", extension.lower().lstrip(".")
    return "unknown", "unknown"


def inventory(root: str | Path, *, progress: ProgressCallback | None = None) -> list[ResourceEntry]:
    root = Path(root).resolve(strict=True)
    files = sorted((path for path in root.rglob("*") if path.is_file()), key=lambda path: path.relative_to(root).as_posix())
    resources = []
    for index, path in enumerate(files):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValidationError(f"El recurso sale del directorio extraído: {path}")
        report(progress, index, len(files), path.name)
        with path.open("rb") as stream:
            header = stream.read(16)
            digest = hashlib.sha256(header)
            while block := stream.read(1024 * 1024):
                digest.update(block)
        logical = path.relative_to(root).as_posix()
        status, kind = detect_type(header, path.suffix)
        resource_id = "resource." + hashlib.sha256(logical.encode("utf-8")).hexdigest()[:24]
        resources.append(ResourceEntry(resource_id, logical, path.stat().st_size, digest.hexdigest(), kind,
                                       type_status=status, extension=path.suffix.lower()))
    report(progress, len(files), len(files), "Inventario terminado")
    return resources
