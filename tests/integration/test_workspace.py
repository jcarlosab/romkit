import hashlib
import os

import pytest

from romkit_core.errors import SerializationError, WorkspaceError
from romkit_core.models import InputImage
from romkit_core.workspace import WorkspaceArea, WorkspaceManager

pytestmark = pytest.mark.integration


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "original.iso"
    path.write_bytes(b"controlled fixture")
    return InputImage(path, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest(), selected_platform="psp")


def test_lazy_layout_and_idempotent_reopen(tmp_path, image):
    manager = WorkspaceManager(tmp_path / "project")
    assert not manager.layout.root.exists()
    manager.open().open()
    assert list(manager.layout.root.iterdir()) == []
    metadata = manager.register_source(image)
    assert manager.register_source(image) == metadata
    reopened = WorkspaceManager(manager.layout.project_root).open()
    assert reopened.load_source_metadata() == metadata
    assert reopened.read_metadata("source.json")["platform"] == "psp"
    assert not manager.layout.area("source").exists()
    manager.layout.ensure().ensure()
    assert all(manager.layout.area(area).is_dir() for area in WorkspaceArea)


def test_explicit_copy_preserves_original(tmp_path, image):
    manager = WorkspaceManager(tmp_path / "project")
    original = image.path.read_bytes(), image.path.stat().st_mtime_ns
    manager.register_source(image)
    copied = manager.copy_source("game.iso")
    assert copied.read_bytes() == original[0]
    with pytest.raises(FileExistsError):
        manager.copy_source("game.iso")
    assert (image.path.read_bytes(), image.path.stat().st_mtime_ns) == original


@pytest.mark.parametrize("relative", ["../escape.json", "nested/../../escape.json", "F:/outside.json"])
def test_traversal_rejected(tmp_path, relative):
    with pytest.raises(WorkspaceError):
        WorkspaceManager(tmp_path).write_metadata(relative, {})


def test_original_cannot_be_registered_inside_technical_area(tmp_path):
    manager = WorkspaceManager(tmp_path)
    original = manager.layout.path("metadata", "source.json", create_parent=True)
    original.write_bytes(b"original")
    image = InputImage(original, 8, hashlib.sha256(b"original").hexdigest())
    with pytest.raises(WorkspaceError, match="outside .romkit"):
        manager.register_source(image)
    assert original.read_bytes() == b"original"


def test_hardlink_to_original_cannot_be_written(tmp_path, image):
    manager = WorkspaceManager(tmp_path / "project")
    manager.register_source(image)
    alias = manager.layout.path("metadata", "alias.json")
    os.link(image.path, alias)
    with pytest.raises(WorkspaceError, match="original"):
        manager.write_metadata("alias.json", {})
    assert image.path.read_bytes() == b"controlled fixture"


def test_workspace_cannot_switch_images(tmp_path, image):
    manager = WorkspaceManager(tmp_path / "project")
    manager.register_source(image)
    with pytest.raises(WorkspaceError, match="different source"):
        manager.register_source(InputImage(image.path, image.size_bytes, "00" * 32))


def test_source_metadata_cannot_be_overwritten_by_generic_writer(tmp_path, image):
    manager = WorkspaceManager(tmp_path / "project")
    metadata = manager.register_source(image)
    with pytest.raises(WorkspaceError, match="reserved"):
        manager.write_metadata("source.json", {})
    assert manager.load_source_metadata() == metadata


def test_copy_rejects_changed_source(tmp_path, image):
    manager = WorkspaceManager(tmp_path / "project")
    manager.register_source(image)
    image.path.write_bytes(b"changed")
    with pytest.raises(WorkspaceError, match="changed"):
        manager.copy_source("game.iso")
    assert not manager.layout.area("source").exists()


def test_metadata_write_is_atomic_and_errors_are_explicit(tmp_path):
    manager = WorkspaceManager(tmp_path)
    manager.write_metadata("chain.json", {"steps": ["identity"]})
    with pytest.raises(SerializationError):
        manager.write_metadata("chain.json", {"bad": object()})
    assert manager.read_metadata("chain.json") == {"steps": ["identity"]}
    assert len(list(manager.layout.area("metadata").iterdir())) == 1


def test_directory_symlink_cannot_escape(tmp_path):
    manager = WorkspaceManager(tmp_path / "project")
    outside = tmp_path / "outside"
    outside.mkdir()
    manager.layout.root.mkdir(parents=True)
    try:
        (manager.layout.root / "metadata").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating directory symlinks requires Windows developer mode")
    with pytest.raises(WorkspaceError, match="outside"):
        manager.write_metadata("escape.json", {})
    assert list(outside.iterdir()) == []
