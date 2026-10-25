from __future__ import annotations

from dataclasses import dataclass

from .config import ExtensionError
from .guide import Programme, normalize


@dataclass(frozen=True)
class Match:
    programme: Programme
    movie: dict
    method: str


class Matcher:
    """Exact IDs first, then exact normalized titles; never fuzzy matching."""

    def __init__(self, movies: list[dict], overrides: dict[str, str] | None = None):
        self.movies = {m["Id"]: m for m in movies if m.get("Type") == "Movie" and not m.get("IsPlaceHolder") and m.get("LocationType") != "Virtual"}
        self.by_title: dict[str, set[str]] = {}
        self.by_provider: dict[tuple[str, str], set[str]] = {}
        self.overrides = {normalize(k): v.replace("-", "").lower() for k, v in (overrides or {}).items()}
        for title, movie_id in self.overrides.items():
            if movie_id not in self.movies:
                raise ExtensionError(f"La correspondance manuelle pour « {title} » ne désigne pas un film disponible.")
        for movie_id, movie in self.movies.items():
            for title in (movie.get("Name"), movie.get("OriginalTitle")):
                if title and normalize(title):
                    self.by_title.setdefault(normalize(title), set()).add(movie_id)
            for key, value in (movie.get("ProviderIds") or {}).items():
                if value:
                    self.by_provider.setdefault((key.lower(), str(value).lower()), set()).add(movie_id)

    def _pick(self, candidates: set[str], programme: Programme, method: str) -> tuple[Match | None, str]:
        if not candidates:
            return None, "absent"
        if method == "titre" and programme.year:
            candidates = {i for i in candidates if not self.movies[i].get("ProductionYear") or self.movies[i]["ProductionYear"] == programme.year}
        if not candidates:
            return None, "année différente"
        # Reject contradictory provider IDs even if a title happens to match.
        valid = set()
        for movie_id in candidates:
            providers = {k.lower(): str(v).lower() for k, v in (self.movies[movie_id].get("ProviderIds") or {}).items()}
            if not any(key in providers and providers[key] != value.lower() for key, value in programme.provider_ids.items()):
                valid.add(movie_id)
        candidates = valid
        if len(candidates) > 1:
            # Several editions are acceptable only when a common ID proves identity.
            same_work = False
            for provider in ("tmdb", "imdb"):
                values = []
                for i in candidates:
                    ids = {k.lower(): str(v).lower() for k, v in (self.movies[i].get("ProviderIds") or {}).items()}
                    values.append(ids.get(provider))
                if values and all(values) and len(set(values)) == 1:
                    same_work = True
                    break
            if not same_work:
                return None, "titre ambigu"
        if not candidates:
            return None, "identifiants différents"
        chosen = sorted(candidates)[0]
        return Match(programme, self.movies[chosen], method), ""

    def match(self, programme: Programme) -> tuple[Match | None, str]:
        keys = {normalize(t) for t in programme.titles}
        forced = {self.overrides[t] for t in keys if t in self.overrides}
        if forced:
            if len(forced) != 1:
                return None, "correspondances manuelles contradictoires"
            movie_id = next(iter(forced))
            return Match(programme, self.movies[movie_id], "manuel"), ""
        provider_candidates: set[str] = set()
        for key, value in programme.provider_ids.items():
            provider_candidates |= self.by_provider.get((key, value.lower()), set())
        if provider_candidates:
            return self._pick(provider_candidates, programme, "identifiant")
        candidates: set[str] = set()
        for title in keys:
            candidates |= self.by_title.get(title, set())
        return self._pick(candidates, programme, "titre")
