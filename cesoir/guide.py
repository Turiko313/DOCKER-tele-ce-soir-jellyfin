from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import gzip
import io
import json
import logging
from pathlib import Path
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zipfile

from .config import Config, ExtensionError, atomic_json
from . import __version__
from .titles import normalize, title_year

LOG = logging.getLogger(__name__)
MAX_DOWNLOAD = 24 * 1024 * 1024
MAX_XML = 128 * 1024 * 1024


@dataclass(frozen=True)
class Programme:
    title: str
    titles: tuple[str, ...]
    channel_id: str
    channel_name: str
    start: datetime
    year: int | None
    provider_ids: dict[str, str]
    description: str = ""
    directors: tuple[str, ...] = ()


@dataclass(frozen=True)
class Guide:
    movies: tuple[Programme, ...]
    slot_count: int
    channels: dict[str, str]
    covered_channels: frozenset[str]


def xmltv_datetime(value: str) -> datetime:
    match = re.fullmatch(r"(\d{12}|\d{14})(?:\s*([+-]\d{4}|Z|UTC|GMT))?", value.strip())
    if not match:
        raise ValueError("date XMLTV invalide")
    digits, offset = match.groups()
    stamp = datetime.strptime(digits, "%Y%m%d%H%M%S" if len(digits) == 14 else "%Y%m%d%H%M")
    offset = offset or "+0000"
    if offset in {"Z", "UTC", "GMT"}:
        return stamp.replace(tzinfo=timezone.utc)
    hours, minutes = int(offset[1:3]), int(offset[3:5])
    if hours > 23 or minutes > 59:
        raise ValueError("décalage horaire XMLTV invalide")
    delta = timedelta(hours=hours, minutes=minutes) * (1 if offset[0] == "+" else -1)
    return stamp.replace(tzinfo=timezone(delta))


def _provider_ids(element: ET.Element) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in element.findall("url") + element.findall("episode-num") + element.findall("uniqueid"):
        value = (node.text or node.get("href") or "").strip().lower()
        system = (node.get("system") or "").lower()
        imdb = re.search(r"(?:imdb\.com/title/|^)(tt\d{5,12})(?:/|$|\?)", value)
        if imdb and ("imdb" in system or "imdb.com/title/" in value):
            result["imdb"] = imdb[1]
        tmdb = re.search(r"themoviedb\.org/movie/(\d+)", value)
        if tmdb:
            result["tmdb"] = tmdb[1]
        elif system in {"tmdb", "themoviedb.org", "themoviedb"} and value.isdecimal():
            result["tmdb"] = value
    return result


def _is_movie(element: ET.Element, include_tv_movies: bool) -> bool:
    categories = [normalize(c.text or "") for c in element.findall("category")]
    if any(re.match(r"^(serie|series|tv series|magazine|journal|sport|emission)\b", c) for c in categories):
        return False
    if any((e.get("system") or "").lower() in {"xmltv_ns", "onscreen"} or ((e.get("system") or "").lower() == "dd_progid" and (e.text or "").startswith("EP")) for e in element.findall("episode-num")):
        return False
    explicit_film = any(re.match(r"^(film|movie|movies|feature film)\b", c) for c in categories)
    if not explicit_film and any(re.match(r"^(documentaire|documentary|doc|making of|bande annonce|trailer)\b", c) for c in categories):
        return False
    if not include_tv_movies and any(re.match(r"^(telefilm|tv movie)\b", c) for c in categories):
        return False
    patterns = r"^(film|cinema|movie|movies|feature film|court metrage|long metrage)\b"
    if include_tv_movies:
        patterns = r"^(film|telefilm|cinema|movie|movies|feature film|tv movie|court metrage|long metrage)\b"
    return any(re.match(patterns, c) for c in categories)


