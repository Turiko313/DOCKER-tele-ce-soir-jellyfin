from __future__ import annotations

from dataclasses import dataclass

from .config import ExtensionError
from .guide import Programme
from .titles import clean_title, filename_evidence, normalize, title_forms, title_similarity, title_year


@dataclass(frozen=True)
class Match:
    programme: Programme
    movie: dict
    method: str
    score: float | None = None


def provider_ids(movie: dict) -> dict[str, str]:
    return {str(k).lower(): str(v).lower() for k, v in (movie.get("ProviderIds") or {}).items() if v}


def same_work(movies: list[dict]) -> bool:
    """A shared ID must not conceal another provider's contradictory IDs."""
    if len(movies) <= 1:
        return True
    ids = [provider_ids(movie) for movie in movies]
    for provider in {p for row in ids for p in row}:
        if len({row[provider] for row in ids if provider in row}) > 1:
            return False
    return any(all(row.get(p) for row in ids) and len({row[p] for row in ids}) == 1 for p in ("tmdb", "imdb"))


class Matcher:
    """Identity first; progressively broader title evidence with explicit guards."""

    def __init__(self, movies: list[dict], overrides: dict[str, str] | None = None):
        self.movies = {m["Id"]: dict(m) for m in movies if m.get("Type") == "Movie" and not m.get("IsPlaceHolder") and m.get("LocationType") != "Virtual"}
        self.by_title: dict[str, set[str]] = {}
        self.by_provider: dict[tuple[str, str], set[str]] = {}
        self.aliases: dict[str, set[str]] = {}
        self.filenames: dict[str, tuple[str, int]] = {}
        self.overrides: dict[str, str] = {}
        self._nearby_cache: dict[tuple[str, ...], list[tuple[float, str]]] = {}
        for title, raw_id in (overrides or {}).items():
            movie_id = raw_id.replace("-", "").lower()
            if movie_id not in self.movies:
                raise ExtensionError(f"La correspondance manuelle pour « {title} » ne désigne pas un film disponible.")
            for form in title_forms(title):
                if form in self.overrides and self.overrides[form] != movie_id:
                    raise ExtensionError(f"Correspondances manuelles contradictoires pour « {title} ».")
                self.overrides[form] = movie_id
        for movie_id, movie in self.movies.items():
            titles = {t for t in (movie.get("Name"), movie.get("OriginalTitle")) if isinstance(t, str) and t.strip()}
            for title in titles:
                for form in title_forms(title):
                    self.by_title.setdefault(form, set()).add(movie_id)
            ids = provider_ids(movie)
            path = movie.get("Path")
            if isinstance(path, str) and path:
                file_title, file_year, file_ids = filename_evidence(path)
                consistent = not any(p in ids and ids[p] != value for p, value in file_ids.items())
                if consistent:
                    ids.update(file_ids)
                    if file_title and file_year and (not movie.get("ProductionYear") or movie["ProductionYear"] == file_year):
                        self.filenames[movie_id] = file_title, file_year
                        if not movie.get("ProductionYear"):
                            movie["ProductionYear"] = file_year
            movie["ProviderIds"] = ids
            embedded_years = {title_year(t) for t in titles} - {None}
            if not movie.get("ProductionYear") and len(embedded_years) == 1:
                movie["ProductionYear"] = next(iter(embedded_years))
            self.aliases[movie_id] = titles
            for provider, value in ids.items():
                self.by_provider.setdefault((provider, value), set()).add(movie_id)

    @staticmethod
    def directors(movie: dict) -> set[str]:
        return {normalize(p["Name"]) for p in movie.get("People") or [] if isinstance(p, dict) and str(p.get("Type", "")).lower() == "director" and isinstance(p.get("Name"), str)}

    def _pick(self, candidates: set[str], programme: Programme, method: str) -> tuple[Match | None, str]:
        if not candidates:
            return None, "absent"
        if method != "identifiant":
            year = programme.year or title_year(programme.title)
            if year:
                exact_year = {i for i in candidates if self.movies[i].get("ProductionYear") == year}
                candidates = exact_year or {i for i in candidates if not self.movies[i].get("ProductionYear")}
                if not candidates:
                    return None, "année différente"
        expected_ids = {str(k).lower(): str(v).lower() for k, v in programme.provider_ids.items()}
        candidates = {i for i in candidates if not any(p in provider_ids(self.movies[i]) and provider_ids(self.movies[i])[p] != value for p, value in expected_ids.items())}
        if not candidates:
            return None, "identifiants différents"
        if programme.directors:
            directors = {normalize(d) for d in programme.directors}
            verified = {i for i in candidates if self.directors(self.movies[i]) & directors}
            candidates = verified or {i for i in candidates if not self.directors(self.movies[i])}
            if not candidates:
                return None, "réalisateur différent"
        if not same_work([self.movies[i] for i in candidates]):
            return None, "titre ambigu"
        return Match(programme, self.movies[sorted(candidates)[0]], method), ""

    def match_identifiers(self, programme: Programme) -> tuple[Match | None, str]:
        candidates: set[str] = set()
        for key, value in programme.provider_ids.items():
            candidates |= self.by_provider.get((key.lower(), str(value).lower()), set())
        return self._pick(candidates, programme, "identifiant")

    def match(self, programme: Programme) -> tuple[Match | None, str]:
        keys = {form for title in programme.titles for form in title_forms(title)}
        forced = {self.overrides[t] for t in keys if t in self.overrides}
        if forced:
            if len(forced) != 1:
                return None, "correspondances manuelles contradictoires"
            return Match(programme, self.movies[next(iter(forced))], "manuel"), ""
        if programme.provider_ids:
            match, reason = self.match_identifiers(programme)
            if match or reason != "absent":
                return match, reason
        candidates = set().union(*(self.by_title.get(t, set()) for t in keys)) if keys else set()
        match, reason = self._pick(candidates, programme, "titre")
        if match or reason != "absent":
            return match, reason
        year = programme.year or title_year(programme.title)
        if year:
            files = {i for i, (title, file_year) in self.filenames.items() if file_year == year and keys & title_forms(title)}
            return self._pick(files, programme, "nom de fichier + année")
        return None, reason

    def _nearby(self, programme: Programme) -> list[tuple[float, str]]:
        cache_key = tuple(programme.titles)
        if cache_key in self._nearby_cache:
            return self._nearby_cache[cache_key]
        ranked = []
        for movie_id, aliases in self.aliases.items():
            titles = set(aliases)
            if movie_id in self.filenames:
                titles.add(self.filenames[movie_id][0])
            score = max((title_similarity(tv, local) for tv in programme.titles for local in titles), default=0.0)
            if score >= 0.65:
                ranked.append((score, movie_id))
        ranked.sort(key=lambda row: (-row[0], row[1]))
        self._nearby_cache[cache_key] = ranked
        return ranked

    def match_approximate(self, programme: Programme) -> tuple[Match | None, str]:
        year = programme.year or title_year(programme.title)
        if not year or programme.provider_ids:
            return None, "preuves insuffisantes"
        candidates = [(score, i) for score, i in self._nearby(programme) if self.movies[i].get("ProductionYear") == year]
        if not candidates or candidates[0][0] < 0.94:
            return None, "absent"
        best = candidates[0][0]
        title_length = len(normalize(clean_title(programme.title)))
        if title_length < 8 or (best < 1.0 and title_length < 16):
            return None, "preuves insuffisantes"
        close = {i for score, i in candidates if best - score < 0.06}
        match, reason = self._pick(close, programme, "titre proche + année")
        return (Match(programme, match.movie, match.method, round(best, 4)), "") if match else (None, reason)

    def suggestions(self, programme: Programme, limit: int = 3) -> list[dict]:
        return [{"jellyfin_id": i, "title": self.movies[i]["Name"], "year": self.movies[i].get("ProductionYear"), "title_similarity": round(score, 4)}
                for score, i in self._nearby(programme) if score >= 0.8][:limit]
