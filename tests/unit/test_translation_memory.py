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
    assert all(u.status.value=='untranslated' and 'REINSERCIÓN PENDIENTE' in u.notes for u in result)
    assert result[0].target=='Sí' and result[1].target=='Nombre'


def test_memory_protects_game_controls_and_button_glyphs():
    for source,target in [('{name} Go','Ir'),('⑧Back','Volver'),('%NULL%','Nada'),('Need %%dKB','Necesitas %dKB'),('%02d items','objetos')]:
        result,count,blocked=apply_memory([TranslationUnit('1',source)],{source:target})
        assert count==0 and blocked and result[0].status.value=='untranslated'
    from romkit_core.project.translation_memory import CONTROLS
    assert not CONTROLS.findall('30% of the work is done; 80% full')


def test_editorial_unicode_is_translated_but_still_reports_insertion_limits():
    unit=TranslationUnit('1','Yes',encoding='cp932',constraints=TextConstraints(max_bytes=3))
    result,count,blocked=apply_memory([unit],{'Yes':'Sí'},editorial=True)
    assert result[0].target=='Sí' and result[0].status.value=='translated' and count==1
    assert blocked and result[0].encoding=='cp932' and result[0].constraints==unit.constraints
    result,count,blocked=apply_memory([TranslationUnit('2','{name} Go')],{'{name} Go':'Ir'},editorial=True)
    assert result[0].status.value=='untranslated' and blocked and count==0


def test_editorial_can_resume_generated_proposals_without_changing_reviewed_work():
    pending=TranslationUnit('1','Yes',target='Sí',encoding='cp932',notes='Propuesta editorial de IA',status='untranslated')
    reviewed=TranslationUnit('2','Yes',target='De acuerdo',status='reviewed')
    result,count,_=apply_memory([pending,reviewed],{'Yes':'Sí'},editorial=True)
    assert result[0].status.value=='translated' and result[1]==reviewed and count==1
