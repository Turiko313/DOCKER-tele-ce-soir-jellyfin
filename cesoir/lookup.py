from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import hashlib
import json
import logging
import re

from .config import Config, ExtensionError, atomic_json
from .guide import Programme, normalize
from .jellyfin import Jellyfin
from .matching import Match, Matcher
from .reporting import read_report

LOG = logging.getLogger(__name__)


def _clean(results: list[dict]) -> list[dict]:
    cleaned = []
    for row in results:
        if not isinstance(row, dict) or not isinstance(row.get("Name"), str):
            continue
        providers = row.get("ProviderIds")
        if not isinstance(providers, dict):
            continue
        ids = {}
        for key, value in providers.items():
            key, value = str(key).lower(), str(value).lower()
            if (key == "tmdb" and re.fullmatch(r"\d+", value)) or (key == "imdb" and re.fullmatch(r"tt\d{5,12}", value)):
                ids[key] = value
        cleaned.append({"Name": row["Name"], "ProductionYear": row.get("ProductionYear") if type(row.get("ProductionYear")) is int else None, "ProviderIds": ids})
    return cleaned


class MetadataLookup:
    """Resolve a TV title through Jellyfin, then require an existing exact ID."""

    def __init__(self, config: Config, client: Jellyfin, matcher: Matcher, now: datetime):
        self.client, self.matcher, self.now = client, matcher, now
        self.path = config.data_dir / "metadata-cache.json"
        entries = read_report(self.path).get("entries", {})
        self.entries = entries if isinstance(entries, dict) else {}
        self.requests = self.cache_hits = 0
        self.used_fallback = False

    def _results(self, programme: Programme) -> list[dict]:
        key = hashlib.sha256(json.dumps([programme.title, programme.year], ensure_ascii=False).encode()).hexdigest()
        cached = self.entries.get(key, {})
        try:
            age = self.now.timestamp() - float(cached["checked_at"])
            results = cached["results"]
            valid = isinstance(results, list) and all(isinstance(row, dict) for row in results) and 0 <= age
        except (KeyError, ValueError, TypeError):
            age, results, valid = float("inf"), [], False
        if valid and age < 24 * 3600:
            self.cache_hits += 1
            return _clean(results)
        self.requests += 1
        try:
            results = _clean(self.client.search_movie(programme.title, programme.year))
        except ExtensionError:
            if valid and age < 7 * 24 * 3600:
                self.cache_hits += 1
                self.used_fallback = True
                LOG.warning("Recherche de métadonnées indisponible ; utilisation du cache de secours pour « %s ».", programme.title)
                return _clean(results)
            raise ExtensionError("Recherche des traductions indisponible dans Jellyfin ; collection conservée. Nouvelle tentative au prochain passage. METADATA_LOOKUP=false permet de revenir aux titres locaux.") from None
        self.entries[key] = {"checked_at": self.now.timestamp(), "results": results}
        # Keep the cache bounded while retaining the latest searches.
        recent = {k:v for k,v in self.entries.items() if isinstance(v, dict) and type(v.get("checked_at")) in (int, float)}
        self.entries = dict(sorted(recent.items(), key=lambda pair: pair[1]["checked_at"], reverse=True)[:500])
        atomic_json(self.path, {"version": 1, "entries": self.entries})
        return results

    def match(self, programme: Programme) -> tuple[Match | None, str]:
        results = self._results(programme)
        if not programme.year and len(results) >= 20:
            return None, "métadonnées ambiguës"
        titles = {normalize(title) for title in programme.titles}
        exact = [r for r in results if normalize(r["Name"]) in titles and (programme.year is None or r["ProductionYear"] == programme.year)]
        if not exact:
            return None, "métadonnées non concluantes"
        ids: dict[str, str] = {}
        years: set[int] = set()
        for row in exact:
            providers = row["ProviderIds"]
            if not providers:
                return None, "métadonnées non concluantes"
            if ids and (not any(ids.get(k) == v for k, v in providers.items()) or any(k in ids and ids[k] != v for k, v in providers.items())):
                return None, "métadonnées ambiguës"
            ids.update(providers)
            if row["ProductionYear"]:
                years.add(row["ProductionYear"])
        if len(years) > 1:
            return None, "métadonnées ambiguës"
        match, reason = self.matcher.match(replace(programme, provider_ids=ids))
        if match:
            return replace(match, programme=programme, method="métadonnées Jellyfin + identifiant"), ""
        return None, "identifiant absent" if reason == "absent" else reason