def parse_guide(path: Path, config: Config, start: datetime, end: datetime) -> Guide:
    channels: dict[str, str] = {}
    movies: list[Programme] = []
    covered: set[str] = set()
    slots = 0
    selected = set(config.channels)
    bad_dates = 0
    try:
        with path.open("rb") as stream:
            iterator = ET.iterparse(stream, events=("start", "end"))
            event, root = next(iterator)
            if root.tag != "tv":
                raise ExtensionError("Le guide reçu n'est pas un fichier XMLTV (racine <tv> absente).")
            for event, node in iterator:
                if event != "end":
                    continue
                if node.tag == "channel":
                    channel_id = node.get("id", "")
                    channels[channel_id] = node.findtext("display-name") or channel_id
                    root.remove(node)
                elif node.tag == "programme":
                    channel_id = node.get("channel", "")
                    if not selected or channel_id in selected:
                        try:
                            stamp = xmltv_datetime(node.get("start", ""))
                        except ValueError:
                            bad_dates += 1
                        else:
                            # Use UTC for comparisons through clock changes.
                            if start.astimezone(timezone.utc) <= stamp < end.astimezone(timezone.utc):
                                slots += 1
                                covered.add(channel_id)
                                titles = tuple(dict.fromkeys(t.text.strip() for t in node.findall("title") if t.text and t.text.strip()))
                                if titles and _is_movie(node, config.include_tv_movies):
                                    french = next((t.text.strip() for t in node.findall("title") if (t.get("lang") or "").startswith("fr") and t.text and t.text.strip()), titles[0])
                                    year_text = node.findtext("date") or ""
                                    year = int(year_text[:4]) if re.match(r"(?:18|19|20)\d{2}", year_text) else title_year(french)
                                    description = next((d.text.strip() for d in node.findall("desc") if (d.get("lang") or "fr").startswith("fr") and d.text), node.findtext("desc") or "")
                                    directors = tuple(d.text.strip() for d in node.findall("credits/director") if d.text and d.text.strip())
                                    movies.append(Programme(french, titles, channel_id, channels.get(channel_id, channel_id), stamp, year, _provider_ids(node), description, directors))
                    root.remove(node)
    except (ET.ParseError, OSError, StopIteration) as error:
        raise ExtensionError(f"Guide XMLTV illisible : {error}") from None
    if bad_dates:
        # A damaged schedule must never clear a previously valid selection.
        raise ExtensionError(f"Le guide contient {bad_dates} horaire(s) invalide(s) sur les chaînes sélectionnées.")
    missing = selected - channels.keys()
    if missing:
        raise ExtensionError("Identifiants de chaînes inconnus : " + ", ".join(sorted(missing)))
    if slots == 0:
        raise ExtensionError("Le guide ne couvre pas cette soirée. La collection est conservée sans modification.")
    if selected - covered:
        raise ExtensionError("Guide incomplet pour les chaînes choisies : " + ", ".join(sorted(selected - covered)))
    movies.sort(key=lambda p: (p.start, p.channel_name, p.title))
    return Guide(tuple(movies), slots, channels, frozenset(covered))


class HttpsRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https":
            raise ExtensionError("Redirection non HTTPS refusée pour le guide TV.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class GuideCache:
    def __init__(self, config: Config):
        self.config = config
        self.path = config.data_dir / "guide.xml"
        self.meta = config.data_dir / "guide-cache.json"

    def _metadata(self) -> dict:
        try:
            value = json.loads(self.meta.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _age_hours(self, now: datetime) -> float:
        meta = self._metadata()
        if meta.get("url") != self.config.guide_url or not self.path.is_file():
            return float("inf")
        try:
            return max(0, (now.timestamp() - float(meta["downloaded_at"])) / 3600)
        except (KeyError, ValueError, TypeError):
            return float("inf")

    def _download(self, destination: Path) -> None:
        request = urllib.request.Request(self.config.guide_url, headers={"User-Agent": f"CeSoirJellyfin/{__version__}", "Accept-Encoding": "identity"})
        opener = urllib.request.build_opener(HttpsRedirects())
        with opener.open(request, timeout=45) as response:
            raw = response.read(MAX_DOWNLOAD + 1)
        if len(raw) > MAX_DOWNLOAD:
            raise ExtensionError("Le guide compressé dépasse la limite de 24 Mio.")
        if raw.startswith(b"\x1f\x8b"):
            source = gzip.GzipFile(fileobj=io.BytesIO(raw))
        elif raw.startswith(b"PK\x03\x04"):
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                files = [n for n in archive.namelist() if n.lower().endswith(".xml")]
                if len(files) != 1 or archive.getinfo(files[0]).file_size > MAX_XML:
                    raise ExtensionError("L'archive doit contenir un seul guide XML de moins de 128 Mio.")
                with archive.open(files[0]) as source:
                    self._copy_xml(source, destination)
            return
        else:
            source = io.BytesIO(raw)
        with source:
            self._copy_xml(source, destination)

    @staticmethod
    def _copy_xml(source, destination: Path) -> None:
        total, tail = 0, b""
        with destination.open("wb") as output:
            while chunk := source.read(65536):
                total += len(chunk)
                if total > MAX_XML:
                    raise ExtensionError("Le guide décompressé dépasse la limite de 128 Mio.")
                upper = (tail + chunk).upper()
                if b"<!ENTITY" in upper or b"\x00" in chunk:
                    raise ExtensionError("Le guide contient des entités XML ou un encodage non pris en charge.")
                tail = upper[-16:]
                output.write(chunk)

    def load(self, now: datetime, start: datetime, end: datetime) -> tuple[Guide, bool]:
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        age = self._age_hours(now)
        if age < self.config.guide_refresh_hours:
            try:
                return parse_guide(self.path, self.config, start, end), False
            except ExtensionError:
                pass  # A cached guide not covering tonight warrants an immediate refresh.
        temporary = self.path.with_suffix(".download")
        try:
            self._download(temporary)
            guide = parse_guide(temporary, self.config, start, end)
            temporary.replace(self.path)
            atomic_json(self.meta, {"url": self.config.guide_url, "downloaded_at": now.timestamp()})
            return guide, False
        except (OSError, ValueError, EOFError, zipfile.BadZipFile, ExtensionError) as error:
            LOG.warning("Actualisation du guide impossible (%s).", type(error).__name__)
            if age <= self.config.guide_max_age_hours:
                guide = parse_guide(self.path, self.config, start, end)
                LOG.warning("Utilisation du guide en cache, téléchargé il y a %.1f h.", age)
                return guide, True
            raise ExtensionError("Guide TV indisponible et aucun cache récent ne couvre cette soirée.") from None
        finally:
            temporary.unlink(missing_ok=True)
