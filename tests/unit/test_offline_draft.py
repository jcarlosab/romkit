import importlib.util
from pathlib import Path
import pytest

from romkit_core.models import TranslationUnit
from romkit_core.project.translation_memory import CONTROLS

spec=importlib.util.spec_from_file_location('offline_draft',Path(__file__).parents[2]/'scripts/translation/offline_draft.py')
offline=importlib.util.module_from_spec(spec);spec.loader.exec_module(offline)


def test_offline_parts_keep_controls_whitespace_and_every_source_word():
    source='  Welcome {name}!\nNeed %%dKB  ⑧OK\n'+' '.join(['word']*100)
    plan=offline.parts(source)
    assert ''.join(text for _,text in plan)==source
    for translated,text in plan:
        if CONTROLS.fullmatch(text):assert not translated


def test_offline_preserves_lore_terms_and_filter_tables():
    plan=offline.parts('Poogie and Felyne {name}')
    assert (False,'Poogie') in plan and (False,'Felyne') in plan
    assert offline.preserve_reason(TranslationUnit('1','禁止',context='x/Forbidword.fmg'))
    assert offline.preserve_reason(TranslationUnit('2','Anise',context='x/Airou_Name.fmg'))
    assert offline.preserve_reason(TranslationUnit('3','■■■Message■■■'))
    assert offline.preserve_reason(TranslationUnit('4','Hello traveller')) is None
    assert offline.preserve_reason(TranslationUnit('5','ＨＥＬＬＯ')) is None
    assert offline.parts('ＨＥＬＬＯ')==[(True,'ＨＥＬＬＯ')]


def test_conditional_glossary_does_not_replace_unrelated_spanish_words():
    assert offline.glossary('This village','Este pueblo')=='Este pueblo'
    assert offline.glossary('The newspaper','Los artículos')=='Los artículos'
    assert offline.glossary('Mushrooms','Hongos')=='Hongos'


def test_offline_keeps_concurrent_editorial_changes(tmp_path):
    path=tmp_path/'main.jsonl';path.write_bytes(b'external edit')
    with pytest.raises(ValueError,match='cambió'):
        offline.checked_write(path,b'previous content',[])
    assert path.read_bytes()==b'external edit'
