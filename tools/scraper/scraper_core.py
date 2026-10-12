"""Sources, matching and frontend exports, independent of the desktop UI."""
from __future__ import annotations

import difflib
import html.parser
import json
import math
import re
import shutil
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import quote, unquote, urlencode, urljoin, urlsplit, parse_qsl, urlunsplit
from urllib.request import Request, urlopen

BASE = "https://thumbnails.libretro.com/"
SYSTEMS = {
    "GBA": ("Nintendo - Game Boy Advance", "gba"),
    "GB": ("Nintendo - Game Boy", "gb"), "GBC": ("Nintendo - Game Boy Color", "gbc"),
    "NES": ("Nintendo - Nintendo Entertainment System", "nes"),
    "SNES": ("Nintendo - Super Nintendo Entertainment System", "snes"),
    "N64": ("Nintendo - Nintendo 64", "n64"), "NDS": ("Nintendo - Nintendo DS", "nds"),
    "PS": ("Sony - PlayStation", "psx"), "PSP": ("Sony - PlayStation Portable", "psp"),
    "PS2": ("Sony - PlayStation 2", "ps2"),
    "MD": ("Sega - Mega Drive - Genesis", "megadrive"),
    "SMS": ("Sega - Master System - Mark III", "mastersystem"),
    "GG": ("Sega - Game Gear", "gamegear"), "DC": ("Sega - Dreamcast", "dreamcast"),
    "PCE": ("NEC - PC Engine - TurboGrafx 16", "pcengine"),
}
FRONTENDS = ("Cannoli", "EmulationStation / RetroPie", "ES-DE")
EXTENSIONS = {".gba", ".gb", ".gbc", ".nes", ".sfc", ".smc", ".n64", ".z64", ".v64", ".nds",
              ".iso", ".chd", ".cue", ".m3u", ".pbp", ".cso", ".md", ".gen", ".sms", ".gg", ".pce", ".zip", ".7z"}


@dataclass(frozen=True)
class Candidate:
    name: str
    url: str
    source: str
    page: str = ""
    license: str = ""
    score: float | None = None


def fetch(url: str, headers: dict | None = None) -> bytes:
    if urlsplit(url).scheme != "https":
        raise ValueError("Solo se permiten URLs HTTPS")
    request = Request(url, headers={"User-Agent": "ROMKit-Art/0.2 (desktop artwork downloader)", **(headers or {})})
    with urlopen(request, timeout=20) as response:
        data = response.read(12 * 1024 * 1024 + 1)
    if len(data) > 12 * 1024 * 1024:
        raise ValueError("Respuesta demasiado grande")
    return data


def normalized(name: str) -> str:
    # Strip known dump metadata, but keep hacks, prototypes and edition names.
    def metadata(match):
        content = match.group(1) or match.group(2)
        parts = re.split(r"[,\s]+", content.strip())
        known = {"usa", "europe", "japan", "world", "uk", "spain", "france", "germany", "italy", "australia", "korea", "china", "taiwan", "canada", "brazil", "u", "e", "j", "en", "fr", "de", "es", "it", "ja", "pt", "nl", "sv", "no", "da", "fi", "zh", "ko", "ru", "pl"}
        text = content.strip().casefold()
        if all(p.casefold() in known for p in parts) or re.fullmatch(r"(?:rev|v|version)[ .]*[\d]+(?:\.\d+)*", text) or re.fullmatch(r"(?:disc|disk|cd)\s*\d+(?:\s*(?:of|/)\s*\d+)?", text) or text == "!":
            return " "
        return match.group(0)
    name = re.sub(r"\(([^()]*)\)|\[([^\[\]]*)\]", metadata, name)
    name = re.sub(r"^\s*\d{3,5}\s*[-_.]\s*", "", name)
    name = re.sub(r",\s*(the|a|an)\s*$", r" \1", name, flags=re.I)
    name = re.sub(r"^(the|a|an)\s+", "", name, flags=re.I)
    name = re.sub(r"\s+(the|a|an)$", "", name, flags=re.I)
    name = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    return re.sub(r"[^\w]+", " ", name).strip().casefold()


