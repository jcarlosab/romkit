"""Optional, offline OPUS-MT draft generation. Never downloads or loads remote code.

Install the inspected runtime separately and provide an already converted Marian
model plus SentencePiece files. ROMKit's application dependencies stay unchanged.
"""
import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import time
import unicodedata

from romkit_core.project import read_jsonl,write_jsonl
from romkit_core.project.translation_memory import CONTROLS

TERMS={name:name for name in ('Felyne','Felynes','Melynx','Poogie','Poogies','Popo','Kopopo','Velociprey',
    'Velocidrome','Bullfango','Bulldrome','Rathalos','Rathian','Tigrex','Gargwa','Gargwas','Nekoht','Nekoto',
    'Trenya','Yukumo','MHP2G','MHP3rd','PP','NP','SP')}
TERMS.update({'Airu':'Felyne','Airou':'Felyne','Palico':'camarada','Palicos':'camaradas','Palicoes':'camaradas'})
TERM_RE=r'(?<!\w)(?:'+'|'.join(re.escape(t) for t in sorted(TERMS,key=len,reverse=True))+r')(?!\w)'
SPLIT=re.compile('('+CONTROLS.pattern+'|\n+|'+TERM_RE+')')
PRESERVE_TABLES={'Forbidword.fmg':'Filtro de nombres: se conserva su comportamiento, no es diálogo.',
                 'Airou_Name.fmg':'Nombre propio conservado; los cargos se traducen mediante memoria editorial.',
                 'Monster_Name.fmg':'Nombre de monstruo conservado.',
                 'QuestRequestName.fmg':'Identificador o nombre propio conservado.',
                 'StaffRoll.fmg':'Créditos y nombres de autores conservados; encabezados por memoria editorial.'}


def preserve_reason(unit):
    table=Path(unit.context).name
    if table in PRESERVE_TABLES:return PRESERVE_TABLES[table]
    plain=unicodedata.normalize('NFKC',CONTROLS.sub('',unit.source))
    if not re.search('[A-Za-z]',plain):return 'Solo símbolos, cifras o controles; no requiere traducción automática.'
    if re.fullmatch(r'[■□\s]+Message[■□\s]+',plain):return 'Separador técnico de la tabla.'
    if re.fullmatch(r'[\w./\\:-]+\.(?:bin|fmg|bnd|gim|prx|param|csv)',plain,re.I):return 'Ruta o nombre técnico de recurso.'
    if plain.strip().casefold() in {'test','dummy','unused npc menu'}:return 'Etiqueta técnica o de depuración.'
    if re.search('[\u3040-\u30ff\u4e00-\u9fff]',plain):return 'Texto japonés fuera de controles: requiere traducción específica, no modelo inglés.'
    return None


def parts(text):
    result=[]
    for piece in SPLIT.split(text):
        if not piece:continue
        if CONTROLS.fullmatch(piece) or piece.startswith('\n'):
            result.append((False,piece));continue
        if piece in TERMS:
            result.append((False,TERMS[piece]));continue
        # Retain whitespace and split long passages without discarding any words.
        for block in re.findall(r'\s+|\S+(?:[^\S\n]+\S+){0,47}',piece):
            if block.isspace():result.append((False,block));continue
            match=re.fullmatch(r'(\s*)(.*?)(\s*)',block,re.S)
            before,body,after=match.groups()
            if before:result.append((False,before))
            result.append((bool(re.search('[A-Za-z]',unicodedata.normalize('NFKC',body))),body))
            if after:result.append((False,after))
    return result


def glossary(source,target):
    # Apply only domain terms actually present in the English source segment.
    substitutions=[]
    # Do not replace pueblo/aldea or hongo/seta mechanically: their genders differ
    # and changing only the noun breaks articles and adjective agreement.
    if re.search(r'\bitems?\b',source,re.I):substitutions += [('artículos','objetos'),('artículo','objeto')]
    for before,after in substitutions:
        target=re.sub(r'\b'+before+r'\b',lambda m:after.capitalize() if m[0][0].isupper() else after,target,flags=re.I)
    if re.search(r'\bsave\b',source,re.I) and re.search(r'\b(game|progress)\b',source,re.I):
        target=re.sub(r'\bsalvar (?:tu|el|su) juego\b','guardar la partida',target,flags=re.I)
    if source.isupper():target=target.upper()
    return target


def checked_write(path,original,units):
    if path.is_symlink() or path.read_bytes()!=original:
        raise ValueError('El catálogo cambió durante la traducción. Se conservan los cambios externos y la caché; vuelve a ejecutar sobre la versión actual.')
    write_jsonl(path,units)


