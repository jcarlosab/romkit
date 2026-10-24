from dataclasses import dataclass, replace
import hashlib
from pathlib import Path

from romkit_core.errors import ValidationError
from romkit_core.models import InputImage
from romkit_core.platforms import PlatformCandidate, PlatformRegistry
from romkit_core.tasks import ProgressCallback, report


@dataclass(frozen=True)
class ImageInspection:
    image: InputImage
    candidates: tuple[PlatformCandidate, ...]


class ImageService:
    def __init__(self, registry: PlatformRegistry):
        self.registry = registry

    def inspect(self, path: str | Path, *, progress: ProgressCallback | None = None) -> ImageInspection:
        path = Path(path).resolve(strict=True)
        if not path.is_file():
            raise ValidationError("La imagen debe ser un archivo")
        before = path.stat()
        digest, size = hashlib.sha256(), 0
        report(progress, 0, before.st_size, "Calculando SHA-256")
        with path.open("rb") as stream:
            while block := stream.read(1024 * 1024):
                digest.update(block)
                size += len(block)
                report(progress, size, before.st_size, "Calculando SHA-256")
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or size != before.st_size:
            raise ValidationError("La imagen cambió durante la lectura; vuelve a abrirla")
        report(progress, size, size, "Identificando plataforma")
        candidates = tuple(self.registry.detect(path))
        reliable = len(candidates) == 1 and candidates[0].probe.confidence >= 0.9
        detected = candidates[0].backend_id if reliable else None
        return ImageInspection(InputImage(path, size, digest.hexdigest(), detected_platform=detected), candidates)

    def select_platform(self, inspection: ImageInspection, backend_id: str) -> InputImage:
        self.registry.resolve(backend_id)
        return replace(inspection.image, selected_platform=backend_id)
