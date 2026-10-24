"""Lazy game adapters and build profiles; the base has no game-specific imports."""
from dataclasses import dataclass
from importlib import import_module
import os


@dataclass(frozen=True)
class Adapter:
    id: str
    title: str
    archive_name: str
    encoding: str
    terminator: bytes
    reader: str
    writer: str
    writer_function: str

    def matches(self, paths):
        archives = sorted(p for p in paths if p.endswith('/' + self.archive_name))
        if self.id == 'pokapoka':
            archives = [p for p in archives if p[:-3] + 'FAT' in paths and p[:-3] + 'BHD' in paths]
        return archives

    def scan(self, workspace, logical, progress=None):
        module = import_module(self.reader)
        if self.id == 'digimon':
            return module.scan_arcv_text(workspace.layout.path('extracted', logical), logical, progress=progress)
        parent = logical.rsplit('/', 1)[0]
        return module.scan_archive(workspace.layout.path('extracted', parent), parent, progress=progress)

    def accepts(self, candidate, origin):
        return (candidate.encoding == self.encoding and candidate.terminator == self.terminator
                and (self.id != 'digimon' or origin.get('format') == 'btx'))

    def rebuild(self, *args, **kwargs):
        return getattr(import_module(self.writer), self.writer_function)(*args, **kwargs)


ADAPTERS = (
    Adapter('pokapoka', 'Poka Poka Ailu Mura G', 'POKAPOKA.BND', 'cp932', b'\0',
            'romkit_core.adapters.pokapoka.reader', 'romkit_core.adapters.pokapoka.writer', 'rebuild_pokapoka'),
    Adapter('digimon', 'Digimon World Re:Digitize PSP', 'ARCVINFO.BIN', 'utf-16-le', b'\0\0',
            'romkit_core.adapters.digimon.text', 'romkit_core.adapters.digimon.writer', 'rebuild_arcv'),
)
PROFILES = {'all': ('pokapoka', 'digimon'), 'base': (), 'pokapoka': ('pokapoka',), 'digimon': ('digimon',)}


def profile():
    name = os.environ.get('ROMKIT_PROFILE', 'all')
    if name not in PROFILES:
        raise ValueError(f'Perfil ROMKit desconocido: {name}')
    return name


def enabled_adapters():
    return tuple(a for a in ADAPTERS if a.id in PROFILES[profile()])


def adapter_for_archive(logical):
    return next((a for a in enabled_adapters() if logical.endswith('/' + a.archive_name)), None)
