"""Regression cases from the October 2026 audit, with no NAS credentials/data."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from cesoir.app import resolve_programme, run_once
from cesoir.config import ExtensionError, evening_window
from cesoir.guide import GuideCache, parse_guide
from cesoir.lookup import MetadataLookup
from cesoir.matching import Matcher
from cesoir.titles import number_signature, title_alias_pair, title_similarity
from test_extension import A, C, NOW, TEMP_ROOT, FakeServer, config, guide_xml, movie, programme


class GenreRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.cfg = config(Path(self.tmp.name))
        self.path = self.cfg.data_dir / 'guide.xml'

    def parse(self, xml):
        self.path.write_bytes(xml)
        return parse_guide(self.path, self.cfg, *evening_window(NOW, self.cfg))

    def test_standalone_film_genres_are_candidates_without_inventing_a_year(self):
        for genre in ['Comédie', 'Drame', 'Comédie dramatique', 'Western', 'Animation', 'Science-fiction']:
            with self.subTest(genre=genre):
                result = self.parse(guide_xml(category=genre).replace(b'<date>2001</date>', b''))
                self.assertEqual(len(result.movies), 1)
                self.assertTrue(result.movies[0].genre_only)
                self.assertIsNone(result.movies[0].year)

    def test_series_documentaries_and_standup_are_not_added_as_comedies(self):
        for extra in ['<category>Série</category>', '<category>Documentaire</category>',
                      '<category>Spectacle</category>', '<category>Divertissement</category>',
                      '<episode-num system="xmltv_ns">0.0.</episode-num>']:
            with self.subTest(extra=extra):
                self.assertFalse(self.parse(guide_xml(category='Comédie', extra=extra)).movies)

    def test_explicit_film_is_not_marked_as_genre_only(self):
        self.assertFalse(self.parse(guide_xml(category='Film Drame')).movies[0].genre_only)

    def test_telefilm_setting_still_applies(self):
        self.cfg = replace(self.cfg, include_tv_movies=False)
        self.assertFalse(self.parse(guide_xml(category='Téléfilm', extra='<category>Comédie</category>')).movies)

    def test_a_feed_without_categories_is_rejected_instead_of_emptying_the_selection(self):
        with self.assertRaisesRegex(ExtensionError, 'aucune catégorie'):
            self.parse(guide_xml().replace(b'<category>Film</category>', b''))


class TitleRegressionTests(unittest.TestCase):
    def test_french_ordinal_variants_match_and_preserve_the_part_number(self):
        local = movie(title='Twilight, chapitre 4 : Révélation, 1ère partie', year=2011)
        matcher = Matcher([local])
        self.assertEqual(matcher.match(programme('Twilight, chapitre 4 : Révélation, 1re partie', year=2011))[0].movie['Id'], A)
        self.assertEqual(number_signature(local['Name']), ('4', '1'))
        self.assertEqual(title_similarity(local['Name'], 'Twilight, chapitre 4 : Révélation, 2e partie'), 0)

    def test_ordinary_titles_and_year_or_language_labels_are_not_split_as_aliases(self):
        for title in ['Film (2025)', 'Film (VF)', 'Film (version restaurée)', 'Rocky (II)', 'Film (2025) (VF)']:
            with self.subTest(title=title):
                self.assertIsNone(title_alias_pair(title))


class MetadataAuditRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.cfg = config(Path(self.tmp.name), metadata_lookup=True)
        self.client = Mock()
        self.matcher = Matcher([movie(ProviderIds={'Tmdb': '42', 'Imdb': 'tt1234567'})])

    def lookup(self):
        return MetadataLookup(self.cfg, self.client, self.matcher, NOW)

    def test_bilingual_parenthetical_title_requires_both_names_of_the_same_work(self):
        self.matcher = Matcher([movie(title='L’Intermédiaire', OriginalTitle='Relay', year=2025, ProviderIds={'Tmdb': '42'})])
        self.client.search_movie.return_value = [{'Name': 'L’Intermédiaire', 'OriginalTitle': 'Relay',
            'ProductionYear': 2025, 'ProviderIds': {'Tmdb': '42'}}]
        match, _ = self.lookup().match(programme('L’Intermédiaire (Relay)', year=2024))
        self.assertEqual(match.movie['Id'], A)
        self.assertIn('±1', match.method)

    def test_parenthetical_subtitle_cannot_match_the_first_film_by_its_base_title(self):
        self.matcher = Matcher([movie(title='Batman', year=1966, ProviderIds={'Tmdb': '42'})])
        self.client.search_movie.return_value = [{'Name': 'Batman', 'OriginalTitle': 'Batman',
            'ProductionYear': 1966, 'ProviderIds': {'Tmdb': '42'}}]
        self.assertIsNone(self.lookup().match(programme('Batman (The Dark Knight)', year=None))[0])

    def test_id_confirmed_local_original_title_can_complete_missing_remote_alias(self):
        self.matcher = Matcher([movie(title='L’Intermédiaire', OriginalTitle='Relay', year=2025, ProviderIds={'Tmdb': '42'})])
        self.client.search_movie.return_value = [{'Name': 'L’Intermédiaire', 'ProductionYear': 2025, 'ProviderIds': {'Tmdb': '42'}}]
        self.assertEqual(self.lookup().match(programme('L’Intermédiaire (Relay)', year=2024))[0].movie['Id'], A)

    def test_parenthetical_alias_queries_recover_results_missing_from_combined_search(self):
        self.matcher = Matcher([movie(title='L’Intermédiaire', OriginalTitle='Relay', year=2025, ProviderIds={'Tmdb': '42'})])
        self.client.search_movie.side_effect = lambda title, *args, **kw: [
            {'Name': 'L’Intermédiaire', 'OriginalTitle': 'Relay', 'ProductionYear': 2025, 'ProviderIds': {'Tmdb': '42'}}
        ] if title == 'Relay' else []
        self.assertIsNotNone(self.lookup().match(programme('L’Intermédiaire (Relay)', year=2024))[0])

    def test_two_providers_can_be_joined_by_the_existing_consistent_identity_pair(self):
        self.client.search_movie.return_value = [
            {'Name': 'Le Cinéma des étoiles', 'ProductionYear': 2001, 'ProviderIds': {'Tmdb': '42'}},
            {'Name': 'Le Cinéma des étoiles', 'ProductionYear': 2002, 'ProviderIds': {'Imdb': 'tt1234567'}},
        ]
        match, _ = self.lookup().match(programme(year=None))
        self.assertEqual(match.movie['Id'], A)

    def test_equal_names_and_years_do_not_merge_unrelated_provider_results(self):
        self.client.search_movie.return_value = [
            {'Name': 'Le Cinéma des étoiles', 'ProductionYear': 2001, 'ProviderIds': {'Tmdb': '42'}},
            {'Name': 'Le Cinéma des étoiles', 'ProductionYear': 2001, 'ProviderIds': {'Imdb': 'tt7654321'}},
        ]
        self.assertIsNone(self.lookup().match(programme(year=None))[0])

    def test_a_conflicting_provider_cannot_be_hidden_by_an_owned_id(self):
        self.client.search_movie.return_value = [
            {'Name': 'Le Cinéma des étoiles', 'ProductionYear': 2001, 'ProviderIds': {'Tmdb': '42', 'Imdb': 'tt7654321'}}
        ]
        self.assertIsNone(self.lookup().match(programme())[0])

    def test_yearless_search_considers_a_remake_returned_only_in_english(self):
        self.client.search_movie.side_effect = lambda *args, **kw: [
            {'Name': 'Le Cinéma des étoiles', 'ProductionYear': 2020 if kw.get('language') == 'en' else 2001,
             'ProviderIds': {'Tmdb': '99' if kw.get('language') == 'en' else '42'}}]
        self.assertIsNone(self.lookup().match(programme(year=None))[0])

    def test_yearless_genre_never_uses_an_owned_remake_as_a_fallback(self):
        self.matcher = Matcher([movie(title='La famille Addams', year=2019, ProviderIds={'Tmdb': '481084'})])
        self.client.search_movie.return_value = [
            {'Name': 'La famille Addams', 'ProductionYear': 1991, 'ProviderIds': {'Tmdb': '2907'}},
            {'Name': 'La famille Addams', 'ProductionYear': 2019, 'ProviderIds': {'Tmdb': '481084'}},
        ]
        p = replace(programme('La famille Addams', year=None), genre_only=True)
        self.assertIsNone(resolve_programme(p, self.matcher, self.lookup())[0])
        self.assertEqual(resolve_programme(p, self.matcher, None), (None, 'identité à confirmer'))

    def test_identified_absent_original_is_not_replaced_with_the_owned_animation(self):
        self.matcher = Matcher([movie(title='La famille Addams', year=2019, ProviderIds={'Tmdb': '481084'})])
        self.client.search_movie.return_value = [
            {'Name': 'La famille Addams', 'ProductionYear': 1991, 'ProviderIds': {'Tmdb': '2907'}}]
        p = replace(programme('La famille Addams', year=None), genre_only=True)
        self.assertEqual(resolve_programme(p, self.matcher, self.lookup()), (None, 'identifiant absent'))

    def test_yearless_comedy_with_a_confirmed_identity_can_be_selected(self):
        self.client.search_movie.return_value = [
            {'Name': 'Le Cinéma des étoiles', 'ProductionYear': 2001, 'ProviderIds': {'Tmdb': '42'}}]
        p = replace(programme(year=None), genre_only=True)
        self.assertEqual(resolve_programme(p, self.matcher, self.lookup())[0].movie['Id'], A)

    def test_manual_override_remains_an_explicit_choice_for_yearless_genres(self):
        matcher = Matcher(list(self.matcher.movies.values()), {'Le Cinéma des étoiles': A})
        p = replace(programme(year=None), genre_only=True)
        self.assertEqual(resolve_programme(p, matcher, None)[0].method, 'manuel')

    def test_short_synopsis_disambiguates_when_seven_words_and_a_clear_margin_agree(self):
        text = 'Trois parapsychologues excentriques, Peter, Raymond et Egon, perdent sans préavis leur poste de chercheur à l’université de New York. Ils fondent S.O.S. Fantômes, une agence spécialisée dans la traque des spectres.'
        self.client.search_movie.return_value = [
            {'Name': 'Titre TV', 'ProductionYear': 1984, 'ProviderIds': {'Tmdb': '42'},
             'Overview': 'Les fantômes menacent New York. Peter, Raymond et Egon, trois scientifiques, inventent un équipement électronique pour capturer les revenants.'},
            {'Name': 'Titre TV', 'ProductionYear': 2016, 'ProviderIds': {'Tmdb': '99'},
             'Overview': 'Erin enseigne les phénomènes paranormaux. Abby et Jillian fabriquent une technologie pour détecter les apparitions dans un manoir hanté.'},
        ]
        p = replace(programme('Titre TV', year=None), description=text)
        self.assertIsNotNone(self.lookup().match(p)[0])
        self.client.search_movie.return_value[1]['Overview'] = self.client.search_movie.return_value[0]['Overview']
        self.assertIsNone(MetadataLookup(replace(self.cfg, data_dir=self.cfg.data_dir / 'other'), self.client, self.matcher, NOW).match(p)[0])


class AuditPipelineRegressionTests(unittest.TestCase):
    def test_yearless_comedy_reaches_the_collection_after_metadata_confirmation(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as folder:
            server = FakeServer()
            self.addCleanup(server.close)
            server.movies = [movie(ProviderIds={'Tmdb': '42'})]
            server.remote_results = [{'Name': 'Le Cinéma des étoiles', 'ProductionYear': 2001, 'ProviderIds': {'Tmdb': '42'}}]
            cfg = replace(config(Path(folder), metadata_lookup=True), jellyfin_url=server.url)
            xml = guide_xml(category='Comédie').replace(b'<date>2001</date>', b'')
            with patch.object(GuideCache, '_download', lambda _cache, dest: dest.write_bytes(xml)):
                report = run_once(cfg, now=NOW)
            self.assertEqual(server.collections[C]['items'], [A])
            self.assertEqual(report['guide_genre_only_count'], 1)
            self.assertEqual(report['broadcasts'][0]['match_method'], 'métadonnées Jellyfin + identifiant')

    def test_uncategorized_feed_cannot_remove_an_existing_collection(self):
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as folder:
            server = FakeServer()
            self.addCleanup(server.close)
            cfg = replace(config(Path(folder)), jellyfin_url=server.url)
            with patch.object(GuideCache, '_download', lambda _cache, dest: dest.write_bytes(guide_xml())):
                run_once(cfg, now=NOW)
            members = set(server.collections[C]['items'])
            bad = guide_xml().replace(b'<category>Film</category>', b'')
            cfg = replace(cfg, data_dir=Path(folder) / 'without-cache')
            with patch.object(GuideCache, '_download', lambda _cache, dest: dest.write_bytes(bad)):
                with self.assertRaises(ExtensionError):
                    run_once(cfg, now=NOW)
            self.assertEqual(set(server.collections[C]['items']), members)


if __name__ == '__main__':
    unittest.main()
