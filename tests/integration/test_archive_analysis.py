import hashlib

from romkit_core.analysis.inventory import inventory
from romkit_core.models import InputImage
from romkit_core.project.generator import ProjectGenerator
from romkit_core.workspace import WorkspaceManager
from romkit_studio.services.controller import StudioController
from pokapoka_builder import make_archive, make_fmg


def test_studio_analysis_and_project_preserve_archive_origin(tmp_path):
    workspace = WorkspaceManager(tmp_path / "workspace")
    directory = workspace.layout.path("extracted", "PSP_GAME/USRDIR", create_parent=True)
    make_archive(directory, make_fmg(["Hi", "English dialogue"]))
    resources = inventory(workspace.layout.area("extracted"))
    analyzed, candidates = StudioController._analyze(None, resources, workspace, progress=lambda value: None)
    assert len(analyzed) == 3
    assert [c.text for c in candidates] == ["Hi", "English dialogue"]
    assert len(workspace.read_metadata("archive_resources.json")["resources"]) == 1
    image_path = tmp_path / "synthetic.iso"
    image_path.write_bytes(b"synthetic")
    image = InputImage(image_path, 9, hashlib.sha256(b"synthetic").hexdigest(), selected_platform="psp")
    project = ProjectGenerator().generate(tmp_path / "project", image, "psp", candidates,
                                          source_language="en", workspace=workspace)
    assert project.units[0].source == "Hi"
    assert workspace.read_metadata("reinsert.json")["archive_resources"][0]["slot"] == 0


def test_known_tables_take_precedence_over_raw_guesses(tmp_path):
    workspace = WorkspaceManager(tmp_path / "workspace")
    directory = workspace.layout.path("extracted", "PSP_GAME/USRDIR", create_parent=True)
    make_archive(directory, make_fmg(["Hi", "English dialogue"]))
    (directory / "NOISE.BIN").write_bytes(b"Unverified English guess\0")
    (directory / "HELP.TXT").write_bytes(b"Real help text\0")
    analyzed, candidates = StudioController._analyze(None, inventory(workspace.layout.area("extracted")), workspace,
                                                    progress=lambda value: None)
    assert {candidate.text for candidate in candidates} == {"Hi", "English dialogue", "Real help text"}
    assert workspace.read_metadata("text_detection.json")["mode"] == "indexed_tables_and_text_files"
