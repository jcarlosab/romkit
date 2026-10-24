"""Build Windows desktop apps with their own executable icons."""
from pathlib import Path
import subprocess
import sys
import argparse
import os
import json
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def release_version():
    import ast
    module = ast.parse((ROOT / 'src/romkit_core/__init__.py').read_text(encoding='utf-8'))
    return next(ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == '__version__' for t in node.targets))


def version_resource(path, title, version):
    numbers = tuple(int(part) for part in version.split('.')) + (0,)
    entries = {'CompanyName': 'ROMKit', 'FileDescription': title, 'FileVersion': version,
               'ProductName': title, 'ProductVersion': version, 'OriginalFilename': title + '.exe'}
    strings = ','.join(f'StringStruct({key!r},{value!r})' for key,value in entries.items())
    path.write_text(f'VSVersionInfo(ffi=FixedFileInfo(filevers={numbers!r},prodvers={numbers!r},'
        f'mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),'
        f'kids=[StringFileInfo([StringTable("040904B0",[{strings}])]),VarFileInfo([VarStruct("Translation",[1033,1200])])])',encoding='utf-8')


def build_environment():
    env = dict(os.environ)
    for key in ('PYTHONPATH', 'PYTHONHOME', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH',
                'QML2_IMPORT_PATH', 'QML_IMPORT_PATH', 'QT_QPA_PLATFORM'):
        env.pop(key, None)
    if os.name == 'nt':
        windows = Path(env.get('SystemRoot', 'C:/Windows'))
        env['PATH'] = os.pathsep.join(str(p) for p in (
            windows / 'System32', windows, Path(sys.executable).parent, Path(sys.base_prefix),
            Path(sys.base_prefix) / 'DLLs'))
    return env


def smoke_test(executable, env):
    reports = ROOT / 'build/desktop-smoke'
    reports.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=reports) as temporary:
        marker = Path(temporary) / 'ready.json'
        result = subprocess.run([str(executable), '--smoke-test', str(marker)], env=env,
            cwd=temporary, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        if result.returncode or not marker.exists():
            raise RuntimeError(f'{executable.name}: no se confirmó la creación de la ventana Qt')
        report = json.loads(marker.read_text(encoding='utf-8'))
        if not report.get('ready') or not report.get('frozen') or (os.name == 'nt' and report.get('platform') != 'windows'):
            raise RuntimeError(f'{executable.name}: informe de arranque incompleto: {report}')
        (reports / (executable.stem + '.json')).write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f'ARRANQUE VERIFICADO: {executable.name} · Qt {report["qt"]} · {report["platform"]}', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', choices=('all', 'base', 'digimon', 'pokapoka'), default='all')
    parser.add_argument('--app', choices=('both', 'studio', 'translator'), default='both')
    parser.add_argument('--dist-dir', type=Path, default=Path('dist'))
    parser.add_argument('--onefile', action='store_true', help='Generar un EXE autónomo')
    options = parser.parse_args()
    version = release_version()
    dist_dir = (ROOT / options.dist_dir).resolve()
    if not dist_dir.is_relative_to(ROOT):
        raise ValueError('El directorio de compilación debe permanecer dentro del repositorio')
    for name, title in (("studio", "ROMKit Studio"), ("translator", "ROMKit Translator")):
        if options.app not in ('both', name):
            continue
        title += '' if options.profile == 'all' or name == 'translator' else ' - ' + options.profile.title()
        generated = ROOT / 'build/desktop-launchers'
        generated.mkdir(parents=True, exist_ok=True)
        launcher = generated / (name + '-' + options.profile + '.py')
        version_file = generated / (name + '-' + options.profile + '-version.txt')
        version_resource(version_file, title, version)
        launcher.write_text('import os\nos.environ["ROMKIT_PROFILE"] = ' + repr(options.profile) + '\n'
            + (ROOT / f'scripts/desktop/{name}.py').read_text(encoding='utf-8'), encoding='utf-8')
        modules = []
        icon_name = options.profile if name == 'studio' and options.profile in ('digimon', 'pokapoka') else name
        env = build_environment()
        env['PYINSTALLER_CONFIG_DIR'] = str(ROOT / 'build/pyinstaller-cache' / (name + '-' + options.profile))
        for adapter in ('digimon', 'pokapoka'):
            if options.profile in ('all', adapter) and name == 'studio':
                for module in (ROOT / f'src/romkit_core/adapters/{adapter}').glob('*.py'):
                    if module.stem != '__init__':
                        modules += ['--hidden-import', f'romkit_core.adapters.{adapter}.{module.stem}']
            else:
                modules += ['--exclude-module', f'romkit_core.adapters.{adapter}']
        subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--windowed", "--onefile" if options.onefile else "--onedir",
            "--name", title, "--icon", str(ROOT / f"src/romkit_core/assets/{icon_name}.ico"),
            '--version-file', str(version_file),
            '--add-data', str(ROOT / 'LICENSE') + os.pathsep + '.',
            "--paths", str(ROOT / "src"), "--collect-data", "romkit_core", *modules,
            "--specpath", str(ROOT / "build/desktop-specs"),
            "--workpath", str(ROOT / "build/desktop"), "--distpath", str(dist_dir),
            str(launcher)], cwd=ROOT, check=True, env=env)
        output = dist_dir if options.onefile else dist_dir / title
        smoke_test(output / (title + '.exe'), env)
        (output / (title + '.release.json' if options.onefile else 'release.json')).write_text(json.dumps({'version': version,
            'profile': options.profile if name == 'studio' else 'shared', 'app': name},indent=2),encoding='utf-8')


if __name__ == "__main__":
    main()
