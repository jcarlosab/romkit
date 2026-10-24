"""Package complete, smoke-tested Windows folders as versioned release ZIPs."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
from build import ROOT, release_version

APPS = [('ROMKit Studio - Digimon','ROMKit-Studio-Digimon'),
        ('ROMKit Studio - Pokapoka','ROMKit-Studio-Pokapoka'),
        ('ROMKit Studio - Base','ROMKit-Studio-Base'),
        ('ROMKit Studio','ROMKit-Studio-Completo'),
        ('ROMKit Translator','ROMKit-Translator')]


def package(source, destination):
    version = release_version()
    destination.mkdir(parents=True,exist_ok=True)
    checksums = []
    for folder,stem in APPS:
        root = source / folder
        metadata = json.loads((root / 'release.json').read_text(encoding='utf-8'))
        if metadata['version'] != version or not (root / (folder+'.exe')).is_file():
            raise ValueError(f'Compilación incorrecta: {folder}')
        report = json.loads((ROOT/'build/desktop-smoke'/(folder+'.json')).read_text(encoding='utf-8'))
        if report.get('version') != version or not report.get('ready') or report.get('platform') != 'windows':
            raise ValueError(f'Falta prueba de arranque de {folder} {version}')
        output = destination / f'{stem}-{version}-windows-x64.zip'
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for file in sorted(root.rglob('*')):
                if file.is_file():
                    archive.write(file,Path(folder)/file.relative_to(root))
            archive.write(ROOT/'LICENSE',folder+'/LICENSE')
            archive.writestr(folder+'/LEEME.txt',f'{folder} {version}\n\nExtrae la carpeta completa y ejecuta {folder}.exe.\nConserva _internal junto al ejecutable. No necesitas Python.\nDocumentación: https://github.com/jcarlosab/romkit\n')
        with zipfile.ZipFile(output) as archive:
            if archive.testzip() is not None:
                raise ValueError(f'ZIP dañado: {output.name}')
        digest = hashlib.file_digest(output.open('rb'),'sha256').hexdigest()
        checksums.append(f'{digest}  {output.name}')
        print(f'{output.name}: {output.stat().st_size:,} bytes',flush=True)
    (destination/'SHA256SUMS.txt').write_text('\n'.join(checksums)+'\n',encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args = parser.parse_args()
    package((ROOT/args.input_dir).resolve(),(ROOT/args.output_dir).resolve())
