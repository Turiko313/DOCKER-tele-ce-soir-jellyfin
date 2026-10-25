from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET
import zipfile

from cesoir.app import run_once
from cesoir.config import Config, ExtensionError, atomic_json, evening_window
from cesoir.guide import GuideCache, Programme, normalize, parse_guide, xmltv_datetime
from cesoir.jellyfin import Jellyfin
from cesoir.locking import instance_lock
from cesoir.matching import Matcher

A, B, C = "a" * 32, "b" * 32, "c" * 32
NOW = datetime(2026, 10, 25, 14, 0, tzinfo=timezone.utc)
KEY = "unittest000000000000000000000000"
TEMP_ROOT = Path(os.environ.get("TEST_TEMP_DIR", str(Path(__file__).resolve().parent / "temporary")))
TEMP_ROOT.mkdir(parents=True, exist_ok=True)


def config(data: Path, **kwargs) -> Config:
    return Config("http://127.0.0.1:8096", KEY, data_dir=data, **kwargs)


def movie(mid=A, title="Le Cinéma des étoiles", year=2001, **kwargs):
    return {"Id": mid, "Name": title, "ProductionYear": year, "Type": "Movie", **kwargs}


def programme(title="Le Cinéma des étoiles", year=2001, providers=None):
    return Programme(title, (title,), "TF1.fr", "TF1", xmltv_datetime("20261025211000 +0100"), year, providers or {})


def guide_xml(title="Le Cinéma des étoiles", category="Film", day="20261025", extra=""):
    title = title.replace("&", "&amp;")
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE tv SYSTEM "xmltv.dtd">
<tv><channel id="TF1.fr"><display-name>TF1</display-name></channel>
<programme start="{day}211000 +0100" stop="{day}231000 +0100" channel="TF1.fr">
<title lang="fr">{title}</title><date>2001</date><category>{category}</category>{extra}</programme></tv>'''.encode()


class TimeTests(unittest.TestCase):
    def test_after_midnight_keeps_previous_evening(self):
        cfg = config(Path("unused"))
        start, end = evening_window(datetime(2026, 10, 26, 0, 30, tzinfo=timezone.utc), cfg)
        self.assertEqual(start.isoformat(), "2026-10-25T20:00:00+01:00")
        self.assertEqual(end.isoformat(), "2026-10-26T02:00:00+01:00")

    def test_end_switches_to_next_evening(self):
        start, _ = evening_window(datetime(2026, 10, 26, 1, 0, tzinfo=timezone.utc), config(Path("unused")))
        self.assertEqual(start.date().isoformat(), "2026-10-26")

    def test_summer_and_winter_offsets(self):
        cfg = config(Path("unused"))
        self.assertEqual(evening_window(datetime(2026, 7, 1, tzinfo=timezone.utc), cfg)[0].utcoffset().total_seconds(), 7200)
        self.assertEqual(evening_window(NOW, cfg)[0].utcoffset().total_seconds(), 3600)

    def test_xmltv_utc_default_and_explicit_offsets(self):
        self.assertEqual(xmltv_datetime("202610252100 +0200"), xmltv_datetime("20261025190000 +0000"))
        self.assertEqual(xmltv_datetime("20261025210000").utcoffset().total_seconds(), 0)
        with self.assertRaises(ValueError):
            xmltv_datetime("20261025210000 +0199")


class GuideTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.cfg = config(Path(self.temporary.name))
        self.path = self.cfg.data_dir / "source.xml"
        self.start, self.end = evening_window(NOW, self.cfg)

    def parse(self, xml):
        self.path.write_bytes(xml)
        return parse_guide(self.path, self.cfg, self.start, self.end)

    def test_movie_categories_and_series_exclusion(self):
        self.assertEqual(len(self.parse(guide_xml(category="Cinéma")).movies), 1)
        self.assertEqual(len(self.parse(guide_xml(category="Téléfilm dramatique")).movies), 1)
        self.assertEqual(len(self.parse(guide_xml(category="Série TV")).movies), 0)
        self.assertEqual(len(self.parse(guide_xml(category="Magazine de cinéma")).movies), 0)
        self.assertEqual(len(self.parse(guide_xml(extra='<episode-num system="xmltv_ns">1.2.</episode-num>')).movies), 0)
        self.cfg = replace(self.cfg, include_tv_movies=False)
        self.assertEqual(len(self.parse(guide_xml(category="Téléfilm")).movies), 0)

    def test_empty_valid_evening_is_distinct_from_missing_guide(self):
        guide = self.parse(guide_xml(category="Série"))
        self.assertEqual(guide.slot_count, 1)
        self.assertFalse(guide.movies)
        with self.assertRaises(ExtensionError):
            self.parse(guide_xml(day="20261024"))

    def test_invalid_or_unknown_channels_rejected(self):
        self.cfg = replace(self.cfg, channels=("Wrong.fr",))
        with self.assertRaisesRegex(ExtensionError, "inconnus"):
            self.parse(guide_xml())
        self.cfg = replace(self.cfg, channels=())
        with self.assertRaisesRegex(ExtensionError, "horaire"):
            self.parse(guide_xml().replace(b"20261025211000", b"not-a-time"))

    def test_bounds_include_start_exclude_end_and_include_second_half(self):
        xml = guide_xml().decode().replace("</tv>", '''
