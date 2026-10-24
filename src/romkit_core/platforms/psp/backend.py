from pathlib import Path
from dataclasses import replace
import hashlib

from romkit_core.analysis.inventory import inventory, detect_type
from romkit_core.errors import PlatformError
from romkit_core.image.service import ImageService
from romkit_core.platforms.base import ExtractionResult, PlatformImage, ProbeResult
from romkit_core.platforms.iso9660 import Iso9660Reader
from romkit_core.platforms.registry import PlatformRegistry
from romkit_core.tasks import ProgressCallback
from romkit_core.models import ResourceEntry
from .models import PspLayout


class PspBackend:
    id = "psp"
    display_name = "PlayStation Portable (PSP)"

    def __init__(self, reader: Iso9660Reader | None = None):
        self.reader = reader if reader is not None else Iso9660Reader()
        self.layout = PspLayout()

    def probe(self, path: Path) -> ProbeResult:
        try:
            with self.reader.open(path) as image:
                entries = {entry.logical_path.upper(): entry for entry in self.reader.walk(image)}
        except (PlatformError, OSError):
            return ProbeResult(False)
        directory = entries.get(self.layout.game_directory)
        parameter, boot = entries.get(self.layout.parameter_file), entries.get(self.layout.boot_file)
        if directory and directory.is_directory and parameter and not parameter.is_directory and boot and not boot.is_directory:
            return ProbeResult(True, 0.98, ("Directorio PSP_GAME", "PARAM.SFO y SYSDIR/EBOOT.BIN"))
        return ProbeResult(False)

    def open_image(self, path: Path) -> PlatformImage:
        if not self.probe(path).compatible:
            raise PlatformError("La imagen no contiene una estructura PSP compatible")
        registry = PlatformRegistry()
        inspection = ImageService(registry).inspect(path)
        return PlatformImage(self.id, replace(inspection.image, detected_platform=self.id, selected_platform=self.id))

    def list_resources(self, image: PlatformImage):
        if image.backend_id != self.id:
            raise PlatformError("La imagen no pertenece al backend PSP")
        resources = []
        with self.reader.open(image.source.path) as iso:
            for entry in self.reader.walk(iso):
                if entry.is_directory:
                    continue
                digest, header = hashlib.sha256(), b""
                for block in self.reader.read_chunks(iso, entry):
                    if not header:
                        header = block[:16]
                    digest.update(block)
                extension = Path(entry.logical_path).suffix.lower()
                status, kind = detect_type(header, extension)
                id = "resource." + hashlib.sha256(entry.logical_path.encode("utf-8")).hexdigest()[:24]
                resources.append(ResourceEntry(id, entry.logical_path, entry.size_bytes, digest.hexdigest(), kind, type_status=status, extension=extension))
        return resources

    def extract(self, image: PlatformImage, destination: Path, *, progress: ProgressCallback | None = None) -> ExtractionResult:
        if image.backend_id != self.id:
            raise PlatformError("La imagen no pertenece al backend PSP")
        with self.reader.open(image.source.path) as iso:
            self.reader.extract_all(iso, destination, progress=progress)
        return ExtractionResult(destination, tuple(inventory(destination, progress=progress)))
