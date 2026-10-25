"""Apply explicit, local editorial translations without guessing or online requests."""
from collections import Counter
from dataclasses import replace
import re

from romkit_core.models import TranslationStatus
from romkit_core.validation import validate_translation

CONTROLS = re.compile(r'\{[^{}]+\}|<[^<>]+>|%[^%\s]+%|%%[diuoxXfFeEgGaAcspn]?|%(?:\d+\$)?[-+#0]*(?:\d+|\*)?(?:\.(?:\d+|\*))?[diuoxXfFeEgGaAcspn]|[\x00-\x08\x0b\x0c\x0e-\x1f\u2460-\u2473]')


def apply_memory(units, memory, *, editorial=False):
    """Keep existing edits; proposals failing codec, space or controls stay pending."""
    result=[];applied=0;blocked=[]
    for unit in units:
        target=memory.get(unit.source)
        promoting=(editorial and unit.status==TranslationStatus.UNTRANSLATED and unit.target==target
                   and 'Propuesta editorial de IA' in unit.notes)
        if target is None or ((unit.target or unit.status!=TranslationStatus.UNTRANSLATED) and not promoting):
            result.append(unit);continue
        proposal=replace(unit,target=target,status=TranslationStatus.TRANSLATED,
                         notes=(unit.notes+'\nPropuesta editorial de IA; pendiente de revisión en contexto.').strip())
        errors=[issue.message for issue in validate_translation(proposal).issues]
        unsafe=Counter(CONTROLS.findall(unit.source))!=Counter(CONTROLS.findall(target))
        if unsafe:
            errors.append('Variables, controles o iconos alterados')
        if errors:
            # Visible in Translator but never inserted by the writer while pending.
            proposal=replace(proposal,status=TranslationStatus.TRANSLATED if editorial and not unsafe else TranslationStatus.UNTRANSLATED,
                             notes=proposal.notes+'\nREINSERCIÓN PENDIENTE: '+'; '.join(errors))
            blocked.append({'id':unit.id,'source':unit.source,'target':target,'issues':errors})
        if not errors or (editorial and not unsafe):
            applied+=1
        result.append(proposal)
    return result,applied,blocked
