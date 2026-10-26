from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import hashlib
import json
import logging
import re

from .config import Config, ExtensionError, atomic_json
from .guide import Programme
from .jellyfin import Jellyfin
from .matching import Match, Matcher
from .reporting import read_report
from .titles import clean_title, normalize, plot_similarity, title_forms, title_similarity

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
        cleaned.append({
            "Name": row["Name"],
            "OriginalTitle": row.get("OriginalTitle") if isinstance(row.get("OriginalTitle"), str) else "",
            "Overview": row.get("Overview")[:8000] if isinstance(row.get("Overview"), str) else "",
            "ProductionYear": row.get("ProductionYear") if type(row.get("ProductionYear")) is int else None,
            "ProviderIds": ids,
        })
    return cleaned


class MetadataLookup:
    """Resolve alternate titles using global candidates before checking ownership."""

    def __init__(self, config: Config, client: Jellyfin, matcher: Matcher, now: datetime):
        self.client, self.matcher, self.now = client, matcher, now
        self.path = config.data_dir / "metadata-cache.json"
        saved = read_report(self.path)
        entries = saved.get("entries", {}) if saved.get("version") == 2 else {}
        self.entries = entries if isinstance(entries, dict) else {}
        self.requests = self.cache_hits = 0
        self.used_fallback = False

    def _results(self, title: str, year: int | None, language: str) -> list[dict]:
        key = hashlib.sha256(json.dumps([title, year, language], ensure_ascii=False).encode()).hexdigest()
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
            result = self.client.search_movie(title, year) if language == "fr" else self.client.search_movie(title, year, language=language)
            results = _clean(result)
        except ExtensionError:
            if valid and age < 7 * 24 * 3600:
                self.cache_hits += 1
                self.used_fallback = True
                LOG.warning("Recherche de métadonnées indisponible ; utilisation du cache de secours pour « %s ».", title)
                return _clean(results)
            raise ExtensionError("Recherche des traductions indisponible dans Jellyfin ; collection conservée. Nouvelle tentative au prochain passage. METADATA_LOOKUP=false permet de revenir aux titres locaux.") from None
        self.entries[key] = {"checked_at": self.now.timestamp(), "results": results}
        recent = {k:v for k,v in self.entries.items() if isinstance(v, dict) and type(v.get("checked_at")) in (int, float)}
        self.entries = dict(sorted(recent.items(), key=lambda pair: pair[1]["checked_at"], reverse=True)[:500])
        atomic_json(self.path, {"version": 2, "entries": self.entries})
        return results

    def _select(self, results: list[dict], programme: Programme, truncated: bool) -> tuple[Match | None, str]:
        forms = {f for t in programme.titles for f in title_forms(t, relaxed=True)}
        exact, nearby = [], []
        for row in results:
            year = row["ProductionYear"]
            if programme.year and (not year or abs(year - programme.year) > 1):
                continue
            names = [row["Name"], row["OriginalTitle"]]
            if any(forms & title_forms(name, relaxed=True) for name in names if name):
                exact.append(row)
            elif programme.year and year == programme.year and len(normalize(clean_title(programme.title))) >= 16:
                score = max((title_similarity(t, name) for t in programme.titles for name in names if name), default=0.0)
                if score >= 0.8:
                    nearby.append((score, row))
        nearby.sort(key=lambda pair: pair[0], reverse=True)
        approximate = not exact
        selected = exact or ([row for score, row in nearby if nearby[0][0] - score < 0.06] if nearby and nearby[0][0] >= 0.94 else [])
        if not selected:
            return None, "métadonnées non concluantes"
        groups = []
        for row in selected:
            ids = row["ProviderIds"]
            if not ids:
                return None, "métadonnées non concluantes"
            linked = [g for g in groups if any(g["ids"].get(p) == value for p, value in ids.items())]
            if any(any(p in g["ids"] and g["ids"][p] != value for p, value in ids.items()) for g in linked):
                return None, "métadonnées ambiguës"
            if not linked:
                groups.append({"ids": dict(ids), "rows": [row]})
            else:
                merged_ids, merged_rows = dict(ids), [row]
                for group in linked:
                    if any(p in merged_ids and merged_ids[p] != value for p, value in group["ids"].items()):
                        return None, "métadonnées ambiguës"
                    merged_ids.update(group["ids"])
                    merged_rows.extend(group["rows"])
                    groups.remove(group)
                groups.append({"ids": merged_ids, "rows": merged_rows})
        method = "titre proche + année + identifiant" if approximate else "métadonnées Jellyfin + identifiant"
        chosen = None
        plot_ranked = []
        for group in groups:
            score, shared = max((plot_similarity(programme.description, r["Overview"]) for r in group["rows"]), default=(0.0, 0))
            plot_ranked.append((score, shared, group))
        plot_ranked.sort(key=lambda row: row[0], reverse=True)
        if plot_ranked and plot_ranked[0][0] >= 0.45 and plot_ranked[0][1] >= 5:
            runner = plot_ranked[1][0] if len(plot_ranked) > 1 else 0.0
            if plot_ranked[0][0] - runner >= 0.18:
                chosen = plot_ranked[0][2]
                method = "titre + synopsis TV + identifiant"
        if chosen is None and programme.directors:
            directors = {normalize(d) for d in programme.directors}
            verified = []
            for group in groups:
                local_ids = set().union(*(self.matcher.by_provider.get((p, v), set()) for p, v in group["ids"].items()))
                if any(self.matcher.directors(self.matcher.movies[i]) & directors for i in local_ids):
                    verified.append(group)
            if len(verified) == 1:
                chosen = verified[0]
                method = "titre + réalisateur + identifiant"
        if chosen is None:
            if programme.year:
                same_year = [g for g in groups if any(r["ProductionYear"] == programme.year for r in g["rows"])]
                groups = same_year or groups
            if len(groups) != 1 or (not programme.year and truncated):
                return None, "métadonnées ambiguës"
            chosen = groups[0]
        match, reason = self.matcher.match_identifiers(replace(programme, provider_ids=chosen["ids"]))
        if match:
            score = max((title_similarity(t, name) for t in programme.titles for r in chosen["rows"] for name in (r["Name"], r["OriginalTitle"]) if name), default=0.0) if approximate else None
            if score is not None and score < 0.94:
                return None, "métadonnées ambiguës"
            if programme.year and not any(r["ProductionYear"] == programme.year for r in chosen["rows"]):
                method += " (année de production/sortie ±1)"
            return replace(match, programme=programme, method=method, score=round(score, 4) if score is not None else None), ""
        return None, "identifiant absent" if reason == "absent" else reason

    def match(self, programme: Programme) -> tuple[Match | None, str]:
        titles = list(dict.fromkeys([clean_title(programme.title)] + [clean_title(t) for t in programme.titles]))[:3]
        queries = [(title, programme.year, language) for language in ("fr", "en") for title in titles if title]
        if programme.year:
            queries.extend((titles[0], None, language) for language in ("fr", "en"))
        results, seen = [], set()
        reason, truncated = "métadonnées non concluantes", False
        for title, year, language in queries:
            batch = self._results(title, year, language)
            truncated |= len(batch) >= 20
            for row in batch:
                marker = json.dumps(row, sort_keys=True, ensure_ascii=False)
                if marker not in seen:
                    seen.add(marker)
                    results.append(row)
            match, reason = self._select(results, programme, truncated)
            if match:
                return match, ""
        return None, reason
