import time
from dataclasses import replace
from PySide6.QtWidgets import QApplication
import pytest
from romkit_core.models import ProjectConfig,TranslationUnit
from romkit_core.project import write_config,write_jsonl,read_jsonl
from romkit_core.project.characters import plan_substitutions
from romkit_core.errors import ValidationError
from romkit_translator.services.project_session import ProjectSession
from romkit_translator.windows.main_window import MainWindow


def project(tmp_path):
    write_config(tmp_path/'project.toml',ProjectConfig('psp','0'*64,'en','es-ES'))
    write_jsonl(tmp_path/'text/main.jsonl',[TranslationUnit('1','Name {ñ}',target='Niño {ñ}',status='reviewed',encoding='cp932'),
                                         TranslationUnit('2','Yes',target='Sí',encoding='cp932')])
    return tmp_path


def wait(dialog):
    deadline=time.monotonic()+10
    while dialog.runner.busy and time.monotonic()<deadline:
        QApplication.processEvents();time.sleep(.005)
    QApplication.processEvents()
    assert not dialog.runner.busy


def test_preview_apply_undo_save_and_reopen(tmp_path,qapp):
    root=project(tmp_path);before=(root/'text/main.jsonl').read_bytes()
    window=MainWindow();assert window.open_project(root)
    window.show_characters();dialog=window._character_dialog;wait(dialog)
    assert 'ñ' in dialog.editors and 'í' in dialog.editors and not dialog.apply_button.isEnabled()
    dialog.editors['ñ'].setText('n');dialog.preview_button.click();wait(dialog)
    assert len(dialog.plan.changes)==1 and dialog.plan.occurrences==1
    assert not window.session.dirty and (root/'text/main.jsonl').read_bytes()==before
    dialog.apply_button.click()
    assert window.session.records[0].unit.target=='Nino {ñ}'
    assert window.session.records[0].unit.status.value=='translated'
    assert window.session.records[0].unit.source=='Name {ñ}' and window.session.dirty
    window.undo_characters_action.trigger()
    assert window.session.records[0].unit.status.value=='reviewed' and not window.session.dirty
    window.apply_characters(plan_substitutions(tuple(r.unit for r in window.session.records),{'ñ':'n','í':'i'}))
    assert window.save_project()
    reopened=ProjectSession();reopened.load(root)
    assert [r.unit.target for r in reopened.records]==['Nino {ñ}','Si']
    window.close();qapp.processEvents()


def test_cancel_and_stale_plan_preserve_all_edits(tmp_path,qapp):
    session=ProjectSession();session.load(project(tmp_path))
    plan=plan_substitutions(tuple(r.unit for r in session.records),{'ñ':'n','í':'i'})
    session.update(1,target='Personal',status='translated',notes='')
    with pytest.raises(ValidationError):session.apply_character_plan(plan)
    assert session.records[0].unit.target=='Niño {ñ}'
    window=MainWindow(session=session);window.show_characters();dialog=window._character_dialog
    dialog.reject();wait(dialog)
    assert session.records[1].unit.target=='Personal'
    window.save_project();window.close();qapp.processEvents()
