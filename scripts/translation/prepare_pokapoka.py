"""Create a clean, resumable Poka Poka editorial project from verified FMG tables."""
import argparse
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import re

from romkit_core.adapters.pokapoka.reader import scan_archive
from romkit_core.models import InputImage
from romkit_core.project import read_config, read_jsonl, write_jsonl
from romkit_core.project.generator import ProjectGenerator
from romkit_core.project.translation_memory import apply_memory
from romkit_core.workspace import WorkspaceManager


def prepare(source_project, original_workspace, output, memory_path, *, resume=False):
    output=Path(output).absolute()
    if output.exists() and not resume:
        raise ValueError('El destino ya existe: se conserva; usa otra carpeta o continúa editando ese proyecto')
    source_project=Path(source_project);original=WorkspaceManager(original_workspace)
    metadata=original.load_source_metadata()
    image=InputImage(metadata.path,metadata.size_bytes,metadata.sha256,selected_platform='psp')
    from romkit_core.project.rebuild import _digest
    if _digest(image.path)!=image.sha256:
        raise ValueError('Hash de la ROM original incorrecto')
    candidates,origins=scan_archive(original.layout.path('extracted','PSP_GAME/USRDIR'),'PSP_GAME/USRDIR')
    old={u.id:u for u in read_jsonl(source_project/'text/main.jsonl')}
    workspace=WorkspaceManager(output)
    if resume and output.exists():
        if read_config(output/'project.toml').source_sha256!=image.sha256:
            raise ValueError('El proyecto de continuación corresponde a otra ROM')
        old={u.id:u for u in read_jsonl(output/'text/main.jsonl')}
    workspace.write_metadata('archive_resources.json',{'resources':origins})
    project=ProjectGenerator().generate(output,image,'psp',candidates,source_language='en',target_language='es-ES',workspace=workspace)
    units=[]
    for unit,candidate in zip(project.units,sorted(candidates,key=lambda c:(c.logical_path,c.offset,c.encoding))):
        previous=old.get(unit.id)
        if previous is not None and previous.source==unit.source:
            unit=replace(previous,encoding=candidate.encoding,constraints=unit.constraints)
        units.append(replace(unit,context=candidate.logical_path))
    memory=json.loads(Path(memory_path).read_text(encoding='utf-8'))
    dictionary=memory['translations']
    # Case variants are explicit label variants, never word replacement in dialogue.
    dictionary={**dictionary,**{k.upper():v.upper() for k,v in dictionary.items()}}
    # Full-width menu lettering is preserved in source and normalized only for lookup.
    import unicodedata
    for u in units:
        normalized=unicodedata.normalize('NFKC',u.source)
        if normalized in dictionary and not re.search('[\u2460-\u2473]',u.source):
            dictionary[u.source]=dictionary[normalized]
        if u.context.endswith('/KeyGuide.fmg') and re.search('[\u2460-\u2473]',u.source):
            pieces=re.split(r'([\u2460-\u2473])',u.source)
            translated=[]
            for piece in pieces:
                label=piece.strip()
                if not label or re.fullmatch(r'[\u2460-\u2473]|OK|[\d+\-/~!?.\s]+',label):
                    translated.append(piece)
                elif label in dictionary:
                    translated.append(piece.replace(label,dictionary[label],1))
                else:
                    break
            else:
                dictionary[u.source]=''.join(translated)
    translated,applied,blocked=apply_memory(units,dictionary)
    write_jsonl(output/'text/main.jsonl',translated)
    indexed={u.id for u in units}
    excluded=[u.to_dict() for id,u in old.items() if id not in indexed]
    report={'source_units':len(old),'indexed_units':len(units),'excluded_unverified':len(excluded),
            'unique_indexed':len({u.source for u in units}),'translated_now':applied,
            'blocked_proposals':len(blocked),'statuses':dict(Counter(u.status.value for u in translated)),
            'source_sha256':image.sha256,'source_language_note':'Principalmente inglés, con controles y algunos textos japoneses; no enviar todo como japonés.',
            'complete_translation':False,'emulator_tested':False}
    (output/'preparation-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'blocked-proposals.json').write_text(json.dumps(blocked,ensure_ascii=False,indent=2),encoding='utf-8')
    if not resume:
        (output/'excluded-unverified.jsonl').write_text(''.join(json.dumps(u,ensure_ascii=False)+'\n' for u in excluded),encoding='utf-8')
    (output/'README.md').write_text('# Poka Poka: proyecto editorial español\n\nAbre esta carpeta en Translator. Se conservan IDs y originales de las tablas FMG verificadas.\nLas entradas descartadas del catálogo anterior quedan en excluded-unverified.jsonl, sin borrar el catálogo original.\n\nLas traducciones son propuestas editoriales pendientes de revisión. Las que no caben o no son CP932 permanecen en estado Pendiente y no se reinsertan. No se han eliminado tildes ni truncado frases.\nConsulta preparation-report.json y blocked-proposals.json. Esto no es una traducción completa ni probada en emulador.\n\nPara reinsertar el lote compatible usa este proyecto y su propia carpeta de trabajo (esta misma carpeta); conserva la ROM original. Su .romkit contiene la metadata de los textos, sin copiar la extracción.\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for option in ('source-project','workspace','output','memory'):parser.add_argument('--'+option,type=Path,required=True)
    parser.add_argument('--resume',action='store_true')
    options=parser.parse_args()
    prepare(options.source_project,options.workspace,options.output,options.memory,resume=options.resume)
