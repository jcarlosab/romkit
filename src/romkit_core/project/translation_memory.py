"""Apply explicit, local editorial translations without guessing or online requests."""
from collections import Counter
from dataclasses import replace
import re

from romkit_core.models import TranslationStatus
from romkit_core.validation import validate_translation

CONTROLS = re.compile(r'\{[^{}]+\}|<[^<>]+>|%[^%\s]+%|[\x00-\x08\x0b\x0c\x0e-\x1f\u2460-\u2473]')


def apply_memory(units, memory):
    """Keep existing edits; proposals failing codec, space or controls stay pending."""
    result=[];applied=0;blocked=[]
    for unit in units:
        target=memory.get(unit.source)
        if target is None or unit.target or unit.status!=TranslationStatus.UNTRANSLATED:
            result.append(unit);continue
        proposal=replace(unit,target=target,status=TranslationStatus.TRANSLATED,
                         notes=(unit.notes+'\nPropuesta editorial de IA; pendiente de revisión en contexto.').strip())
        errors=[issue.message for issue in validate_translation(proposal).issues]
        if Counter(CONTROLS.findall(unit.source))!=Counter(CONTROLS.findall(target)):
            errors.append('Variables, controles o iconos alterados')
        if errors:
            # Visible in Translator but never inserted by the writer while pending.
            proposal=replace(proposal,status=TranslationStatus.UNTRANSLATED,
                             notes=proposal.notes+'\nNO REINSERTAR: '+'; '.join(errors))
            blocked.append({'id':unit.id,'source':unit.source,'target':target,'issues':errors})
        else:
            applied+=1
        result.append(proposal)
    return result,applied,blocked
