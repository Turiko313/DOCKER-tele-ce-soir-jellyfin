from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import logging
from pathlib import Path

from . import __version__
from .config import Config, atomic_json

LOG = logging.getLogger(__name__)

REASONS = {
    "absent": "aucun titre ou identifiant correspondant dans la médiathèque",
    "année différente": "titre trouvé, mais année différente du programme TV",
    "titre ambigu": "plusieurs films possibles, sans information pour les départager",
    "identifiants différents": "titre trouvé, mais identifiants IMDb/TMDb contradictoires",
    "correspondances manuelles contradictoires": "plusieurs correspondances manuelles contradictoires",
}


def read_report(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def log_startup(config: Config, mode: str, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    path = config.data_dir / "service.json"
    previous = read_report(path)
    LOG.info("Films à la télé ce soir — version %s — %s", __version__, mode)
    if mode == "service continu":
        LOG.info("Contrôle toutes les %d secondes ; plage TV %s–%s (%s).", config.interval_seconds, config.start, config.end, config.timezone)
        try:
            age = (now - datetime.fromisoformat(previous["started_at"])).total_seconds()
        except (KeyError, ValueError, TypeError):
            age = -1
        if previous.get("mode") == mode and 0 <= age < min(config.interval_seconds, 120):
            LOG.info("Nouveau lancement %d secondes après le précédent. Ce lancement est distinct du contrôle périodique ; vérifier les relances OMV/Watchtower si cela se répète.", int(age))
        atomic_json(path, {"started_at": now.isoformat(), "version": __version__, "mode": mode})


def _schedule(stamp: str) -> str:
    # Include the date so broadcasts after midnight cannot be mistaken for today.
    return datetime.fromisoformat(stamp).strftime("%d/%m %H:%M")


def log_report(report: dict, previous: dict, path: Path, force_details: bool = False) -> None:
    changes = report["changes"]
    changed = changes["created"] or changes["added"] or changes["removed"]
    status = "Simulation" if report["dry_run"] else ("Collection actualisée" if changed else "Collection inchangée")
    counts = Counter(p["reason"] for p in report["skipped"])
    LOG.info("%s — soirée du %s : %d film(s) disponible(s), %d diffusion(s) retenue(s) sur %d ; %d écartée(s) ; ajouts : %d, retraits : %d.",
             status, report["evening"], report["collection_movie_count"], report["matched_broadcast_count"],
             report["guide_movie_count"], len(report["skipped"]), changes["added"], changes["removed"])
    keys = ("evening", "start", "end", "broadcasts", "skipped", "library_movie_count", "covered_channel_count", "cached_guide_fallback")
    details = force_details or changed or report["dry_run"] or any(report.get(k) != previous.get(k) for k in keys)
    if not details:
        return
    LOG.info("Médiathèque : %d film(s) disponible(s). Guide : %d chaîne(s) couverte(s). Horaires : %s.", report["library_movie_count"], report["covered_channel_count"], report["timezone"])
    if report["cached_guide_fallback"]:
        LOG.warning("Programme lu dans le cache de secours : le téléchargement du guide a échoué.")
    for broadcast in report["broadcasts"]:
        year = f" ({broadcast['year']})" if broadcast.get("year") else ""
        LOG.info("  RETENU | %s | %s | %s%s", _schedule(broadcast["start"]), broadcast["channel"], broadcast["title"], year)
    for skipped in report["skipped"]:
        year = f" ({skipped['year']})" if skipped.get("year") else ""
        LOG.info("  ÉCARTÉ | %s | %s | %s%s — %s", _schedule(skipped["start"]), skipped["channel"], skipped["title"], year, REASONS.get(skipped["reason"], skipped["reason"]))
    if counts:
        LOG.info("Motifs des exclusions : %s.", "; ".join(f"{count} × {REASONS.get(reason, reason)}" for reason, count in sorted(counts.items())))
    LOG.info("Rapport complet : %s. Les prochains contrôles sans changement afficheront uniquement le bilan.", path)
