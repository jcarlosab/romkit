from dataclasses import dataclass, replace
from pathlib import Path

from romkit_core.errors import ValidationError
from romkit_core.models import InputImage, ProjectConfig, TextConstraints, TranslationUnit
from romkit_core.models.text_candidate import TextCandidate
from romkit_core.tasks import ProgressCallback, report
from romkit_core.workspace import WorkspaceManager
from .config import read_config, write_config
from .jsonl import read_jsonl, write_jsonl
from .reinsert_map import ReinsertEntry
from .schema import stable_unit_id


@dataclass(frozen=True)
class GeneratedProject:
    root: Path
    units: tuple[TranslationUnit, ...]


class ProjectGenerator:
    def generate(self, destination: str | Path, image: InputImage, platform: str, candidates: list[TextCandidate], *,
                 source_language: str = "ja", target_language: str = "es-ES", workspace: WorkspaceManager | None = None,
                 progress: ProgressCallback | None = None) -> GeneratedProject:
        destination = Path(destination).resolve()
        config = ProjectConfig(platform, image.sha256, source_language, target_language)
        if not candidates:
            raise ValidationError("Selecciona al menos un candidato de texto confirmado")
        ordered = sorted(candidates, key=lambda c: (c.logical_path, c.offset, c.encoding))
        units, metadata, previous_end = [], [], {}
        for candidate in ordered:
            if candidate.offset < previous_end.get(candidate.logical_path, 0):
                raise ValidationError(f"Candidatos solapados: {candidate.logical_path}; selecciona una sola codificación")
            previous_end[candidate.logical_path] = candidate.offset + candidate.length_bytes + len(candidate.terminator)
            id = stable_unit_id(candidate.logical_path, candidate.offset, candidate.encoding)
            unit = TranslationUnit(id, candidate.text, encoding=candidate.encoding,
                                   constraints=TextConstraints(max_bytes=candidate.length_bytes))
            units.append(unit)
            metadata.append(ReinsertEntry(id, candidate).to_dict())
        # Repeating generation preserves editorial changes instead of resetting them.
        config_path, text_path = destination / "project.toml", destination / "text/main.jsonl"
        if config_path.exists() and read_config(config_path) != config:
            raise ValidationError("El destino ya contiene un proyecto con otra configuración")
        if text_path.exists():
            old = {unit.id: unit for unit in read_jsonl(text_path)}
            if set(old) != {unit.id for unit in units} or any(old[unit.id].source != unit.source for unit in units):
                raise ValidationError("El destino ya contiene textos diferentes; elige otra carpeta")
            units = [old[unit.id] for unit in units]
        workspace = workspace if workspace is not None else WorkspaceManager(destination)
        workspace.register_source(replace(image, selected_platform=platform))
        for path in (config_path, text_path):
            if not path.resolve().is_relative_to(destination) or path.is_symlink():
                raise ValidationError("Un archivo del proyecto sale de la carpeta destino")
            if path.resolve() == image.path.resolve() or (path.exists() and WorkspaceManager._same_file(path, image.path)):
                raise ValidationError("El proyecto no puede sobrescribir la imagen original")
        report(progress, 0, 3, "Guardando proyecto")
        write_config(config_path, config)
        report(progress, 1, 3, "Guardando textos")
        write_jsonl(text_path, units)
        report(progress, 2, 3, "Guardando metadata de reinserción")
        reinsert = {"schema_version": 1, "source_sha256": image.sha256, "entries": metadata}
        archive_metadata = workspace.layout.path("metadata", "archive_resources.json")
        if archive_metadata.exists():
            selected_paths = {candidate.logical_path for candidate in ordered}
            reinsert["archive_resources"] = [entry for entry in workspace.read_metadata("archive_resources.json")["resources"]
                                              if entry["logical_path"] in selected_paths]
        workspace.write_metadata("reinsert.json", reinsert)
        report(progress, 3, 3, "Proyecto creado")
        return GeneratedProject(destination, tuple(units))