def index_candidates(candidates: list[Candidate]) -> dict[str, list[Candidate]]:
    index = {}
    for candidate in candidates:
        index.setdefault(normalized(candidate.name), []).append(candidate)
    return index


def indexed_candidates(stem: str, index: dict[str, list[Candidate]]) -> list[Candidate]:
    keys = {normalized(stem), normalized(re.sub(r'[&*/:`<>?\\|]', "_", stem))}
    return list(dict.fromkeys(candidate for key in keys for candidate in index.get(key, [])))


def automatic(stem: str, candidates: list[Candidate], preferred_region: str = "") -> Candidate | None:
    sanitized = re.sub(r'[&*/:`<>?\\|]', "_", stem).casefold()
    key = normalized(stem)
    if not key:
        return None
    matches = [c for c in candidates if c.name.casefold() == sanitized or normalized(c.name) == key]
    if not matches:
        return None
    aliases = {"Europe": {"europe", "e", "eur"}, "USA": {"usa", "u", "us"},
               "Japan": {"japan", "j", "jp"}, "World": {"world"}}
    def regions(name):
        tokens = set(re.findall(r"\w+", " ".join(re.findall(r"[([]([^\])]+)[\])]", name)).casefold()))
        return [region for region, words in aliases.items() if tokens & words]
    priorities = regions(stem) or ([preferred_region] if preferred_region in aliases else [])
    def rank(candidate):
        available = regions(candidate.name)
        region_rank = next((len(priorities) - index for index, region in enumerate(priorities) if region in available), 0)
        proximity = difflib.SequenceMatcher(None, stem.casefold(), candidate.name.casefold()).ratio()
        return (candidate.name.casefold() == sanitized, region_rank, proximity)
    # Same-title variants are resolved automatically, with a stable tie-breaker.
    return min(matches, key=lambda c: (*(-value for value in rank(c)), c.name.casefold(), c.url))


def search(query: str, candidates: list[Candidate]) -> list[Candidate]:
    key = normalized(query)
    if not key:
        return []
    return sorted(candidates, key=lambda c: (key in normalized(c.name), difflib.SequenceMatcher(None, key, normalized(c.name)).ratio()), reverse=True)[:50]


class Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(v for k, v in attrs if k == "href" and v)


def libretro(system: str) -> list[Candidate]:
    url = BASE + quote(system, safe="") + "/Named_Boxarts/"
    parser = Links()
    parser.feed(fetch(url).decode("utf-8"))
    candidates = {}
    for href in parser.links:
        target = urljoin(url, href)
        if not target.startswith(url) or urlsplit(target).query:
            continue
        name = unquote(urlsplit(target).path.rsplit("/", 1)[-1])
        if name.lower().endswith(".png"):
            candidates[name] = Candidate(name[:-4], target, "Libretro", target)
    return list(candidates.values())


def commons(query: str) -> list[Candidate]:
    params = dict(action="query", format="json", generator="search", gsrsearch=query,
                  gsrnamespace=6, gsrlimit=20, prop="imageinfo", iiprop="url|mime|extmetadata")
    result = json.loads(fetch("https://commons.wikimedia.org/w/api.php?" + urlencode(params)))
    if "error" in result:
        raise ValueError(result["error"].get("info", "Error de Wikimedia"))
    candidates = []
    for page in result.get("query", {}).get("pages", {}).values():
        info = page.get("imageinfo", [{}])[0]
        if info.get("mime") not in ("image/png", "image/jpeg"):
            continue
        license_name = info.get("extmetadata", {}).get("LicenseShortName", {}).get("value", "Consultar ficha")
        candidates.append(Candidate(page["title"].removeprefix("File:"), info["url"], "Wikimedia Commons", info.get("descriptionurl", ""), license_name))
    return candidates


