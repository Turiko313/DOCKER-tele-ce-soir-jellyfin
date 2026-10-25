from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


class ExtensionError(Exception):
    """An actionable error, safe to include in a local diagnostic."""


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


@dataclass(frozen=True)
class Config:
    jellyfin_url: str
    api_key: str = field(repr=False)
    data_dir: Path = Path("/data")
    guide_url: str = "https://xmltvfr.fr/xmltv/xmltv_tnt.xml.gz"
    timezone: str = "Europe/Paris"
    start: str = "20:00"
    end: str = "02:00"
    channels: tuple[str, ...] = ()
    collection_name: str = "Films à la télé ce soir"
    collection_id: str = ""
    interval_seconds: int = 900
    guide_refresh_hours: int = 12
    guide_max_age_hours: int = 48
    include_tv_movies: bool = True
    metadata_lookup: bool = True
    title_overrides: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls) -> Config:
        path = Path(os.environ.get("CONFIG_FILE", "/app/config.json"))
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(raw, dict):
                raise ValueError("le fichier doit contenir un objet JSON")
            raw["jellyfin_url"] = os.environ.get("JELLYFIN_URL", "").strip().rstrip("/")
            secret_path = os.environ.get("JELLYFIN_API_KEY_FILE", "/run/secrets/jellyfin_api_key")
            raw["api_key"] = Path(secret_path).read_text(encoding="utf-8-sig").strip()
            raw["data_dir"] = Path(os.environ.get("DATA_DIR", "/data"))
            if "METADATA_LOOKUP" in os.environ:
                value = os.environ["METADATA_LOOKUP"].strip().lower()
                if value not in {"true", "false"}:
                    raise ValueError("METADATA_LOOKUP doit être true ou false")
                raw["metadata_lookup"] = value == "true"
            if "channels" in raw:
                if not isinstance(raw["channels"], list) or not all(isinstance(c, str) for c in raw["channels"]):
                    raise ValueError("channels doit être une liste d'identifiants XMLTV")
                raw["channels"] = tuple(raw["channels"])
            config = cls(**raw)
            config.validate()
            return config
        except (OSError, ValueError, TypeError) as error:
            raise ExtensionError(f"Configuration invalide : {error}") from None

    def validate(self) -> None:
        for value, label, schemes in (
            (self.jellyfin_url, "JELLYFIN_URL", {"http", "https"}),
            (self.guide_url, "guide_url", {"https"}),
        ):
            parts = urlsplit(value)
            if parts.scheme not in schemes or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
                raise ValueError(f"{label} doit être une URL sans identifiant, paramètre ni fragment")
        if not re.fullmatch(r"[a-zA-Z0-9._~-]{16,256}", self.api_key) or "COLLER" in self.api_key.upper():
            raise ValueError("renseigne ta clé API Jellyfin dans jellyfin-api-key.txt")
        for value in (self.start, self.end):
            if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
                raise ValueError("les horaires start et end doivent être au format HH:MM")
        if self.start == self.end:
            raise ValueError("start et end doivent être différents")
        ZoneInfo(self.timezone)
        if not isinstance(self.collection_name, str) or not self.collection_name.strip():
            raise ValueError("collection_name ne peut pas être vide")
        if self.collection_id and not re.fullmatch(r"[a-fA-F0-9-]{32,36}", self.collection_id):
            raise ValueError("collection_id doit être un identifiant Jellyfin")
        if type(self.interval_seconds) is not int or self.interval_seconds < 60:
            raise ValueError("interval_seconds doit être un entier d'au moins 60 secondes")
        if type(self.guide_refresh_hours) is not int or self.guide_refresh_hours < 1:
            raise ValueError("guide_refresh_hours doit être un entier d'au moins 1 heure")
        if type(self.guide_max_age_hours) is not int or self.guide_max_age_hours < self.guide_refresh_hours:
            raise ValueError("guide_max_age_hours doit être supérieur ou égal à guide_refresh_hours")
        if type(self.include_tv_movies) is not bool:
            raise ValueError("include_tv_movies doit être true ou false")
        if type(self.metadata_lookup) is not bool:
            raise ValueError("metadata_lookup doit être true ou false")
        if not isinstance(self.title_overrides, dict) or not all(
            isinstance(k, str) and k.strip() and isinstance(v, str) and re.fullmatch(r"[a-fA-F0-9-]{32,36}", v)
            for k, v in self.title_overrides.items()
        ):
            raise ValueError("title_overrides doit associer des titres TV à des identifiants de films Jellyfin")


def evening_window(now: datetime, config: Config) -> tuple[datetime, datetime]:
    """After midnight, retain the preceding evening until its configured end."""
    zone = ZoneInfo(config.timezone)
    local = now.astimezone(zone)
    start_time, end_time = time.fromisoformat(config.start), time.fromisoformat(config.end)
    overnight = end_time < start_time
    day = local.date()
    if overnight and local.time().replace(tzinfo=None) < end_time:
        day -= timedelta(days=1)
    start = datetime.combine(day, start_time, zone)
    end = datetime.combine(day + timedelta(days=int(overnight)), end_time, zone)
    return start, end
