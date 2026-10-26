from romkit_core.models import ProjectConfig, TranslationUnit
from romkit_core.project import write_config, write_jsonl
from romkit_translator.windows.main_window import MainWindow


def test_search_filters_and_edits_the_correct_record(tmp_path, qapp):
    write_config(tmp_path / 'project.toml', ProjectConfig('psp', '0' * 64, 'en', 'es'))
    write_jsonl(tmp_path / 'text/main.jsonl', [
        TranslationUnit('one', 'Hello', target='Hola'),
        TranslationUnit('two', '猫 [A]', target='Niño'),
    ])
    window = MainWindow()
    assert window.open_project(tmp_path)
    for query in ('NIÑO', '猫', '[A]', 'TWO'):
        window.search.setText(query)
        window._search_texts()
        assert window.proxy.rowCount() == 1
        assert window.current_row == 1
    window.editor.target.setPlainText('Gato')
    assert window.session.records[1].unit.target == 'Gato'
    window.search.setText('does not exist')
    window._search_texts()
    assert window.proxy.rowCount() == 0 and window.current_row is None
    window.search.clear()
    window._search_texts()
    assert window.proxy.rowCount() == 2
    assert window.session.records[1].unit.target == 'Gato'
    assert window.session.records[0].unit.target == 'Hola'
    window.save_project()
    window.close()