def steamgriddb(query: str, api_key: str, platform_titles: set[str] | None = None) -> list[Candidate]:
    """Search public artwork using the user's SteamGridDB API key."""
    from urllib.error import HTTPError
    if not api_key.strip():
        raise ValueError("Introduce tu clave API de SteamGridDB para buscar.")
    headers = {"Authorization": "Bearer " + api_key.strip()}
    def api(path):
        try:
            result = json.loads(fetch("https://www.steamgriddb.com/api/v2/" + path, headers))
        except HTTPError as error:
            if error.code in (401, 403):
                raise ValueError("SteamGridDB rechazó la clave API.") from None
            if error.code == 429:
                raise ValueError("SteamGridDB ha limitado las peticiones. Prueba más tarde.") from None
            raise
        if not result.get("success"):
            raise ValueError("SteamGridDB no pudo completar la consulta.")
        return result.get("data", [])
    results = []
    def rating(grid):
        try:
            value = float(grid.get("score"))
            return value if math.isfinite(value) else None
        except (TypeError, ValueError):
            return None
    games = api("search/autocomplete/" + quote(query, safe=""))
    if platform_titles is not None:
        games = [game for game in games if normalized(game["name"]) in platform_titles]
    for game in games[:5]:
        grids = [grid for grid in api(f"grids/game/{game['id']}?types=static&limit=50") if grid.get("mime") in (None, "image/png", "image/jpeg") and not grid.get("nsfw") and not grid.get("humor")]
        # Preserve game relevance; rank its artwork by the API's vote score.
        grids.sort(key=lambda grid: (rating(grid) is None, -(rating(grid) or 0)))
        for grid in grids[:12]:
            author = grid.get("author", {}).get("name", "")
            results.append(Candidate(f"{game['name']} · {grid.get('width', '?')}×{grid.get('height', '?')} · {author}", grid["url"], "SteamGridDB", f"https://www.steamgriddb.com/grid/{grid['id']}", score=rating(grid)))
    return results


def automatic_steamgriddb(stem: str, candidates: list[Candidate]) -> Candidate | None:
    """Only accept the same game title; prefer portrait artwork among its variants."""
    matches = [c for c in candidates if normalized(c.name.split(" · ", 1)[0]) == normalized(stem)]
    if not matches:
        return None
    # Variants of a title share its normalized name; choose a portrait cover first.
    def portrait(candidate):
        dimensions = re.search(r" · (\d+)×(\d+) · ", candidate.name)
        return bool(dimensions and int(dimensions[2]) > int(dimensions[1]))
    selected = max(matches, key=lambda c: (portrait(c), c.score is not None, c.score or 0))
    return replace(selected, name=selected.name.split(" · ", 1)[0])


