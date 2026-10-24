import importlib.util
import os
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('desktop_build', Path(__file__).parents[2] / 'scripts/desktop/build.py')
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)


@pytest.mark.skipif(os.name != 'nt', reason='Windows DLL search environment')
def test_build_excludes_unrelated_dll_paths(monkeypatch):
    monkeypatch.setenv('PATH', r'C:\unrelated\poppler\bin;C:\another\Qt\bin')
    monkeypatch.setenv('QT_PLUGIN_PATH', r'C:\another\Qt\plugins')
    monkeypatch.setenv('PYTHONPATH', r'C:\another\python')
    result = desktop.build_environment()
    assert 'poppler' not in result['PATH'] and 'another' not in result['PATH']
    assert 'QT_PLUGIN_PATH' not in result and 'PYTHONPATH' not in result
    assert result['PATH'].split(os.pathsep)[0].lower().endswith('system32')


def test_exit_zero_without_qt_marker_is_not_success(monkeypatch, tmp_path):
    from subprocess import CompletedProcess
    monkeypatch.setattr(desktop, 'ROOT', tmp_path)
    monkeypatch.setattr(desktop.subprocess, 'run', lambda *args, **kwargs: CompletedProcess(args, 0))
    with pytest.raises(RuntimeError, match='no se confirmó'):
        desktop.smoke_test(tmp_path / 'fake.exe', {})
