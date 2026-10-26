from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from cesoir.config import Config, ExtensionError, atomic_json, evening_window
from cesoir.guide import GuideCache, parse_guide
from cesoir.app import run_once
from cesoir.lookup import MetadataLookup
from cesoir.matching import Matcher
from cesoir.titles import filename_evidence, normalize, title_similarity
from test_extension import A, B, KEY, NOW, TEMP_ROOT, FakeServer, config, guide_xml, movie, programme


class ExtendedRecognitionTests(unittest.TestCase):
    def test_year_and_broadcast_labels_are_not_part_of_the_title(self):
        matcher = Matcher([movie()])
        for title in ("Cinéma : Le Cinéma des étoiles", "Le Cinéma des étoiles (2001) (VF)", "Le Cinéma des étoiles (version restaurée)"):
            with self.subTest(title=title):
                self.assertEqual(matcher.match(programme(title))[0].movie["Id"], A)

    def test_roman_sequel_numbers_are_equivalent_but_other_sequels_are_not(self):
        matcher = Matcher([movie(title="Rocky II", year=1979)])
        self.assertIsNotNone(matcher.match(programme("Rocky 2", year=1979))[0])
        self.assertIsNone(matcher.match(programme("Rocky 3", year=1979))[0])
        self.assertEqual(title_similarity("Rocky II", "Rocky III"), 0)

    def test_non_latin_titles_remain_distinct(self):
        self.assertNotEqual(normalize("千と千尋の神隠し"), normalize("となりのトトロ"))
        matcher = Matcher([movie(title="千と千尋の神隠し")])
        self.assertIsNotNone(matcher.match(programme("千と千尋の神隠し"))[0])
        self.assertIsNone(matcher.match(programme("となりのトトロ"))[0])

    def test_filename_recovers_an_incorrect_display_name_with_a_confirmed_year(self):
        matcher = Matcher([movie(title="Nom incorrect", Path="/data/movies/Le Cinéma des étoiles (2001) [tmdbid-42].mkv")])
        match, _ = matcher.match(programme())
        self.assertEqual(match.method, "nom de fichier + année")
        self.assertIsNone(matcher.match(programme(year=None))[0])
        self.assertIsNone(matcher.match(programme(year=2020))[0])

    def test_scene_filename_and_identifiers_are_extracted_without_quality_tags(self):
        title, year, ids = filename_evidence("/movies/Le.Cinema.des.etoiles.2001.1080p.BluRay.x264.mkv")
        self.assertEqual((title, year, ids), ("Le Cinema des etoiles", 2001, {}))
        matcher = Matcher([movie(title="Nom incorrect", Path="/movies/Film (2001) [imdbid-tt1234567].mkv")])
        self.assertIsNotNone(matcher.match(programme("Autre traduction", providers={"imdb":"tt1234567"}))[0])

    def test_filename_ids_do_not_override_conflicting_library_metadata(self):
        matcher = Matcher([movie(title="Nom incorrect", ProviderIds={"Tmdb":"99"}, Path="/movies/Le Cinéma des étoiles (2001) [tmdbid-42].mkv")])
        self.assertIsNone(matcher.match(programme(providers={"tmdb":"42"}))[0])

    def test_filename_year_is_not_mistaken_for_a_different_known_release_year(self):
        matcher = Matcher([movie(title="Nom incorrect", year=2020, Path="/movies/Le Cinéma des étoiles (2001).mkv")])
        self.assertIsNone(matcher.match(programme())[0])

    def test_small_typo_can_match_only_with_the_same_known_year(self):
        matcher = Matcher([movie()])
        target = programme("Le Cinéma des étoile")
        match, _ = matcher.match_approximate(target)
        self.assertEqual(match.movie["Id"], A)
        self.assertGreaterEqual(match.score, 0.94)
        self.assertIsNone(matcher.match_approximate(replace(target, year=None))[0])
        self.assertIsNone(matcher.match_approximate(replace(target, year=2020))[0])

    def test_articles_and_written_ampersands_require_year_evidence_locally(self):
        matcher = Matcher([movie(title="The Smashing Machine", year=2025)])
        self.assertIsNotNone(matcher.match_approximate(programme("Smashing Machine", year=2025))[0])
        self.assertIsNone(matcher.match_approximate(programme("Smashing Machine", year=None))[0])
        matcher = Matcher([movie(title="Fast & Furious", year=2001)])
        self.assertIsNotNone(matcher.match_approximate(programme("Fast and Furious"))[0])

    def test_fuzzy_match_does_not_add_missing_sequel_or_conflicting_provider(self):
        matcher = Matcher([movie(title="La route des étoiles 2")])
        self.assertIsNone(matcher.match_approximate(programme("La route des étoiles"))[0])
        self.assertIsNone(matcher.match_approximate(programme("La route des étoiles 3"))[0])
        self.assertIsNone(matcher.match_approximate(programme("La route des étoiles 2", providers={"tmdb":"99"}))[0])

    def test_close_competing_works_are_not_selected_arbitrarily(self):
        matcher = Matcher([movie(title="Le Cinéma des étoiles"), movie(B, title="Le Cinéma des étoile")])
        self.assertIsNone(matcher.match_approximate(programme("Le Cinéma des étoiless"))[0])

    def test_short_similar_titles_are_not_automatically_selected(self):
        matcher = Matcher([movie(title="Dune")])
        self.assertIsNone(matcher.match_approximate(programme("June"))[0])
        matcher = Matcher([movie(title="The A")])
        self.assertIsNone(matcher.match_approximate(programme("A"))[0])

    def test_embedded_library_year_cannot_bypass_the_year_check(self):
        matcher = Matcher([movie(title="Titre (2020)",year=None)])
        self.assertIsNone(matcher.match(programme("Titre",year=2001))[0])

    def test_director_disambiguates_two_releases_of_the_same_title(self):
        matcher = Matcher([movie(People=[{"Name":"Alice Martin", "Type":"Director"}]), movie(B, year=2020, People=[{"Name":"Bob Durand", "Type":"Director"}])])
        target = replace(programme(year=None), directors=("Bob Durand",))
        self.assertEqual(matcher.match(target)[0].movie["Id"], B)
        self.assertIsNone(matcher.match(replace(target, directors=("Someone Else",)))[0])

    def test_shared_id_does_not_hide_a_conflicting_second_provider(self):
        matcher = Matcher([movie(ProviderIds={"Tmdb":"42", "Imdb":"tt1234567"}), movie(B, ProviderIds={"Tmdb":"42", "Imdb":"tt7654321"})])
        self.assertIsNone(matcher.match(programme())[0])

    def test_conflicting_normalized_manual_overrides_fail_explicitly(self):
        with self.assertRaisesRegex(ExtensionError, "contradictoires"):
            Matcher([movie(), movie(B)], {"Étoiles":A, "ETOILES":B})


class EnhancedMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.cfg = config(Path(self.tmp.name), metadata_lookup=True)
        self.client = Mock()
        self.matcher = Matcher([movie(title="Local original", ProviderIds={"Tmdb":"42"})])

    def resolve(self, target):
        return MetadataLookup(self.cfg, self.client, self.matcher, NOW).match(target)

    def test_english_lookup_is_tried_when_french_search_has_no_matching_name(self):
        def search(title, year, **kw):
            return [{"Name":"English television title" if kw.get("language") == "en" else "Titre français", "ProductionYear":2001, "ProviderIds":{"Tmdb":"42"}}]
        self.client.search_movie.side_effect = search
        self.assertIsNotNone(self.resolve(programme("English television title"))[0])
        self.assertTrue(any(call.kwargs.get("language") == "en" for call in self.client.search_movie.call_args_list))

    def test_all_titles_in_the_guide_are_available_for_search(self):
        self.client.search_movie.side_effect = lambda title, year, **kw: [{"Name":title, "ProductionYear":2001, "ProviderIds":{"Tmdb":"42"}}] if title == "Alternate title" else []
        target = replace(programme("Unrecognised main title"), titles=("Unrecognised main title", "Alternate title"))
        self.assertIsNotNone(self.resolve(target)[0])

    def test_production_release_year_difference_is_accepted_only_via_identity(self):
        self.client.search_movie.side_effect = lambda title, year, **kw: [] if year else [{"Name":"Titre TV", "ProductionYear":2002, "ProviderIds":{"Tmdb":"42"}}]
        match, _ = self.resolve(programme("Titre TV"))
        self.assertEqual(match.movie["Id"], A)
        self.assertIn("±1", match.method)
        self.client.search_movie.side_effect = lambda *args, **kw: [{"Name":"Titre TV", "ProductionYear":2003, "ProviderIds":{"Tmdb":"42"}}]
        self.assertIsNone(self.resolve(programme("Titre TV", year=2000))[0])

    def test_original_title_in_search_result_can_identify_the_owned_film(self):
        self.client.search_movie.return_value = [{"Name":"Titre français", "OriginalTitle":"Original television title", "ProductionYear":2001, "ProviderIds":{"Tmdb":"42"}}]
        self.assertIsNotNone(self.resolve(programme("Original television title"))[0])

    def test_missing_year_can_be_resolved_by_a_distinctive_plot(self):
        plot = "Une expédition antarctique découvre un laboratoire abandonné. Un biologiste isole un parasite extraterrestre dans la glace pendant une tempête polaire."
        self.client.search_movie.return_value = [
            {"Name":"Titre TV", "ProductionYear":2001, "ProviderIds":{"Tmdb":"42"}, "Overview":plot},
            {"Name":"Titre TV", "ProductionYear":2020, "ProviderIds":{"Tmdb":"99"}, "Overview":"Un inspecteur parisien recherche un cambrioleur dans les quartiers de la capitale avec sa brigade et un témoin mystérieux."},
        ]
        match, _ = self.resolve(replace(programme("Titre TV", year=None), description=plot))
        self.assertEqual(match.movie["Id"], A)
        self.assertIn("synopsis", match.method)

    def test_similar_remake_plots_remain_ambiguous(self):
        plot = "Une expédition antarctique découvre un laboratoire abandonné. Un biologiste isole un parasite extraterrestre dans la glace pendant une tempête polaire."
        self.client.search_movie.return_value = [
            {"Name":"Titre TV", "ProductionYear":2001, "ProviderIds":{"Tmdb":"42"}, "Overview":plot},
            {"Name":"Titre TV", "ProductionYear":2020, "ProviderIds":{"Tmdb":"99"}, "Overview":plot},
        ]
        self.assertIsNone(self.resolve(replace(programme("Titre TV", year=None), description=plot))[0])

    def test_lookup_never_claims_an_id_match_based_only_on_a_local_title(self):
        self.matcher = Matcher([movie(title="Titre TV")])
        self.client.search_movie.return_value = [{"Name":"Titre TV", "ProductionYear":2001, "ProviderIds":{"Tmdb":"99"}}]
        self.assertEqual(self.resolve(programme("Titre TV")), (None, "identifiant absent"))

    def test_old_cache_is_refreshed_to_include_plot_and_language_evidence(self):
        atomic_json(self.cfg.data_dir / "metadata-cache.json", {"version":1, "entries":{}})
        self.client.search_movie.return_value = [{"Name":"Titre TV", "ProductionYear":2001, "ProviderIds":{"Tmdb":"42"}}]
        self.assertIsNotNone(self.resolve(programme("Titre TV"))[0])
        self.assertEqual(json.loads((self.cfg.data_dir / "metadata-cache.json").read_text())["version"], 2)