def public_url(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k.casefold() not in {"devid", "devpassword", "ssid", "sspassword"}]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def image_extension(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    raise ValueError("Solo se admiten imágenes PNG o JPEG")


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
        temp = Path(file.name)
        file.write(data)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


@dataclass(frozen=True)
class Export:
    frontend: str
    root: Path
    roms: Path
    tag: str
    system: str

    def directory(self) -> Path:
        if self.frontend == "Cannoli":
            return self.root / "Art" / self.tag
        if self.frontend == "ES-DE":
            return self.root / "downloaded_media" / self.system / "covers"
        return self.root / self.system / "images"

    def xml_path(self) -> Path | None:
        if self.frontend == "Cannoli":
            return None
        if self.frontend == "ES-DE":
            return self.root / "gamelists" / self.system / "gamelist.xml"
        return self.root / self.system / "gamelist.xml"

    def existing(self, rom: Path) -> Path | None:
        directory = self.directory()
        if not directory.exists():
            return None
        return next((p for p in directory.iterdir() if p.is_file() and p.stem == rom.stem and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")), None)

    def save(self, rom: Path, candidate: Candidate, data: bytes) -> Path:
        xml = self.xml_path()
        tree = ET.parse(xml) if xml and xml.exists() else ET.ElementTree(ET.Element("gameList"))
        if tree.getroot().tag != "gameList":
            raise ValueError("El XML existente no es un gameList")
        extension = image_extension(data)
        existing = self.existing(rom)
        destination = existing or self.directory() / (rom.stem + extension)
        if not existing:
            atomic_write(destination, data)
        if xml:
            relative = "./" + rom.relative_to(self.roms).as_posix()
            accepted_paths = {relative, relative[2:], str(rom), rom.as_posix()}
            game = next((g for g in tree.getroot().findall("game") if g.findtext("path") in accepted_paths), None)
            if game is None:
                game = ET.SubElement(tree.getroot(), "game")
                ET.SubElement(game, "path").text = relative
                ET.SubElement(game, "name").text = candidate.name
            if self.frontend != "ES-DE":
                element = game.find("image")
                if element is None:
                    element = ET.SubElement(game, "image")
                element.text = "./images/" + destination.name
            if xml.exists() and not xml.with_suffix(".xml.bak").exists():
                shutil.copy2(xml, xml.with_suffix(".xml.bak"))
            ET.indent(tree)
            atomic_write(xml, ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True))
        # Keep provenance and license information alongside the export.
        provenance = destination.with_suffix(destination.suffix + ".source.json")
        if not existing:
            atomic_write(provenance, json.dumps({**candidate.__dict__, "url": public_url(candidate.url)}, ensure_ascii=False, indent=2).encode("utf-8"))
        return destination



IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def migration_system(folder: str, frontend: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", folder.casefold())
    aliases = {"ps1": "PS", "playstation": "PS", "playstation1": "PS", "genesis": "MD"}
    for tag, (name, system) in SYSTEMS.items():
        for alias in (tag, name, system):
            aliases[re.sub(r"[^a-z0-9]", "", alias.casefold())] = tag
    tag = aliases.get(key)
    return (tag if frontend == "Cannoli" else SYSTEMS[tag][1]) if tag else folder


def migrate_covers(source_frontend: str, source_root: Path, target_frontend: str,
                   target_root: Path, stop=None, progress=None) -> dict:
    """Copy all systems' artwork without requiring ROM files or guessing ROM extensions."""
    if source_frontend not in FRONTENDS or target_frontend not in FRONTENDS:
        raise ValueError("Selecciona un frontend válido.")
    source_root, target_root = Path(source_root), Path(target_root)
    if source_frontend == target_frontend and source_root.resolve() == target_root.resolve():
        raise ValueError("El origen y el destino de las carátulas son iguales.")
    base = source_root / ("Art" if source_frontend == "Cannoli" else "downloaded_media") if source_frontend != "EmulationStation / RetroPie" else source_root
    if not base.is_dir():
        raise ValueError(f"No se encuentra la carpeta del frontend: {base}")
    folders = {p.name for p in base.iterdir() if p.is_dir()}
    if source_frontend == "ES-DE" and (source_root / "gamelists").is_dir():
        folders.update(p.name for p in (source_root / "gamelists").iterdir() if p.is_dir())
    result = {"total": 0, "systems": 0, "copied": 0, "existing": 0,
              "processed": 0, "errors": [], "cancelled": False, "unlinked": 0}
    plans = []
    for folder in sorted(folders):
        if stop is not None and stop.is_set():
            result["cancelled"] = True
            return result
        source = Export(source_frontend, source_root, source_root, folder, folder)
        target_folder = migration_system(folder, target_frontend)
        destination = Export(target_frontend, target_root, target_root, target_folder, target_folder)
        if not source.directory().is_dir() and not (source.xml_path() and source.xml_path().exists()):
            continue
        if source.directory().resolve() == destination.directory().resolve():
            raise ValueError("El origen y el destino de las carátulas son iguales.")
        # Each image is keyed by its destination name, including relative subfolders.
        images = {}
        if source.directory().is_dir():
            images = {p.relative_to(source.directory()): p for p in sorted(source.directory().rglob("*"))
                      if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS}
        source_games = []
        xml = source.xml_path()
        if xml and xml.exists():
            try:
                tree = ET.parse(xml)
                if tree.getroot().tag != "gameList":
                    raise ValueError("El XML no es un gameList")
                for game in tree.getroot().findall("game"):
                    path, image_path = game.findtext("path"), game.findtext("image")
                    relative_image = None
                    if path and image_path:
                        image = Path(image_path.replace(chr(92), "/"))
                        image = image if image.is_absolute() else xml.parent / image
                        if image.is_file():
                            # Use the game's filename rather than a custom artwork filename.
                            rom = Path(path.replace(chr(92), "/"))
                            relative_image = Path(rom.stem + image.suffix.lower())
                            try:
                                original_relative = image.resolve().relative_to(source.directory().resolve())
                                if original_relative != relative_image:
                                    images.pop(original_relative, None)
                            except ValueError:
                                pass
                            images[relative_image] = image
                    elif path:
                        rom_stem = Path(path.replace(chr(92), "/")).stem.casefold()
                        relative_image = next((rel for rel in images if rel.stem.casefold() == rom_stem), None)
                    source_games.append((game, relative_image))
            except (OSError, ValueError, ET.ParseError) as error:
                result["errors"].append(f"{folder}/gamelist.xml: {error}")
        if images:
            plans.append((folder, destination, images, source_games))
    result["total"] = sum(len(images) for _, _, images, _ in plans)
    result["systems"] = len(plans)
    if not result["total"]:
        if result["errors"]:
            return result
        raise ValueError("No se encontraron carátulas en el frontend de origen.")
    for folder, destination, images, source_games in plans:
        imported = {}
        for relative, image in images.items():
            if stop is not None and stop.is_set():
                result["cancelled"] = True
                break
            try:
                directory = destination.directory() / relative.parent
                existing = next((p for p in directory.iterdir() if p.is_file() and
                                 p.stem.casefold() == relative.stem.casefold() and
                                 p.suffix.lower() in IMAGE_EXTENSIONS), None) if directory.is_dir() else None
                output = existing or directory / relative.name
                if existing:
                    result["existing"] += 1
                else:
                    data = image.read_bytes()
                    image_extension(data)
                    atomic_write(output, data)
                    provenance = image.with_suffix(image.suffix + ".source.json")
                    if provenance.exists():
                        atomic_write(output.with_suffix(output.suffix + ".source.json"), provenance.read_bytes())
                    result["copied"] += 1
                imported[relative] = output
            except Exception as error:
                result["errors"].append(f"{folder}/{relative}: {error}")
            result["processed"] += 1
            if progress is not None:
                progress(result["processed"], result["total"], f"{folder}/{relative}")
        xml = destination.xml_path()
        if xml and imported:
            try:
                tree = ET.parse(xml) if xml.exists() else ET.ElementTree(ET.Element("gameList"))
                if tree.getroot().tag != "gameList":
                    raise ValueError("El XML existente no es un gameList")
                changed = False
                def path_key(path):
                    value = (path or "").replace(chr(92), "/")
                    return value[2:] if value.startswith("./") else value
                known = {path_key(g.findtext("path")): g for g in tree.getroot().findall("game")}
                # Preserve existing destination metadata; add only real paths from source XML.
                for original, relative in source_games:
                    path = original.findtext("path")
                    if not path:
                        continue
                    if Path(path).is_absolute():
                        path = "./" + Path(path).name
                    game = known.get(path_key(path))
                    if game is None:
                        game = ET.fromstring(ET.tostring(original))
                        game.find("path").text = path
                        tree.getroot().append(game)
                        known[path_key(path)] = game
                        stale = game.find("image")
                        if stale is not None:
                            game.remove(stale)
                        # Other media paths belong to the source installation.
                        for media in ("thumbnail", "video", "marquee", "fanart", "manual"):
                            element = game.find(media)
                            if element is not None:
                                game.remove(element)
                        changed = True
                linked = set()
                if target_frontend == "EmulationStation / RetroPie":
                    for game in tree.getroot().findall("game"):
                        path = game.findtext("path")
                        if not path:
                            continue
                        stem = Path(path.replace(chr(92), "/")).stem.casefold()
                        output = next((out for rel, out in imported.items() if rel.stem.casefold() == stem), None)
                        if output:
                            element = game.find("image")
                            if element is None:
                                element = ET.SubElement(game, "image")
                            element.text = "./images/" + output.relative_to(destination.directory()).as_posix()
                            linked.add(output)
                            changed = True
                    result["unlinked"] += len(set(imported.values()) - linked)
                if changed:
                    if xml.exists() and not xml.with_suffix(".xml.bak").exists():
                        shutil.copy2(xml, xml.with_suffix(".xml.bak"))
                    ET.indent(tree)
                    atomic_write(xml, ET.tostring(tree.getroot(), encoding="utf-8", xml_declaration=True))
            except Exception as error:
                result["errors"].append(f"{folder}/gamelist.xml: {error}")
        if result["cancelled"]:
            break
    return result
