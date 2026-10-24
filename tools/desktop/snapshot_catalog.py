"""Copy an explicitly selected editorial project for publication, without its ROM/workspace."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil

from romkit_core.project import read_config, read_jsonl


def snapshot(source, destination, game, adapter):
    source, destination = Path(source).resolve(strict=True), Path(destination).resolve()
    if destination.exists():
        raise ValueError('El catálogo ya existe; elige una carpeta nueva')
    config = read_config(source / 'project.toml')
    files, statuses, count = {}, Counter(), 0
    for path in sorted((source / 'text').glob('*.jsonl')):
        if path.is_symlink():
            raise ValueError('No se admiten enlaces en el proyecto')
        units = read_jsonl(path)
        count += len(units)
        statuses.update(u.status.value for u in units)
        files['text/' + path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not count:
        raise ValueError('El proyecto no contiene textos')
    destination.mkdir(parents=True)
    (destination / 'text').mkdir()
    shutil.copyfile(source / 'project.toml', destination / 'project.toml')
    for relative in files:
        shutil.copyfile(source / relative, destination / relative)
    files['project.toml'] = hashlib.sha256((destination / 'project.toml').read_bytes()).hexdigest()
    manifest = {'schema_version': 1, 'game': game, 'adapter': adapter, 'units': count,
                'statuses': dict(statuses), 'source_sha256': config.source_sha256,
                'source_language': config.source_language, 'target_language': config.target_language,
                'snapshot_date': '2026-10-24', 'files_sha256': files}
    (destination / 'snapshot.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (destination / 'README.md').write_text(f'''# {game}: catálogo actual

Snapshot del proyecto editorial del 24 de octubre de 2026, publicado por petición
del propietario del proyecto. Contiene {count:,} unidades; conserva exactamente los
originales, traducciones, estados y notas de los JSONL actuales. No es un fixture
sintético ni forma parte de los ejecutables. El texto procede del juego/parche y
no se presenta como código original de ROMKit ni se cambia su licencia por incluirlo aquí.

Abre esta carpeta con **ROMKit Translator**. `snapshot.json` registra recuentos,
estados y hashes para comprobar el snapshot. Los idiomas de `project.toml` se han
conservado del proyecto local; revísalos antes de pedir sugerencias online si
partes de un parche inglés y el proyecto sigue configurado como japonés.

ROM base SHA-256: `{config.source_sha256}`. Adaptador: `{adapter}`.
No se incluye ROM, extracción, imágenes, rutas personales ni `.romkit`.
Para reinsertar, necesitas esa misma ROM y el workspace con el mapa de exportación
correspondiente a los IDs de este proyecto. Conserva tu propio workspace original.
''',encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('destination',type=Path)
    parser.add_argument('--game',required=True)
    parser.add_argument('--adapter',required=True)
    options = parser.parse_args()
    result = snapshot(options.source,options.destination,options.game,options.adapter)
    print(json.dumps({'game':result['game'],'units':result['units'],'statuses':result['statuses']},ensure_ascii=False))