class ExtendedGuideAndWindowTests(unittest.TestCase):
    def test_four_am_window_covers_both_occurrences_of_the_autumn_clock_change(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as folder:
            cfg = config(Path(folder))
            now = datetime(2026,10,24,16,tzinfo=timezone.utc)
            start,end = evening_window(now,cfg)
            self.assertEqual((end.astimezone(timezone.utc)-start.astimezone(timezone.utc)).total_seconds(),9*3600)
            extra = '''<programme start="20261025023000 +0200" channel="TF1.fr"><title>Heure été</title><category>Film</category></programme>
<programme start="20261025023000 +0100" channel="TF1.fr"><title>Heure hiver</title><category>Film</category></programme>'''
            path = Path(folder) / "guide.xml"
            path.write_bytes(guide_xml(day="20261024").replace(b"</tv>",extra.encode()+b"</tv>"))
            self.assertEqual([p.title for p in parse_guide(path,cfg,start,end).movies][-2:],["Heure été","Heure hiver"])

    def test_defaults_retain_the_same_evening_at_three_am_and_switch_at_four(self):
        cfg = Config("http://example.invalid", KEY)
        self.assertEqual(cfg.end, "04:00")
        start, end = evening_window(datetime(2026,10,27,2,30,tzinfo=timezone.utc), cfg)
        self.assertEqual(start.date().isoformat(), "2026-10-26")
        self.assertEqual(end.isoformat(), "2026-10-27T04:00:00+01:00")
        self.assertEqual(evening_window(datetime(2026,10,27,3,0,tzinfo=timezone.utc), cfg)[0].date().isoformat(), "2026-10-27")

    def test_environment_can_override_the_window_in_an_old_mounted_config(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as folder:
            root = Path(folder)
            (root / "config.json").write_text(json.dumps({"start":"20:00", "end":"02:00"}))
            (root / "key.txt").write_text(KEY)
            env = {"CONFIG_FILE":str(root / "config.json"),"JELLYFIN_API_KEY_FILE":str(root / "key.txt"),"JELLYFIN_URL":"http://example.invalid", "TV_END":"04:00", "APPROXIMATE_MATCHING":"false"}
            with patch.dict(os.environ, env, clear=True):
                cfg = Config.load()
            self.assertEqual(cfg.end, "04:00")
            self.assertFalse(cfg.approximate_matching)

    def test_year_directors_synopsis_and_case_insensitive_identifiers_are_parsed(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as folder:
            cfg = config(Path(folder))
            xml = guide_xml(title="Film (2020)", extra='<desc lang="fr">Une intrigue précise.</desc><credits><director>Alice Martin</director></credits><episode-num system="IMDB">TT1234567</episode-num>').replace(b"<date>2001</date>", b"")
            p = Path(folder) / "guide.xml"
            p.write_bytes(xml)
            item = parse_guide(p,cfg,*evening_window(NOW,cfg)).movies[0]
            self.assertEqual(item.year,2020)
            self.assertEqual(item.directors,("Alice Martin",))
            self.assertEqual(item.provider_ids,{"imdb":"tt1234567"})
            self.assertEqual(item.description,"Une intrigue précise.")

    def test_making_of_is_not_misclassified_as_a_movie_by_generic_cinema_category(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as folder:
            cfg = config(Path(folder))
            p = Path(folder) / "guide.xml"
            p.write_bytes(guide_xml(category="Cinema",extra="<category>Doc Cinema</category>"))
            self.assertFalse(parse_guide(p,cfg,*evening_window(NOW,cfg)).movies)
            p.write_bytes(guide_xml(category="Film documentaire",extra="<category>Documentaire</category>"))
            self.assertEqual(len(parse_guide(p,cfg,*evening_window(NOW,cfg)).movies),1)


class ExtendedPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.server = FakeServer()
        self.addCleanup(self.server.close)
        self.cfg = replace(config(Path(self.tmp.name)), jellyfin_url=self.server.url)

    def run_xml(self, xml):
        def download(_cache, destination):
            destination.write_bytes(xml)
        with patch.object(GuideCache,"_download",download):
            return run_once(self.cfg,now=NOW)

    def test_a_broadcast_at_three_thirty_is_included_in_the_collection(self):
        xml = guide_xml().replace(b"20261025211000",b"20261026033000").replace(b"20261025231000",b"20261026035500")
        report = self.run_xml(xml)
        self.assertEqual(report["collection_movie_count"],1)
        self.assertEqual(report["end"],"2026-10-26T04:00:00+01:00")

    def test_a_verified_typo_is_added_only_after_unconclusive_metadata_search(self):
        self.cfg = replace(self.cfg,metadata_lookup=True)
        report = self.run_xml(guide_xml(title="Le Cinéma des étoile"))
        self.assertEqual(report["collection_movie_count"],1)
        self.assertEqual(report["broadcasts"][0]["match_method"],"titre proche + année")
        self.assertGreaterEqual(report["broadcasts"][0]["title_similarity"],0.94)

    def test_an_identified_different_film_is_not_overridden_by_fuzzy_matching(self):
        self.cfg = replace(self.cfg,metadata_lookup=True)
        self.server.remote_results = [{"Name":"Le Cinéma des étoile", "ProductionYear":2001,"ProviderIds":{"Tmdb":"99"}}]
        report = self.run_xml(guide_xml(title="Le Cinéma des étoile"))
        self.assertEqual(report["collection_movie_count"],0)
        self.assertEqual(report["skipped"][0]["reason"],"identifiant absent")
        self.assertEqual(report["skipped"][0]["suggestions"][0]["jellyfin_id"],A)

    def test_approximate_matching_can_be_disabled(self):
        self.cfg = replace(self.cfg,approximate_matching=False)
        report = self.run_xml(guide_xml(title="Le Cinéma des étoile"))
        self.assertEqual(report["collection_movie_count"],0)


if __name__ == "__main__":
    unittest.main()