<programme start="20261026013000 +0100" channel="TF1.fr"><title>Suite</title><category>Film</category></programme>
<programme start="20261026020000 +0100" channel="TF1.fr"><title>Trop tard</title><category>Film</category></programme>
<programme start="20261025200000 +0100" channel="TF1.fr"><title>Début</title><category>Film</category></programme>
</tv>''')
        guide = self.parse(xml.encode())
        self.assertEqual([p.title for p in guide.movies], ["Début", "Le Cinéma des étoiles", "Suite"])

    def test_external_ids(self):
        guide = self.parse(guide_xml(extra='<url>https://www.imdb.com/title/tt1234567/</url><url>https://www.themoviedb.org/movie/123</url>'))
        self.assertEqual(guide.movies[0].provider_ids, {"imdb": "tt1234567", "tmdb": "123"})

    def test_gzip_zip_and_plain_downloads(self):
        xml = guide_xml()
        zipped = io.BytesIO()
        with zipfile.ZipFile(zipped, "w") as archive:
            archive.writestr("guide.xml", xml)
        cache = GuideCache(self.cfg)
        for raw in (xml, gzip.compress(xml), zipped.getvalue()):
            response = io.BytesIO(raw)
            class Opener:
                def open(self, *_args, **_kwargs):
                    return response
            with patch("cesoir.guide.urllib.request.build_opener", return_value=Opener()):
                cache._download(self.path)
            self.assertEqual(self.path.read_bytes(), xml)

    def test_unsafe_xml_and_oversized_xml_rejected(self):
        with self.assertRaises(ExtensionError):
            GuideCache._copy_xml(io.BytesIO(b'<!DOCTYPE tv [<!ENTITY x "test">]><tv/>'), self.path)
        with patch("cesoir.guide.MAX_XML", 10):
            with self.assertRaises(ExtensionError):
                GuideCache._copy_xml(io.BytesIO(guide_xml()), self.path)

    def test_bad_refresh_preserves_valid_cache(self):
        cache = GuideCache(self.cfg)
        cache.path.write_bytes(guide_xml())
        atomic_json(cache.meta, {"url": self.cfg.guide_url, "downloaded_at": NOW.timestamp() - 13 * 3600})
        def invalid_download(destination):
            destination.write_bytes(b"<tv/>")
        with patch.object(cache, "_download", side_effect=invalid_download):
            result, fallback = cache.load(NOW, self.start, self.end)
        self.assertTrue(fallback)
        self.assertEqual(len(result.movies), 1)
        self.assertEqual(cache.path.read_bytes(), guide_xml())

    def test_old_or_changed_source_cache_cannot_be_used(self):
        cache = GuideCache(self.cfg)
        cache.path.write_bytes(guide_xml())
        for url, age in ((self.cfg.guide_url, 49), ("https://another.invalid/guide.gz", 1)):
            atomic_json(cache.meta, {"url": url, "downloaded_at": NOW.timestamp() - age * 3600})
            with patch.object(cache, "_download", side_effect=OSError("offline")):
                with self.assertRaises(ExtensionError):
                    cache.load(NOW, self.start, self.end)


class MatchingTests(unittest.TestCase):
    def test_accents_punctuation_original_title(self):
        match, _ = Matcher([movie(OriginalTitle="A Night's Tale")]).match(programme("LE CINEMA DES ETOILES"))
        self.assertEqual(match.movie["Id"], A)
        match, _ = Matcher([movie(OriginalTitle="A Night's Tale")]).match(programme("A Night’s Tale"))
        self.assertEqual(match.movie["Id"], A)
        self.assertEqual(normalize("L’Œuvre"), normalize("L'Oeuvre"))

    def test_no_fuzzy_matching(self):
        match, _ = Matcher([movie(title="La route des étoiles 2")]).match(programme("La route des étoiles"))
        self.assertIsNone(match)

    def test_remakes_require_unambiguous_year(self):
        matcher = Matcher([movie(year=2001), movie(B, year=2020)])
        match, _ = matcher.match(programme(year=2020))
        self.assertEqual(match.movie["Id"], B)
        match, reason = matcher.match(programme(year=None))
        self.assertIsNone(match)
        self.assertIn("ambigu", reason)
        self.assertIsNone(matcher.match(programme(year=1990))[0])

    def test_provider_id_and_conflicts(self):
        matcher = Matcher([movie(ProviderIds={"Tmdb": "42"})])
        match, _ = matcher.match(programme("Titre traduit différent", providers={"tmdb": "42"}))
        self.assertEqual(match.method, "identifiant")
        self.assertIsNone(matcher.match(programme(providers={"tmdb": "99"}))[0])

    def test_duplicate_editions_require_common_provider_id(self):
        matcher = Matcher([movie(ProviderIds={"Imdb": "tt1234567"}), movie(B, ProviderIds={"Imdb": "tt1234567"})])
        self.assertIsNotNone(matcher.match(programme())[0])
        matcher = Matcher([movie(), movie(B)])
        self.assertIsNone(matcher.match(programme())[0])

    def test_manual_override_and_unavailable_movie(self):
        matcher = Matcher([movie()], {"Titre TV alternatif": A})
        match, _ = matcher.match(programme("Titre TV alternatif"))
        self.assertEqual(match.method, "manuel")
        with self.assertRaises(ExtensionError):
            Matcher([movie()], {"Titre": B})
        self.assertIsNone(Matcher([movie(IsPlaceHolder=True)]).match(programme())[0])


class FakeServer:
    def __init__(self):
        self.movies = [movie()]
        self.collections = {}
        self.mutations = []
        self.requests = []
        self.fail_add = False
        self.bad_page = False
        self.redirect = False
        self.collapse_collection_items = False
        self.collapse_library_items = False
        self.ignore_add = False
        self.ignore_remove = False
        self.delay_add_reads = 0
        self.pending_additions = []
        self.pending_reads = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, status, payload=None, location=None):
                self.send_response(status)
                if location:
                    self.send_header("Location", location)
                if payload is not None:
                    self.send_header("Content-Type", "application/json")
                self.end_headers()
                if payload is not None:
                    self.wfile.write(json.dumps(payload).encode())

            def dispatch(self):
                parts = urlsplit(self.path)
                path = parts.path.removeprefix("/jellyfin")
                query = {k.lower(): v[0] for k, v in parse_qs(parts.query).items()}
                owner.requests.append((self.command, self.path, self.headers.get("Authorization", "")))
                if owner.redirect:
                    self.respond(302, location="http://127.0.0.1:1/leak")
                    return
                if f'Token="{KEY}"' not in self.headers.get("Authorization", ""):
                    self.respond(401)
                    return
                if self.command == "GET" and path == "/System/Info/Public":
                    self.respond(200, {"Id": "test-server", "Version": "12.0.0"})
                elif self.command == "GET" and path == "/Items":
                    if "ids" in query:
                        items = [dict(Id=k, Name=v["name"], Type="BoxSet") for k, v in owner.collections.items() if k in query["ids"].split(",")]
                    elif "parentid" in query:
                        collection = owner.collections[query["parentid"]]
                        if owner.pending_additions:
                            if owner.pending_reads:
                                owner.pending_reads -= 1
                            else:
                                collection["items"].extend(i for i in owner.pending_additions if i not in collection["items"])
                                owner.pending_additions = []
                        if query.get("recursive") != "true" and not query.get("userid"):
                            # Reproduce Jellyfin's API-key / linked-child behaviour.
                            items = []
                        elif owner.collapse_collection_items and query.get("collapseboxsetitems") != "false":
                            items = [{"Id": query["parentid"], "Type": "BoxSet"}]
                        else:
                            items = [{"Id": i, "Type": "Movie"} for i in collection["items"]]
                    elif query.get("includeitemtypes") == "BoxSet":
                        items = [dict(Id=k, Name=v["name"], Type="BoxSet") for k, v in owner.collections.items()]
                    else:
                        if owner.collapse_library_items and query.get("collapseboxsetitems") != "false" and owner.collections:
                            items = [{"Id": k, "Name": v["name"], "Type": "BoxSet"} for k, v in owner.collections.items()]
                        else:
                            items = owner.movies
                    total = len(items)
                    offset, limit = int(query.get("startindex", 0)), int(query.get("limit", 200))
                    self.respond(200, {"Items": [] if owner.bad_page else items[offset:offset + limit], "TotalRecordCount": total})
                elif self.command == "POST" and path == "/Collections":
                    owner.mutations.append((self.command, path))
                    owner.collections[C] = {"name": query["name"], "items": query.get("ids", "").split(",") if query.get("ids") else []}
                    self.respond(200, {"Id": C})
                elif path == f"/Collections/{C}/Items" and self.command in {"POST", "DELETE"}:
                    owner.mutations.append((self.command, path))
                    if self.command == "POST" and owner.fail_add:
                        self.respond(500)
                        return
                    ids = query["ids"].split(",")
                    current = owner.collections[C]["items"]
                    if self.command == "POST":
                        if owner.ignore_add:
                            pass
                        elif owner.delay_add_reads:
                            owner.pending_additions.extend(ids)
                            owner.pending_reads = owner.delay_add_reads
                        else:
                            current.extend(i for i in ids if i not in current)
                    elif not owner.ignore_remove:
                        owner.collections[C]["items"] = [i for i in current if i not in ids]
                    self.respond(204)
                else:
                    self.respond(404)

            do_GET = do_POST = do_DELETE = dispatch

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/jellyfin"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.addCleanup(self.temporary.cleanup)
        self.server = FakeServer()
        self.addCleanup(self.server.close)
        self.cfg = replace(config(Path(self.temporary.name)), jellyfin_url=self.server.url)
        self.cfg.validate()

    def feed(self, xml=None):
        xml = guide_xml() if xml is None else xml
        def download(_self, destination):
            destination.write_bytes(xml)
        return patch.object(GuideCache, "_download", download)

    def owned_collection(self, members):
        self.server.collections[C] = {"name": self.cfg.collection_name, "items": list(members)}
        atomic_json(self.cfg.data_dir / "state.json", {"server_id": "test-server", "collection_id": C})

    def test_full_sync_idempotent_auth_and_base_url(self):
        with self.feed():
            report = run_once(self.cfg, now=NOW)
        self.assertTrue(report["changes"]["created"])
        self.assertEqual(report["collection_movie_count"], 1)
        self.assertEqual(self.server.collections[C]["items"], [A])
        self.assertTrue(all("/jellyfin/" in path and KEY not in path for _, path, _ in self.server.requests))
        first_mutations = list(self.server.mutations)
        report = run_once(self.cfg, now=NOW)
        self.assertEqual(self.server.mutations, first_mutations)
        self.assertEqual(report["changes"]["added"], 0)
        self.assertTrue((self.cfg.data_dir / "report.json").exists())

    def test_dry_run_makes_no_jellyfin_writes_or_state(self):
        with self.feed():
            report = run_once(self.cfg, dry_run=True, now=NOW)
        self.assertEqual(report["collection_movie_count"], 1)
        self.assertFalse(self.server.mutations)
        self.assertFalse((self.cfg.data_dir / "state.json").exists())
        self.assertTrue((self.cfg.data_dir / "preview.json").exists())

    def test_existing_unmanaged_collection_not_adopted(self):
        self.server.collections[C] = {"name": self.cfg.collection_name, "items": [B]}
        with self.feed(), self.assertRaisesRegex(ExtensionError, "existe déjà"):
            run_once(self.cfg, now=NOW)
        self.assertFalse(self.server.mutations)

    def test_add_then_remove_only_collection_links(self):
        self.owned_collection([B])
        with self.feed():
            run_once(self.cfg, now=NOW)
        self.assertEqual(self.server.collections[C]["items"], [A])
        self.assertEqual(self.server.mutations, [("POST", f"/Collections/{C}/Items"), ("DELETE", f"/Collections/{C}/Items")])

    def test_failed_add_does_not_remove_previous_selection(self):
        self.owned_collection([B])
        self.server.fail_add = True
        with self.feed(), self.assertRaises(ExtensionError):
            run_once(self.cfg, now=NOW)
        self.assertEqual(self.server.collections[C]["items"], [B])
        self.assertTrue(all(method != "DELETE" for method, _ in self.server.mutations))

    def test_api_key_linked_children_are_read_recursively(self):
        self.owned_collection([A])
        self.assertEqual(Jellyfin(self.cfg).items(ParentId=C, Recursive="false"), [])
        with self.feed():
            report = run_once(self.cfg, now=NOW)
        self.assertEqual(report["collection_movie_count"], 1)
        self.assertFalse(self.server.mutations)

    def test_collection_members_are_not_hidden_behind_a_boxset(self):
        self.owned_collection([A])
        self.server.collapse_collection_items = True
        with self.feed():
            run_once(self.cfg, now=NOW)
        self.assertEqual(self.server.collections[C]["items"], [A])
        self.assertFalse(self.server.mutations)

    def test_library_movies_remain_visible_after_collection_creation(self):
        self.owned_collection([A])
        self.server.collapse_library_items = True
        self.assertEqual([m["Id"] for m in Jellyfin(self.cfg).movies()], [A])

    def test_unconfirmed_add_keeps_previous_selection(self):
        self.owned_collection([B])
        self.server.ignore_add = True
        with self.feed(), patch("cesoir.jellyfin.time.sleep"), self.assertRaisesRegex(ExtensionError, "1 manquant"):
            run_once(self.cfg, now=NOW)
        self.assertEqual(self.server.collections[C]["items"], [B])
        self.assertTrue(all(method != "DELETE" for method, _ in self.server.mutations))

    def test_delayed_add_is_confirmed_before_removing_previous_films(self):
        self.owned_collection([B])
        self.server.delay_add_reads = 2
        with self.feed(), patch("cesoir.jellyfin.time.sleep"):
            run_once(self.cfg, now=NOW)
        self.assertEqual(self.server.collections[C]["items"], [A])
        self.assertEqual(self.server.mutations[-1], ("DELETE", f"/Collections/{C}/Items"))

    def test_unconfirmed_removal_reports_actual_difference(self):
        self.owned_collection([A, B])
        self.server.ignore_remove = True
        with self.feed(), patch("cesoir.jellyfin.time.sleep"), self.assertRaisesRegex(ExtensionError, "0 manquant.*1 inattendu"):
            run_once(self.cfg, now=NOW)
        self.assertEqual(set(self.server.collections[C]["items"]), {A, B})

    def test_incomplete_library_or_missing_guide_never_clears(self):
        self.owned_collection([B])
        self.server.bad_page = True
        with self.feed(), self.assertRaises(ExtensionError):
            run_once(self.cfg, now=NOW)
        self.assertFalse(self.server.mutations)
        (self.cfg.data_dir / "guide-cache.json").unlink(missing_ok=True)
        self.server.bad_page = False
        with self.feed(guide_xml(day="20261024")), self.assertRaises(ExtensionError):
            run_once(self.cfg, now=NOW)
        self.assertEqual(self.server.collections[C]["items"], [B])

    def test_valid_guide_with_no_matching_film_clears_stale_selection(self):
        self.owned_collection([B])
        with self.feed(guide_xml(title="Un film absent")):
            result = run_once(self.cfg, now=NOW)
        self.assertEqual(result["collection_movie_count"], 0)
        self.assertEqual(self.server.collections[C]["items"], [])

    def test_server_change_requires_separate_state(self):
        atomic_json(self.cfg.data_dir / "state.json", {"server_id": "another-server", "collection_id": C})
        with self.feed(), self.assertRaisesRegex(ExtensionError, "autre serveur"):
            run_once(self.cfg, now=NOW)
        self.assertFalse(self.server.mutations)

    def test_pagination_reads_entire_library(self):
        self.server.movies = [movie(f"{i:032x}", f"Film {i}") for i in range(401)]
        movies = Jellyfin(self.cfg).movies()
        self.assertEqual(len(movies), 401)
        self.assertEqual(len(self.server.requests), 3)

    def test_redirect_never_forwards_api_key(self):
        self.server.redirect = True
        with self.assertRaisesRegex(ExtensionError, "redirige"):
            Jellyfin(self.cfg).movies()
        self.assertEqual(len(self.server.requests), 1)


class ConfigAndLockTests(unittest.TestCase):
    def test_credentials_and_insecure_guide_are_rejected(self):
        cfg = config(Path("unused"))
        cfg.validate()
        for invalid in (replace(cfg, api_key="COLLER_LA_CLE_API_JELLYFIN_ICI"), replace(cfg, guide_url="http://untrusted.invalid/tv.xml"), replace(cfg, jellyfin_url="http://user:password@nas:8096"), replace(cfg, start="25:00")):
            with self.assertRaises(ValueError):
                invalid.validate()
        self.assertNotIn(KEY, repr(cfg))

    def test_os_lock_prevents_parallel_writers_and_is_released(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory)
            with instance_lock(path):
                with self.assertRaises(ExtensionError):
                    with instance_lock(path):
                        self.fail("second writer obtained lock")
            with instance_lock(path):
                pass


if __name__ == "__main__":
    unittest.main()
