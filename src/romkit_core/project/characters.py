"""Inspect and replace target characters, preserving controls and originals."""
from collections import Counter,defaultdict
from dataclasses import dataclass,replace
import re

from romkit_core.errors import ValidationError
from romkit_core.tasks import report
from romkit_core.validation import validate_translation
from .translation_memory import CONTROLS


def spans(unit):
    ranges=[m.span() for m in CONTROLS.finditer(unit.target)]
    for token in unit.tokens:
        if token:ranges.extend(m.span() for m in re.finditer(re.escape(token),unit.target))
    merged=[]
    for start,end in sorted(ranges):
        if merged and start<=merged[-1][1]:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else:merged.append((start,end))
    cursor=0
    for start,end in merged:
        yield False,unit.target[cursor:start]
        yield True,unit.target[start:end]
        cursor=end
    yield False,unit.target[cursor:]


@dataclass(frozen=True)
class CharacterInfo:
    character: str
    occurrences: int
    entries: int
    encodings: tuple
    unsupported: tuple


def inspect_characters(units, *, progress=None):
    counts=Counter();entries=Counter();codecs=defaultdict(set)
    for i,unit in enumerate(units):
        if i%256==0:report(progress,i,len(units),'Buscando caracteres en las traducciones')
        found=Counter(c for protected,text in spans(unit) if not protected for c in text if ord(c)>127)
        counts.update(found);entries.update(found.keys())
        for c in found:codecs[c].add(unit.encoding)
    result=[]
    for c in sorted(counts,key=ord):
        unsupported=[]
        for codec in codecs[c]-{None}:
            try:c.encode(codec)
            except (UnicodeEncodeError,LookupError):unsupported.append(codec)
        result.append(CharacterInfo(c,counts[c],entries[c],tuple(sorted(codecs[c]-{None})),tuple(sorted(unsupported))))
    report(progress,len(units),len(units),'Caracteres encontrados')
    return tuple(result)


@dataclass(frozen=True)
class CharacterChange:
    row: int
    before: object
    after: object


@dataclass(frozen=True)
class CharacterPlan:
    mapping: tuple
    changes: tuple
    occurrences: int
    invalid_entries: int


def plan_substitutions(units,mapping, *, progress=None):
    if any(not isinstance(c,str) or len(c)!=1 or not isinstance(target,str) for c,target in mapping.items()):
        raise ValidationError('Cada origen debe ser un único carácter y su sustitución debe ser texto')
    mapping={c:target for c,target in mapping.items() if c!=target}
    if any('\0' in target for target in mapping.values()):raise ValidationError('No se admiten bytes cero en las sustituciones')
    table=str.maketrans(mapping);changes=[];occurrences=0;invalid=0;size=0
    for i,unit in enumerate(units):
        if i%256==0:report(progress,i,len(units),'Previsualizando sustituciones')
        pieces=[];hits=0
        for protected,text in spans(unit):
            pieces.append(text if protected else text.translate(table))
            if not protected:hits+=sum(n for c,n in Counter(text).items() if c in mapping)
        target=''.join(pieces)
        if target==unit.target:continue
        if (Counter(CONTROLS.findall(target))!=Counter(CONTROLS.findall(unit.target))
                or any(target.count(token)!=unit.target.count(token) for token in unit.tokens if token)):
            raise ValidationError(f'{unit.id}: la sustitución crearía o alteraría controles protegidos')
        size+=len(target)
        if size>64*1024*1024:raise ValidationError('El resultado supera 64 millones de caracteres; divide las sustituciones en lotes')
        after=replace(unit,target=target,status='translated' if target else 'untranslated')
        changes.append(CharacterChange(i,unit,after));occurrences+=hits
        invalid+=not validate_translation(after).valid
    report(progress,len(units),len(units),'Previsualización lista')
    return CharacterPlan(tuple(sorted(mapping.items())),tuple(changes),occurrences,invalid)
