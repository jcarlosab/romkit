"""Validate saved translations and build a separate PSP ISO with fixed extents."""
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import re
import struct
import tempfile
import zlib

from romkit_core.adapters.registry import adapter_for_archive
from romkit_core.errors import ValidationError
from romkit_core.models import TranslationStatus
from romkit_core.models.text_candidate import TextCandidate
from romkit_core.platforms.iso9660 import Iso9660Reader
from romkit_core.project import read_config, read_jsonl
from romkit_core.project.schema import stable_unit_id
from romkit_core.tasks import report
from romkit_core.validation import validate_translation


@dataclass(frozen=True)
class BuildResult:
    path: Path
    translated: int
    skipped: int
    tables: int
    experimental: bool = False


def _digest(path, progress=None):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            report(progress, stream.tell(), path.stat().st_size, "Comprobando imagen original")
            digest.update(block)
    return digest.hexdigest()


def _compress(raw, capacity):
    # Compatibility for callers of the original helper.
    from romkit_core.adapters.pokapoka.writer import _compress as compress
    return compress(raw, capacity)


def rebuild_project(project, workspace, image, destination, *, progress=None, experimental=False):
    project, destination = Path(project).resolve(strict=True), Path(destination).absolute()
    if destination.exists() or destination.is_symlink() or destination.resolve() == image.path.resolve():
        raise ValidationError("Elige un nombre nuevo para la ISO traducida")
    config = read_config(project / "project.toml")
    if not workspace.layout.path("metadata", "reinsert.json").is_file():
        raise ValidationError("Falta la metadata de reinserción. Abre la carpeta de trabajo con la que exportaste los textos")
    metadata = workspace.read_metadata("reinsert.json")
    if (config.platform != "psp" or config.source_sha256 != image.sha256
            or metadata.get("source_sha256") != image.sha256 or metadata.get("schema_version") != 1):
        raise ValidationError("El proyecto o la metadata no corresponden a la imagen PSP abierta")
    if workspace.load_source_metadata().sha256 != image.sha256 or _digest(image.path, progress) != image.sha256:
        raise ValidationError("La imagen original ha cambiado o no corresponde a la carpeta de trabajo")
    text_root = project / "text"
    if not text_root.is_dir() or text_root.is_symlink():
        raise ValidationError("Falta la carpeta text del proyecto")
    units = {}
    for path in sorted(text_root.glob("*.jsonl")):
        if path.is_symlink():
            raise ValidationError("No se admiten enlaces en los textos del proyecto")
        for unit in read_jsonl(path):
            if unit.id in units:
                raise ValidationError(f"ID de texto duplicado: {unit.id}")
            units[unit.id] = unit
    entries = metadata.get("entries", [])
    if len({entry["id"] for entry in entries}) != len(entries) or {entry["id"] for entry in entries} != set(units):
        raise ValidationError("Los textos no coinciden con la última exportación de esta carpeta de trabajo")
    origins = {entry["logical_path"]: entry for entry in metadata.get("archive_resources", [])}
    changes = defaultdict(list)
    translated, skipped = 0, 0
    for entry in entries:
        unit = units[entry["id"]]
        if unit.status == TranslationStatus.UNTRANSLATED:
            skipped += 1
            continue
        values = {key: value for key, value in entry.items() if key != "id"}
        candidate = TextCandidate.from_dict({**values, "text": unit.source})
        if stable_unit_id(candidate.logical_path, candidate.offset, candidate.encoding) != unit.id:
            raise ValidationError("La metadata del texto no corresponde a su ID")
        if candidate.logical_path not in origins:
            raise ValidationError(f"Falta el origen de la tabla {candidate.logical_path}. Vuelve a analizar y exportar")
        origin = origins[candidate.logical_path]
        archive = origin.get("archive", "")
        adapter = adapter_for_archive(archive)
        if candidate.transforms.steps or adapter is None or not adapter.accepts(candidate, origin):
            raise ValidationError("Formato de reinserción no compatible con los adaptadores habilitados")
        effective = replace(unit, encoding=candidate.encoding,
                            constraints=replace(unit.constraints, max_bytes=None if experimental and adapter.id == "digimon" else min(candidate.length_bytes,
                                unit.constraints.max_bytes if unit.constraints.max_bytes is not None else candidate.length_bytes)))
        validation = validate_translation(effective)
        if not validation.valid:
            raise ValidationError(f"{unit.id}: " + "; ".join(issue.message for issue in validation.issues))
        if "\0" in unit.target:
            raise ValidationError(f"{unit.id}: la traducción no puede contener bytes cero")
        # Older exports did not register game controls; protect them here too.
        controls = lambda text: Counter(re.findall(r"\{[^{}]+\}|<[^<>]+>|[\x01-\x08\x0b\x0c\x0e-\x1f]", text))
        if controls(unit.source) != controls(unit.target):
            raise ValidationError(f"{unit.id}: se han alterado variables o controles del texto")
        changes[candidate.logical_path].append((candidate, unit.target.encode(candidate.encoding)))
        translated += 1
    if not translated:
        raise ValidationError("No hay textos con estado Traducido o Revisado. Guarda los cambios en Translator")
    reader = Iso9660Reader()
    table_count = 0
    with tempfile.TemporaryDirectory(prefix="romkit-build-") as temporary:
        staging = Path(temporary)
        replacements = {}
        with reader.open(image.path) as iso:
            iso_entries = {entry.logical_path: entry for entry in reader.walk(iso) if not entry.is_directory}
            archive_groups = defaultdict(list)
            for logical in changes:
                archive = origins[logical]["archive"]
                archive_groups[archive].append(logical)
            for archive, logicals in archive_groups.items():
                adapter = adapter_for_archive(archive)
                if adapter is None:
                    raise ValidationError("No hay un adaptador de escritura habilitado para este juego")
                patched, count = adapter.rebuild(reader, iso, iso_entries, staging, archive, logicals,
                                                  origins, changes, progress=progress, experimental=experimental)
                replacements.update(patched)
                table_count += count
        if _digest(image.path, progress) != image.sha256:
            raise ValidationError("La imagen cambió durante la reconstrucción")
        reader.patch_copy(image.path, destination, replacements, progress=progress, expected_sha256=image.sha256)
    return BuildResult(destination, translated, skipped, table_count, experimental)
