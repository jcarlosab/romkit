from dataclasses import replace
import pytest
from romkit_core.models import TranslationUnit,TextConstraints
from romkit_core.project.characters import inspect_characters,plan_substitutions
from romkit_core.errors import ValidationError
from romkit_core.tasks import TaskCancelled


def test_inventory_counts_targets_not_sources_and_excludes_controls():
    units=[TranslationUnit('a','Original ñ',target='niño ñ {señal} ⑧ <á> %%d',encoding='cp932'),
           TranslationUnit('b','Original é',target='ñé TOKENñ',tokens=('TOKENñ',),encoding='utf-8')]
    info={x.character:x for x in inspect_characters(units)}
    assert set(info)=={'ñ','é'}
    assert (info['ñ'].occurrences,info['ñ'].entries)==(3,2)
    assert info['ñ'].unsupported==('cp932',)


def test_simultaneous_replacements_preserve_originals_tokens_and_clear_review():
    u=TranslationUnit('1','Fuente á',target='áñ {ñ} ⑧ <á> TOKENñ',tokens=('TOKENñ',),status='reviewed')
    plan=plan_substitutions([u],{'á':'ñ','ñ':'n'})
    assert plan.changes[0].after.target=='ñn {ñ} ⑧ <á> TOKENñ'
    assert plan.changes[0].after.source==u.source and plan.changes[0].after.status.value=='translated'
    assert u.target.startswith('áñ') and plan.occurrences==2


def test_delete_noop_encoding_limits_and_injected_controls():
    u=TranslationUnit('1','X',target='ñ',status='reviewed',encoding='cp932',constraints=TextConstraints(max_bytes=1))
    assert plan_substitutions([u],{'ñ':'ñ'}).changes==()
    assert plan_substitutions([u],{'ñ':''}).changes[0].after.status.value=='untranslated'
    assert plan_substitutions([u],{'ñ':'nn'}).invalid_entries==1
    for mapping in ({'ñ':'{new}'},{'ñ':'\0'},{'nn':'n'}):
        with pytest.raises(ValidationError):plan_substitutions([u],mapping)


def test_cancel_is_propagated_before_any_changes():
    def cancel(_):raise TaskCancelled()
    with pytest.raises(TaskCancelled):plan_substitutions([TranslationUnit('1','X',target='ñ')],{'ñ':'n'},progress=cancel)
