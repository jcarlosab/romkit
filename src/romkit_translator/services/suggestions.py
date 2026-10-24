"""Asynchronous suggestions; only query MyMemory's GET endpoint."""
import html
import json
import re
from urllib.parse import urlencode

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


def request_url(text, source, target):
    if not text.strip():
        raise ValueError("No hay texto original para traducir")
    if len(text.encode("utf-8")) > 500:
        raise ValueError("MyMemory admite un máximo de 500 bytes por consulta. Este texto es demasiado largo")
    for language in (source, target):
        if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language):
            raise ValueError("Revisa los códigos de idioma del proyecto (por ejemplo: en, ja, es-ES)")
    query = urlencode({"q": text, "langpair": source + "|" + target})
    return QUrl.fromEncoded(("https://api.mymemory.translated.net/get?" + query).encode("ascii"))


def parse_suggestion(data):
    try:
        response = json.loads(bytes(data))
        if not isinstance(response, dict):
            raise ValueError("Respuesta de traducción no válida")
        if response.get("quotaFinished"):
            raise ValueError("Se ha alcanzado el límite de consultas de MyMemory. Inténtalo más tarde")
        if str(response.get("responseStatus")) != "200":
            raise ValueError(str(response.get("responseDetails") or "El servicio no pudo traducir el texto"))
        text = response.get("responseData", {}).get("translatedText")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("El servicio no devolvió una sugerencia")
        return html.unescape(text)
    except (json.JSONDecodeError, TypeError, AttributeError, UnicodeDecodeError) as exc:
        raise ValueError("Respuesta de traducción no válida") from exc


class OnlineSuggestions(QObject):
    ready = Signal(object, str)
    failed = Signal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self.reply = None
        self.cache = {}

    def cancel(self):
        reply, self.reply = self.reply, None
        if reply is not None:
            reply.abort()

    def request(self, context, text, source, target):
        self.cancel()
        try:
            url = request_url(text, source, target)
        except ValueError as exc:
            self.failed.emit(context, str(exc))
            return
        key = (text, source, target)
        if key in self.cache:
            self.ready.emit(context, self.cache[key])
            return
        request = QNetworkRequest(url)
        request.setTransferTimeout(15000)
        request.setRawHeader(b"User-Agent", b"ROMKit-Translator/0.1")
        reply = self.network.get(request)
        self.reply = reply
        reply.finished.connect(lambda: self._finished(reply, context, key))

    def _finished(self, reply, context, key):
        try:
            if reply is not self.reply:
                return
            self.reply = None
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.failed.emit(context, "No se pudo obtener la sugerencia: " + reply.errorString())
                return
            try:
                if reply.bytesAvailable() > 1024 * 1024:
                    raise ValueError("Respuesta del servicio demasiado grande")
                text = parse_suggestion(reply.readAll())
            except ValueError as exc:
                self.failed.emit(context, str(exc))
                return
            if len(self.cache) >= 256:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = text
            self.ready.emit(context, text)
        finally:
            reply.deleteLater()
