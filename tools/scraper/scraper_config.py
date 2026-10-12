"""Persistent preferences with Windows DPAPI-protected credentials."""
import base64
import ctypes
import json
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from ctypes import wintypes


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def crypt(data, decrypt=False):
    if os.name != "nt":
        raise OSError("El guardado cifrado de credenciales requiere Windows.")
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    library = ctypes.WinDLL("crypt32", use_last_error=True)
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise OSError("Windows no pudo cifrar o recuperar las credenciales.")
    free = ctypes.WinDLL("kernel32", use_last_error=True).LocalFree
    free.argtypes = [ctypes.c_void_p]
    free.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        free(output.data)


class ConfigStore:
    def __init__(self, path=None):
        directory = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
        self.path = path or directory / "scraper_config.json"
        self.warning = ""
        self.broken = False
        self.previous_credentials = None
        self.credentials_unavailable = False

    def load(self):
        if not self.path.exists():
            return {}, {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("preferences", {}), dict):
                raise ValueError()
        except (OSError, ValueError):
            self.broken = True
            self.warning = "No se pudo leer la configuración. Se conservará una copia al guardar."
            return {}, {}
        credentials = data.get("credentials")
        self.previous_credentials = credentials
        secrets = {}
        if credentials:
            try:
                if credentials.get("provider") != "windows-dpapi":
                    raise ValueError()
                secrets = json.loads(crypt(base64.b64decode(credentials["data"], validate=True), decrypt=True))
                if not isinstance(secrets, dict):
                    raise ValueError()
            except (OSError, ValueError, KeyError, AttributeError, TypeError):
                secrets = {}
                self.credentials_unavailable = True
                self.warning = "No se pudieron recuperar las credenciales. Configúralas con este usuario de Windows."
        return data.get("preferences", {}), secrets

    def save(self, preferences, secrets):
        credentials = self.previous_credentials if self.credentials_unavailable and not any(secrets.values()) else None
        if any(secrets.values()):
            credentials = {"provider": "windows-dpapi", "data": base64.b64encode(crypt(json.dumps(secrets).encode("utf-8"))).decode("ascii")}
            self.credentials_unavailable = False
        document = {"version": 1, "preferences": preferences, "credentials": credentials}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.broken and self.path.exists():
            shutil.copy2(self.path, self.path.with_name(self.path.name + ".invalid-" + uuid.uuid4().hex[:8] + ".bak"))
            self.broken = False
        with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8"))
        try:
            temporary.replace(self.path)
            self.previous_credentials = credentials
        finally:
            temporary.unlink(missing_ok=True)
