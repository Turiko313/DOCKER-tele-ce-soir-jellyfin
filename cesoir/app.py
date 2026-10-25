from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
import signal
import sys
import threading

from .config import Config, ExtensionError, atomic_json, evening_window
from .guide import GuideCache
from .jellyfin import Jellyfin
from .matching import Matcher
from .locking import instance_lock

LOG = logging.getLogger(__name__)


def run_once(config: Config, dry_run: bool = False, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    start, end = evening_window(now, config)
    guide, used_fallback = GuideCache(config).load(now, start, end)
    client = Jellyfin(config)
    server_id, version = client.server_identity()
    movies = client.movies()
    matcher = Matcher(movies, config.title_overrides)
    matches, skipped = [], []
    for programme in guide.movies:
        match, reason = matcher.match(programme)
        if match:
            matches.append(match)
        else:
            skipped.append({"title": programme.title, "channel": programme.channel_name, "reason": reason})
    desired = list(dict.fromkeys(m.movie["Id"] for m in matches))
    collection_id = client.collection(server_id, desired, dry_run)
    changes = client.sync(collection_id, desired, dry_run)
    report = {
        "updated_at": now.isoformat(),
        "evening": start.date().isoformat(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "jellyfin_version": version,
        "dry_run": dry_run,
        "cached_guide_fallback": used_fallback,
        "library_movie_count": len(movies),
        "guide_movie_count": len(guide.movies),
        "covered_channel_count": len(guide.covered_channels),
        "collection_movie_count": len(desired),
        "changes": changes,
        "broadcasts": [
            {"title": m.movie["Name"], "jellyfin_id": m.movie["Id"], "tv_title": m.programme.title,
             "channel": m.programme.channel_name, "channel_id": m.programme.channel_id,
             "start": m.programme.start.astimezone(start.tzinfo).isoformat(), "match_method": m.method}
            for m in matches
        ],
        "skipped": skipped,
    }
    atomic_json(config.data_dir / ("preview.json" if dry_run else "report.json"), report)
    prefix = "Simulation" if dry_run else "Collection actualisée"
    LOG.info("%s : soirée du %s, %d film(s) sur %d diffusion(s) de films, %d ajout(s), %d retrait(s).", prefix, report["evening"], len(desired), len(guide.movies), changes["added"], changes["removed"])
    for match in matches:
        LOG.info("  %s — %s — %s", match.programme.start.astimezone(start.tzinfo).strftime("%H:%M"), match.programme.channel_name, match.movie["Name"])
    if skipped:
        LOG.info("%d diffusion(s) sans correspondance certaine ; détails dans %s.", len(skipped), "preview.json" if dry_run else "report.json")
    return report


def healthcheck(config: Config) -> int:
    try:
        status = json.loads((config.data_dir / "health.json").read_text(encoding="utf-8"))
        age = datetime.now(timezone.utc).timestamp() - float(status["checked_at"])
        return 0 if status["ok"] and age < config.interval_seconds * 3 + 120 else 1
    except (OSError, ValueError, KeyError, TypeError):
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Films de ta médiathèque diffusés à la télé ce soir.")
    parser.add_argument("--once", action="store_true", help="Effectue une seule synchronisation.")
    parser.add_argument("--dry-run", action="store_true", help="Simule une synchronisation sans écrire dans Jellyfin.")
    parser.add_argument("--healthcheck", action="store_true", help="Vérifie le dernier passage du service.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    try:
        config = Config.load()
    except (ExtensionError, ValueError, KeyError) as error:
        LOG.error("%s", error)
        return 1
    if args.healthcheck:
        return healthcheck(config)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    try:
        with instance_lock(config.data_dir):
            while not stop.is_set():
                success = False
                try:
                    run_once(config, args.dry_run)
                    success = True
                except Exception as error:
                    # Redact the secret even for unexpected exception messages.
                    message = str(error).replace(config.api_key, "[clé masquée]")
                    LOG.error("%s : %s", type(error).__name__, message)
                    LOG.error("La dernière sélection confirmée est conservée si la lecture du guide ou de la médiathèque a échoué.")
                if not args.dry_run:
                    atomic_json(config.data_dir / "health.json", {"ok": success, "checked_at": datetime.now(timezone.utc).timestamp()})
                if args.once or args.dry_run:
                    return 0 if success else 1
                stop.wait(config.interval_seconds)
    except ExtensionError as error:
        LOG.error("%s", error)
        return 1
    return 0
