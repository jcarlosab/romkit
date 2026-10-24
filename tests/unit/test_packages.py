import importlib
from importlib.metadata import version

import pytest

from romkit_core import __version__


@pytest.mark.unit
def test_installed_version():
    assert version("romkit") == __version__


@pytest.mark.unit
@pytest.mark.parametrize("package", ["romkit_core", "romkit_studio", "romkit_translator"])
def test_packages_import(package):
    assert importlib.import_module(package)
