from romkit_core.models import TranslationUnit, TextConstraints
from romkit_core.project.translation_memory import apply_memory


def test_memory_preserves_existing_work_and_counts_valid_translations():
    units=[TranslationUnit('1','Back',encoding='cp932',constraints=TextConstraints(max_bytes=6)),
           TranslationUnit('2','Back',target='Salir',status='reviewed'),TranslationUnit('3','Unmapped')]
    result,count,blocked=apply_memory(units,{'Back':'Volver'})
    assert result[0].target=='Volver' and result[0].status.value=='translated'
    assert result[1]==units[1] and result[2]==units[2]
    assert count==1 and not blocked


def test_unencodable_or_oversized_proposals_are_visible_but_not_insertable():
    units=[TranslationUnit('1','Yes',encoding='cp932'),
           TranslationUnit('2','Name',encoding='cp932',constraints=TextConstraints(max_bytes=4))]
    result,count,blocked=apply_memory(units,{'Yes':'Sí','Name':'Nombre'})
    assert count==0 and len(blocked)==2
    assert all(u.status.value=='untranslated' and 'NO REINSERTAR' in u.notes for u in result)
    assert result[0].target=='Sí' and result[1].target=='Nombre'


def test_memory_protects_game_controls_and_button_glyphs():
    for source,target in [('{name} Go','Ir'),('⑧Back','Volver'),('%NULL%','Nada')]:
        result,count,blocked=apply_memory([TranslationUnit('1',source)],{source:target})
        assert count==0 and blocked and result[0].status.value=='untranslated'
