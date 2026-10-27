# Validation de la version 1.3.0

Les défauts ont été isolés pendant un audit du 27 octobre 2026, puis reproduits dans des tests sans accès à un NAS. Les captures et le catalogue personnels restent hors du dépôt public.

## Relecture des captures

Les résultats ci-dessous utilisent le même catalogue au moment de l'audit et les réponses de recherche déjà enregistrées. Ils ne reconstituent pas la présence historique des fichiers ni les anciennes exécutions Docker. Aucune collection n'est modifiée par la relecture.

| Soirée | Périmètre | Sélection v1.2.0 | Sélection v1.3.0 avec réponses enregistrées | Nouvelles recherches nécessaires, non rejouées |
| --- | --- | --- | --- | --- |
| 22 octobre | Archive web partielle, 20 chaînes | 1 | 2 | 0 |
| 23 octobre | Archive web partielle, 20 chaînes | 0 | 1 | 0 |
| 24 octobre | XMLTVFR TNT, 30 chaînes | 0 | 0 | 0 |
| 25 octobre | XMLTVFR TNT, 30 chaînes | 6 | 6 | 4 |
| 26 octobre | XMLTVFR TNT, 30 chaînes | 2 | 2 | 3 |
| 27 octobre, contrôle complémentaire | XMLTVFR TNT, 30 chaînes | 4 | 5 | 0 |

Les programmes commencent entre 20 h et 4 h, Europe/Paris. La nuit du changement d'heure du 24 au 25 couvre 9 heures réelles. Pour les 22–23, les entrées proviennent des pages datées de programme, avec une interprétation des genres ; les XMLTV historiques n'étaient pas disponibles.

La relecture confirme la récupération de **Twilight, chapitre 4, première partie**, **S.O.S. Fantômes (1984)** et **L'Intermédiaire / Relay**. Les 4 nouveaux candidats du 25 et les 3 du 26 sont désormais détectés ; ils nécessitent une recherche de métadonnées supplémentaire pour confirmer leur identité. Cette recherche n'avait pas été capturée par l'ancienne version, qui les ignorait avant cette étape. Leur résultat de production n'est donc pas présenté comme acquis.

Le cas **La Famille Addams** reste exclu dans la relecture : une version possédée ne doit pas remplacer une autre version de même titre annoncée à la télévision.

## Cas de régression automatisés

La suite couvre notamment :

- La détection des genres seuls et le rejet des séries, spectacles et documentaires associés à ces genres.
- Les ordinaux français, avec protection des numéros de parties et de suites.
- Les alias bilingues confirmés par les noms et identifiants d'une même œuvre ; le rejet d'un simple titre de base d'une suite.
- Les paires TMDb/IMDb cohérentes, les identifiants contradictoires et les œuvres distinctes portant le même nom la même année.
- Les remakes apparaissant dans une autre langue de recherche, ainsi que les synopsis trop similaires pour départager les candidats.
- La vérification d'identité des nouveaux genres sans année, même lorsqu'un seul homonyme est présent localement.
- Le refus d'un guide sans catégorie, avant toute synchronisation de la collection.

Les tests utilisent des réponses simulées et des identifiants d'exemple. Les constructions GitHub Actions les exécutent dans l'image Linux, sans réseau externe, avant de publier les images AMD64/ARM64.

## Sources supplémentaires

Le flux XMLTVFR reste la référence. Dans les captures du 27, Open-EPG n'ajoutait ni année ni identifiant aux 15 films déjà reconnus. Le flux EPG.pw présentait des décalages de grille et des dates de diffusion dans un champ interprété comme l'année de production. Ces constats sur un échantillon ne constituent pas une évaluation permanente des fournisseurs. Aucun de ces deux flux n'est activé automatiquement.
