import json
from urllib.parse import parse_qs, urlparse

import pytest
from PySide6.QtCore import QObject, Signal

from romkit_core.models import ProjectConfig, TranslationUnit
from romkit_core.project import read_jsonl, write_jsonl, write_config
from romkit_translator.services.suggestions import request_url, parse_suggestion
from romkit_translator.windows.main_window import MainWindow


class FakeSuggestions(QObject):
    ready = Signal(object, str)
    failed = Signal(object, str)
    def cancel(self):
        pass
    def request(self, context, text, source, target):
        self.requested = context, text, source, target


def test_request_encodes_text_languages_and_provider_limits():
    text = "A&B + {name} 日本語"
    url = bytes(request_url(text, "en", "es-ES").toEncoded()).decode()
    assert parse_qs(urlparse(url).query) == {"q": [text], "langpair": ["en|es-ES"]}
    with pytest.raises(ValueError, match="500"):
        request_url("あ" * 200, "ja", "es")
    assert parse_suggestion(json.dumps({"responseStatus": 200, "responseData": {"translatedText": "Tom &amp; Jerry"}}).encode()) == "Tom & Jerry"
    for response in (b"broken", b"[]", b'{"responseStatus":429,"responseDetails":"quota"}'):
        with pytest.raises(ValueError):
            parse_suggestion(response)


def test_suggestions_are_manual_review_check_persists_and_edits_reset_it(tmp_path, qapp):
    root = tmp_path / "project"
    root.mkdir()
    write_config(root / "project.toml", ProjectConfig("psp", "ab" * 32, "en", "es-ES"))
    write_jsonl(root / "text/main.jsonl", [TranslationUnit("a", "Hello", encoding="ascii"), TranslationUnit("b", "Goodbye")])
    provider = FakeSuggestions()
    window = MainWindow(suggestions=provider)
    assert window.open_project(root)
    window.editor.suggest_button.click()
    context, text, source, target = provider.requested
    assert (text, source, target) == ("Hello", "en", "es-ES")
    provider.ready.emit(context, "Hola")
    assert window.editor.target.toPlainText() == ""
    window.editor.use_suggestion_button.click()
    assert window.session.records[0].unit.target == "Hola"
    assert window.session.records[0].unit.status.value == "translated"
    window.editor.reviewed.setChecked(True)
    window.editor.notes.setPlainText("Checked")
    assert window.session.records[0].unit.status.value == "reviewed"
    assert window.save_project()
    assert read_jsonl(root / "text/main.jsonl")[0].status.value == "reviewed"
    window.editor.target.setPlainText("Hello")
    assert not window.editor.reviewed.isChecked()
    assert window.session.records[0].unit.status.value == "translated"
    window.editor.suggest_button.click()
    old_context = provider.requested[0]
    window.table.setCurrentIndex(window.proxy.index(1, 0))
    provider.ready.emit(old_context, "Must not appear")
    assert window.editor.target.toPlainText() == ""
    assert window.editor.suggestion.toPlainText() == ""
    window.save_project()
    window.close()
