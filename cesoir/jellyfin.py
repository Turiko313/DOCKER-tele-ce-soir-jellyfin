from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from .config import Config, ExtensionError, atomic_json
from . import __version__


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ExtensionError("Jellyfin redirige la requête : utilise son adresse finale dans JELLYFIN_URL.")


def item_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", value.replace("-", "")):
        raise ExtensionError("Jellyfin a retourné un identifiant d'élément invalide.")
    return value.replace("-", "").lower()


class Jellyfin:
    def __init__(self, config: Config):
        self.config = config
        self.opener = urllib.request.build_opener(NoRedirects())
        self.created = False

    def request(self, method: str, path: str, **query):
        url = self.config.jellyfin_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        auth = f'MediaBrowser Client="CeSoirJellyfin", Device="Docker", DeviceId="ce-soir-jellyfin", Version="{__version__}", Token="{self.config.api_key}"'
        request = urllib.request.Request(url, method=method, headers={"Authorization": auth, "Accept": "application/json"})
        try:
            with self.opener.open(request, timeout=30) as response:
                data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                raise ExtensionError("Réponse Jellyfin trop volumineuse.")
            return json.loads(data) if data else None
        except urllib.error.HTTPError as error:
            hints = {401: "vérifie la clé API", 403: "la clé ne permet pas de gérer les collections", 404: "vérifie l'adresse Jellyfin et son éventuel préfixe /jellyfin"}
            raise ExtensionError(f"Jellyfin : HTTP {error.code} sur {path} ({hints.get(error.code, 'consulte les journaux du serveur')}).") from None
        except (OSError, ValueError) as error:
            # Never include headers, API keys or a full URL in a diagnostic.
            raise ExtensionError(f"Connexion Jellyfin impossible sur {path} ({type(error).__name__}).") from None

    def items(self, **query) -> list[dict]:
        found: list[dict] = []
        seen: set[str] = set()
        total = None
        for _ in range(10000):
            page = self.request("GET", "/Items", **query, StartIndex=len(found), Limit=200, EnableTotalRecordCount="true", EnableImages="false", EnableUserData="false")
            if not isinstance(page, dict) or not isinstance(page.get("Items"), list) or type(page.get("TotalRecordCount")) is not int:
                raise ExtensionError("Réponse de la médiathèque Jellyfin inattendue.")
            count = page["TotalRecordCount"]
            if count < 0 or (total is not None and count != total):
                raise ExtensionError("La médiathèque a changé pendant la lecture ; nouvelle tentative au prochain passage.")
            total = count
            batch = page["Items"]
            if not batch and len(found) < total:
                raise ExtensionError("Lecture incomplète de la médiathèque ; collection conservée.")
            for movie in batch:
                if not isinstance(movie, dict):
                    raise ExtensionError("Élément Jellyfin invalide.")
                movie["Id"] = item_id(movie.get("Id"))
                if movie["Id"] in seen:
                    raise ExtensionError("Pagination instable de Jellyfin ; collection conservée.")
                seen.add(movie["Id"])
                found.append(movie)
            if len(found) == total:
                return found
            if len(found) > total:
                raise ExtensionError("Nombre d'éléments Jellyfin incohérent.")
        raise ExtensionError("La pagination Jellyfin a dépassé la limite de sécurité.")

    def movies(self) -> list[dict]:
        movies = self.items(IncludeItemTypes="Movie", Recursive="true", IsPlaceHolder="false", ExcludeLocationTypes="Virtual", Fields="OriginalTitle,ProviderIds", SortBy="SortName", SortOrder="Ascending")
        if not movies:
            raise ExtensionError("Aucun film trouvé dans Jellyfin. Vérifie la médiathèque et l'adresse du serveur.")
        return movies

    def server_identity(self) -> tuple[str, str]:
        info = self.request("GET", "/System/Info/Public")
        if not isinstance(info, dict) or not info.get("Id"):
            raise ExtensionError("Impossible d'identifier le serveur Jellyfin.")
        return str(info["Id"]), str(info.get("Version", "inconnue"))

    def _state(self) -> dict:
        path = self.config.data_dir / "state.json"
        if not path.exists():
            return {}
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError()
            return state
        except (OSError, ValueError):
            raise ExtensionError("state.json est illisible : restaure ce fichier ou renseigne explicitement collection_id.") from None

    def _validate_collection(self, collection_id: str) -> None:
        result = self.items(Ids=collection_id, Recursive="true")
        if len(result) != 1 or result[0].get("Type") != "BoxSet":
            raise ExtensionError("La collection mémorisée est absente ou invalide. Renseigne collection_id pour en désigner une autre.")
        if result[0].get("Name") != self.config.collection_name:
            raise ExtensionError("Le nom de la collection diffère de collection_name. Ajuste config.json avant de poursuivre.")

    def collection(self, server_id: str, desired: list[str], dry_run: bool) -> str | None:
        state = self._state() if not self.config.collection_id else {}
        if state and state.get("server_id") != server_id:
            raise ExtensionError("Le volume de données appartient à un autre serveur Jellyfin. Utilise un volume distinct.")
        collection_id = self.config.collection_id or state.get("collection_id")
        if collection_id:
            collection_id = item_id(collection_id)
            self._validate_collection(collection_id)
            if not dry_run:
                atomic_json(self.config.data_dir / "state.json", {"server_id": server_id, "collection_id": collection_id})
            return collection_id
        existing = self.items(IncludeItemTypes="BoxSet", Recursive="true")
        if any(c.get("Name") == self.config.collection_name for c in existing):
            raise ExtensionError("Une collection de ce nom existe déjà. Pour la confier à l'extension, renseigne explicitement son collection_id dans config.json.")
        if dry_run or not desired:
            return None
        created = self.request("POST", "/Collections", Name=self.config.collection_name, Ids=",".join(desired[:50]), IsLocked="false")
        if not isinstance(created, dict):
            raise ExtensionError("Jellyfin n'a pas confirmé la création de la collection.")
        collection_id = item_id(created.get("Id"))
        atomic_json(self.config.data_dir / "state.json", {"server_id": server_id, "collection_id": collection_id})
        self.created = True
        return collection_id

    def sync(self, collection_id: str | None, desired: list[str], dry_run: bool) -> dict:
        if not collection_id:
            return {"added": len(desired), "removed": 0, "created": bool(desired), "collection_id": None}
        current = {m["Id"] for m in self.items(ParentId=collection_id, Recursive="false")}
        desired_set = {item_id(i) for i in desired}
        added, removed = sorted(desired_set - current), sorted(current - desired_set)
        if not dry_run:
            # Add first. If this fails, yesterday's selection has not been removed.
            for offset in range(0, len(added), 50):
                self.request("POST", f"/Collections/{collection_id}/Items", Ids=",".join(added[offset:offset + 50]))
            for offset in range(0, len(removed), 50):
                self.request("DELETE", f"/Collections/{collection_id}/Items", Ids=",".join(removed[offset:offset + 50]))
            actual = {m["Id"] for m in self.items(ParentId=collection_id, Recursive="false")}
            if actual != desired_set:
                raise ExtensionError("Jellyfin n'a pas encore confirmé le contenu attendu de la collection ; nouvelle tentative au prochain passage.")
        return {"added": len(desired_set) if self.created else len(added), "removed": len(removed), "created": self.created, "collection_id": collection_id}