def run(project,runtime,model,source_spm,target_spm,memory=None):
    project=Path(project).resolve(strict=True)
    sys.path.insert(0,str(Path(runtime).resolve(strict=True)))
    import ctranslate2
    import sentencepiece
    model=Path(model).resolve(strict=True)
    source_spm=Path(source_spm).resolve(strict=True);target_spm=Path(target_spm).resolve(strict=True)
    model_hash=hashlib.file_digest((model/'model.bin').open('rb'),'sha256').hexdigest()
    signature='marian-int8-beam2-parts-v1:'+model_hash
    cache=sqlite3.connect(project/'offline-cache.sqlite')
    cache.execute('CREATE TABLE IF NOT EXISTS translations (engine TEXT, source TEXT, target TEXT, PRIMARY KEY(engine,source))')
    known={s:t for s,t in cache.execute('SELECT source,target FROM translations WHERE engine=?',(signature,))}
    if memory:
        # Explicit editorial translations always take priority over machine output.
        known.update(json.loads(Path(memory).read_text(encoding='utf-8'))['translations'])
    text_path=project/'text/main.jsonl';original_bytes=text_path.read_bytes()
    units=read_jsonl(text_path);originals=[u.source for u in units]
    if text_path.read_bytes()!=original_bytes:raise ValueError('El catálogo cambió mientras se leía')
    plans={};preserved=[];needed=set()
    for i,unit in enumerate(units):
        if unit.target or unit.status.value!='untranslated':continue
        reason=preserve_reason(unit)
        if reason:
            preserved.append({'id':unit.id,'reason':reason});continue
        plan=parts(unit.source);plans[i]=plan
        needed.update(text for translate,text in plan if translate and text not in known)
    print(json.dumps({'pending_units':len(plans),'preserved_units':len(preserved),'new_segments':len(needed),'cached_segments':len(known)}),flush=True)
    processor=sentencepiece.SentencePieceProcessor(model_file=str(source_spm))
    decoder=sentencepiece.SentencePieceProcessor(model_file=str(target_spm))
    translator=ctranslate2.Translator(str(model),device='cpu',compute_type='int8',intra_threads=8,inter_threads=1)
    segments=sorted(needed,key=lambda s:(len(s),s));failures={};start=time.monotonic()
    for offset in range(0,len(segments),64):
        batch=segments[offset:offset+64]
        inputs=[processor.encode(s,out_type=str) for s in batch]
        if any(len(tokens)>384 for tokens in inputs):
            raise ValueError('Segmento demasiado largo: dividirlo sin truncar antes de traducir')
        results=translator.translate_batch(inputs,beam_size=2,max_decoding_length=512,
            repetition_penalty=1.05,no_repeat_ngram_size=4)
        for text,result in zip(batch,results):
            tokens=result.hypotheses[0]
            translated=glossary(text,decoder.decode(tokens))
            if not translated.strip() or len(tokens)>=511:
                failures[text]='Salida vacía o límite de generación; no se ha truncado el texto.';continue
            known[text]=translated
            cache.execute('INSERT OR REPLACE INTO translations VALUES (?,?,?)',(signature,text,translated))
        cache.commit()
        if offset%512==0 or offset+64>=len(segments):
            print(json.dumps({'segments_done':min(offset+64,len(segments)),'segments_total':len(segments),'seconds':round(time.monotonic()-start,1),'failures':len(failures)}),flush=True)
    generated=0;unchanged=0;blocked=[]
    for i,plan in plans.items():
        missing=[text for translate,text in plan if translate and text not in known]
        if missing:
            blocked.append({'id':units[i].id,'reason':'Segmentos sin traducción íntegra','segments':missing});continue
        target=''.join(known[text] if translate else text for translate,text in plan)
        if Counter(CONTROLS.findall(target))!=Counter(CONTROLS.findall(units[i].source)):
            blocked.append({'id':units[i].id,'reason':'Controles alterados por la generación; se conserva pendiente'});continue
        if target==units[i].source:unchanged+=1
        units[i]=replace(units[i],target=target,status='translated',notes=(units[i].notes+'\nBorrador automático local OPUS-MT inglés-español. NO REVISADO. Reinserción pendiente de codec, fuentes, espacio y prueba en juego.').strip())
        generated+=1
    assert originals==[u.source for u in units]
    checked_write(text_path,original_bytes,units)
    report={'engine':'Helsinki-NLP OPUS-MT eng-spa opus-2021-02-19, CTranslate2 int8',
        'engine_license':'CC BY 4.0 (archivo LICENSE de los pesos originales)',
        'model_sha256':model_hash,'source_spm_sha256':hashlib.sha256(source_spm.read_bytes()).hexdigest(),
        'target_spm_sha256':hashlib.sha256(target_spm.read_bytes()).hexdigest(),
        'network_text_requests':0,'new_draft_units':generated,'unchanged_model_outputs':unchanged,
        'preserved_units':preserved,'blocked_units':blocked,'failed_segments':failures,
        'statuses':dict(Counter(u.status.value for u in units)),
        'automatic_draft_units_total':sum('Borrador automático local OPUS-MT' in u.notes for u in units),
        'targets_present_total':sum(bool(u.target) for u in units),
        'reviewed_automatically':0,'complete_game_translation':False,'insertion_ready':False,'emulator_tested':False}
    (project/'offline-draft-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    cache.close()
    print(json.dumps({k:v for k,v in report.items() if k not in ('preserved_units','blocked_units','failed_segments')},ensure_ascii=True),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('project','runtime','model','source-spm','target-spm'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--memory',type=Path)
    args=parser.parse_args();run(args.project,args.runtime,args.model,args.source_spm,args.target_spm,args.memory)
