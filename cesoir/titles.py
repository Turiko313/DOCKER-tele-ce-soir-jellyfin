"""Title evidence shared by the TV guide, local catalogue and metadata search."""
from __future__ import annotations

from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import PurePosixPath
import re
import unicodedata

ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10", "i": "1"}
ARTICLES = {"le", "la", "les", "l", "un", "une", "des", "the", "a", "an"}
STOPWORDS = set("a au aux avec ce ces dans de des du elle en est et eux il ils je la le les leur lui mais ne nous on ou par pas pour que qui sa se ses son sur un une vous the a an and as at be by for from he her his in is it its of on or she that their they this to was were with film movie vie homme femme jour fait faire va plus tout tous entre alors apres avant doit jeune".split())
LABEL = r"(?:vf|vo|vost(?:fr)?|in[eé]dit|rediffusion|version\s+(?:restaur[eé]e|longue|courte|originale|fran[cç]aise|int[eé]grale)|director'?s\s+cut|extended(?:\s+cut)?|remaster(?:ed|is[eé])?|4k|uhd|hd)"


@lru_cache(maxsize=32768)
def normalize(value: str) -> str:
    value = value.replace("œ", "oe").replace("Œ", "OE").replace("æ", "ae").replace("Æ", "AE")
    value = "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))
    return " ".join(re.findall(r"[^\W_]+", value, flags=re.UNICODE))


@lru_cache(maxsize=16384)
def clean_title(value: str) -> str:
    value = re.sub(r"^\s*(?:cin[eé]ma|film|t[eé]l[eé]film)\s*[:–—]\s*", "", value, flags=re.I)
    previous = None
    while previous != value:
        previous = value
        value = re.sub(rf"\s*[\[(]\s*(?:{LABEL}|(?:18|19|20)\d{{2}})\s*[\])]\s*$", "", value, flags=re.I)
        value = re.sub(rf"\s+[-–—]\s*{LABEL}\s*$", "", value, flags=re.I)
    return value.strip()


def title_year(value: str) -> int | None:
    found = re.search(r"[\[(]((?:18|19|20)\d{2})[\])]\s*(?:[\[(].*?[\])])?\s*$", value)
    return int(found[1]) if found else None


def _ordinals(value: str) -> str:
    return re.sub(r"\b(\d+)(?:ere|re|er|ieme|eme|e)(?=\s+(?:partie|chapitre|volet|episode)\b)", r"\1", value)


@lru_cache(maxsize=16384)
def title_alias_pair(value: str) -> tuple[str, str] | None:
    """Return possible bilingual names for lookup, never strip a subtitle blindly."""
    found = re.fullmatch(r"(.+?)\s*\(([^()]+)\)", clean_title(value))
    if not found:
        return None
    pair = tuple(t.strip() for t in found.groups())
    if any(len(normalize(t)) < 4 or not any(c.isalpha() for c in t) for t in pair):
        return None
    if re.fullmatch(LABEL, pair[1], flags=re.I) or number_signature(pair[0]) != number_signature(pair[1]):
        return None
    return pair


@lru_cache(maxsize=32768)
def title_forms(value: str, *, relaxed: bool = False) -> frozenset[str]:
    forms = {normalize(value), normalize(clean_title(value))} - {""}
    forms.update(_ordinals(f) for f in list(forms))
    for form in list(forms):
        words = form.split()
        if len(words) > 1:
            forms.add(" ".join(ROMAN.get(word, word) for word in words))
    if relaxed:
        for form in list(forms):
            words = form.split()
            if words and words[0] in ARTICLES and len(words) > 1:
                forms.add(" ".join(words[1:]))
            # Ampersands disappear during normalization. Treat their written
            # French/English forms alike only in the evidence-gated pass.
            if len(words) >= 3:
                forms.add(" ".join(w for w in words if w not in {"and", "et"}))
    return frozenset(forms - {""})


@lru_cache(maxsize=16384)
def number_signature(value: str) -> tuple[str, ...]:
    return tuple(ROMAN.get(w, w) for w in _ordinals(normalize(clean_title(value))).split() if w.isdecimal() or w in ROMAN)


def title_similarity(left: str, right: str) -> float:
    if number_signature(left) != number_signature(right):
        return 0.0
    a, b = title_forms(left, relaxed=True), title_forms(right, relaxed=True)
    if a & b:
        return 1.0
    return max((SequenceMatcher(None, x, y, autojunk=False).ratio() for x in a for y in b), default=0.0)


def filename_evidence(path: str) -> tuple[str, int | None, dict[str, str]]:
    name = PurePosixPath(path.replace("\\", "/")).stem
    ids = {}
    for provider, value in re.findall(r"[\[{](tmdb|imdb)(?:id)?[-= ]+([a-z0-9]+)[\]}]", name, flags=re.I):
        provider, value = provider.lower(), value.lower()
        if (provider == "tmdb" and value.isdecimal()) or (provider == "imdb" and re.fullmatch(r"tt\d{5,12}", value)):
            ids[provider] = value
    name = re.sub(r"\s*[\[{](?:tmdb|imdb)(?:id)?[-= ][^\]}]+[\]}]", "", name, flags=re.I)
    year_match = re.search(r"[\[(]((?:18|19|20)\d{2})[\])]", name)
    if not year_match:
        year_match = re.search(r"[ ._-]((?:19|20)\d{2})(?=[ ._-]+(?:2160p|1080p|720p|480p|bluray|brrip|webrip|web[ ._-]?dl|hdtv)\b)", name, flags=re.I)
    year = int(year_match[1]) if year_match else None
    if year_match:
        name = name[:year_match.start()]
    return name.replace(".", " ").replace("_", " ").strip(" -"), year, ids


def plot_similarity(description: str, overview: str) -> tuple[float, int]:
    wanted = {w for w in normalize(description).split() if len(w) >= 3 and w not in STOPWORDS}
    offered = {w for w in normalize(overview).split() if len(w) >= 3 and w not in STOPWORDS}
    shared = len(wanted & offered)
    return (shared / len(wanted), shared) if len(wanted) >= 8 and len(offered) >= 8 else (0.0, shared)
