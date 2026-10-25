"""Audit CCM glyph positions and draft unused-code candidates; never patch a ROM."""
import argparse
import hashlib
import json
from pathlib import Path

from romkit_core.adapters.pokapoka.fonts import read_ccm,candidate_codes
from romkit_core.adapters.pokapoka.reader import iter_archive_members
from romkit_core.analysis.containers import _children,Traversal
from romkit_core.analysis.gim import decode_gim
from romkit_core.project import read_jsonl
from romkit_core.workspace import WorkspaceManager


def audit(workspace,project,destination):
    workspace=WorkspaceManager(workspace);project=Path(project);destination=Path(destination)
    if destination.exists():raise ValueError('El informe ya existe; elige otro nombre')
    directory=workspace.layout.path('extracted','PSP_GAME/USRDIR')
    fonts={};atlases={};hashes={};extra_texts=[]
    for slot,name,raw,origin in iter_archive_members(directory,'PSP_GAME/USRDIR',on_error=lambda *a:None):
        if slot==5:
            for logical,data in _children(raw,origin['logical_path'],Traversal()):
                label=logical.rsplit('-',1)[-1];fonts[label]=read_ccm(data)
                hashes[label]=hashlib.sha256(data).hexdigest()
        if slot in (1,2,3):
            images=[]
            for logical,data in _children(raw,origin['logical_path'],Traversal()):
                decoded=decode_gim(data)
                if len(decoded)!=1:raise ValueError('Atlas con varias superficies sin correspondencia verificada')
                images.append({'source':logical,'width':decoded[0].width,'height':decoded[0].height,
                               'sha256':hashlib.sha256(data).hexdigest()})
            label={1:'MainFont.ccm',2:'TitleFont.ccm',3:'sjisfont.ccm'}[slot];atlases[label]=images
        if name.lower().endswith(('.csv','.txt')):
            try:extra_texts.append(raw.decode('cp932',errors='strict'))
            except UnicodeDecodeError:pass
    if set(fonts)!=set(atlases) or len(fonts)!=3:raise ValueError('Faltan fuentes o atlas de la variante esperada')
    units=read_jsonl(project/'text/main.jsonl')
    codes=candidate_codes(list(fonts.values()),[u.source for u in units]+extra_texts)
    # Avoid ASCII, punctuation and kana; numeric/user input must remain available.
    codes=[c for c in codes if c>=0x889f]
    slots=[]
    for code in codes:
        locations={}
        for label,glyphs in fonts.items():
            glyph=glyphs[code]
            if glyph.texture>=len(atlases[label]):raise ValueError('Índice de atlas sin imagen')
            atlas=atlases[label][glyph.texture]
            rect=glyph.rectangle(atlas['width'],atlas['height'])
            locations[label]={'texture':glyph.texture,'atlas':atlas['source'],'rectangle':rect,
                              'record_offset':glyph.record,'advance':glyph.advance}
        slots.append({'code_hex':f'{code:04x}','original_character':code.to_bytes(2,'big').decode('cp932'),'fonts':locations})
    report={'schema_version':1,'source_sha256':workspace.load_source_metadata().sha256,'active':False,
            'atlas_bindings_verified':False,
            'ccm_sha256':hashes,'fonts':{label:{'glyphs':len(fonts[label]),'atlases':atlases[label]} for label in fonts},
            'coverage':{'fmg_units':len(units),'additional_text_files':len(extra_texts)},
            'missing_validation':['Vinculación de cada CCM con los atlas usados en ejecución; el nombre de archivo no basta','Texto generado en ejecución y entradas del jugador','Asignación a Unicode y métricas de los glifos españoles','Reconstrucción de los atlas activos y de sus CCM','Codec de escritura y verificación en emulador'],
            'required_characters':'áéíóúüñÁÉÍÓÚÜÑ¿¡','candidates':slots}
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'fonts':{n:len(f) for n,f in fonts.items()},'candidate_slots':len(slots),'active':False},ensure_ascii=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for option in ('workspace','project','output'):parser.add_argument('--'+option,type=Path,required=True)
    options=parser.parse_args();audit(options.workspace,options.project,options.output)
