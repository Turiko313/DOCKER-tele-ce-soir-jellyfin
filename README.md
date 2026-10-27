# Films à la télé ce soir

[![Tests et Docker](https://github.com/Turiko313/DOCKER-tele-ce-soir-jellyfin/actions/workflows/docker.yml/badge.svg)](https://github.com/Turiko313/DOCKER-tele-ce-soir-jellyfin/actions/workflows/docker.yml)
[![Version](https://img.shields.io/github/v/release/Turiko313/DOCKER-tele-ce-soir-jellyfin)](https://github.com/Turiko313/DOCKER-tele-ce-soir-jellyfin/releases/latest)

Retrouve dans **Jellyfin → Collections → Films à la télé ce soir** les films de ta médiathèque qui passent à la télévision pendant la soirée.

L'extension compare le programme TV à ta médiathèque et actualise une collection Jellyfin. Sur Android TV, tu retrouves les affiches, les fiches et la lecture de tes propres fichiers, à l'heure qui te convient.

Elle tourne dans un conteneur Docker supplémentaire sur le NAS et utilise l'API de Jellyfin. La page est celle d'une collection : elle n'ajoute pas d'onglet ou de rangée personnalisée à l'accueil de l'application TV. Les chaînes et horaires sont disponibles dans les journaux et le rapport de l'extension, pas sur les affiches.

## Fonctionnement par défaut

- Programme du [guide TNT de XML TV Fr](https://xmltvfr.fr/xmltv.php), sans clé de fournisseur TV.
- Films et téléfilms dont la diffusion commence entre **20 h et 4 h**, heure de Paris.
- Mise à jour toutes les **15 minutes** ; rafraîchissement du programme toutes les **12 heures** en fonctionnement normal.
- Après minuit, conservation de la soirée précédente jusqu'à 4 h.
- Affichage des seuls films déjà présents dans la médiathèque ; aucun téléchargement de films.
- Correspondances par IMDb/TMDb, ou par titre normalisé et année lorsque les données sont disponibles. Les homonymes ambigus sont écartés.
- Recherche complémentaire des traductions via les métadonnées de Jellyfin si aucun titre local ne correspond ; le résultat doit fournir un identifiant TMDb/IMDb déjà présent dans la médiathèque.
- Reconnaissance des variantes de titres et des noms de fichiers ; titres très proches acceptés avec une année identique et des contrôles de suites et d'homonymes.
- Films également détectés avec un genre seul (« Comédie », « Drame », « Western »…). Sans année ni identifiant, ces nouveaux candidats passent par une vérification d'identité via les métadonnées de Jellyfin avant ajout.
- Images Docker pour **Linux AMD64 et ARM64**, construites automatiquement après réussite des tests.

## Installation Docker sur le NAS

### 1. Télécharger le projet

Télécharge l'archive de la [dernière version](https://github.com/Turiko313/DOCKER-tele-ce-soir-jellyfin/releases/latest) et extrais-la dans un dossier du NAS, par exemple `docker/ce-soir-jellyfin`.

Tu peux aussi cloner le dépôt :

```sh
git clone https://github.com/Turiko313/DOCKER-tele-ce-soir-jellyfin.git
cd DOCKER-tele-ce-soir-jellyfin
```

### 2. Préparer les deux fichiers personnels

Copie `.env.example` vers `.env` et `jellyfin-api-key.txt.example` vers `jellyfin-api-key.txt`. Dans un terminal :

```sh
cp .env.example .env
cp jellyfin-api-key.txt.example jellyfin-api-key.txt
```

Dans `.env`, renseigne l'adresse locale de Jellyfin :

```dotenv
JELLYFIN_URL=http://192.168.1.10:8096
CESOIR_VERSION=latest
```

Utilise l'IP du NAS et le port publié par Jellyfin. `localhost` désignerait le nouveau conteneur lui-même. Si ton adresse comprend un préfixe, conserve-le, par exemple `https://media.exemple.fr/jellyfin`. L'adresse doit être joignable depuis les conteneurs ; les certificats HTTPS doivent être valides et reconnus.

Dans Jellyfin, connecté comme administrateur, ouvre **Tableau de bord → Clés API / API** et crée une clé nommée « Films à la télé ce soir ». Remplace tout le contenu de `jellyfin-api-key.txt` par cette clé, sans guillemets.

Ces deux fichiers restent sur ton NAS et sont exclus de Git. La clé n'est pas intégrée à l'image Docker et n'est pas nécessaire aux constructions GitHub Actions.

### 3. Démarrer

Dans le gestionnaire Docker du NAS, crée un projet à partir de `compose.yaml` et démarre-le. Les noms des boutons dépendent du NAS. Le gestionnaire téléchargera l'image déjà construite.

Dans un terminal :

```sh
docker compose pull
docker compose up -d
docker compose logs --tail=50 ce-soir
```

Aucune compilation sur le NAS, aucun port à ouvrir, aucun dossier de films à monter dans ce conteneur. Il doit simplement pouvoir joindre Jellyfin et le fournisseur du guide TV.

Pour consulter les correspondances avant toute modification de Jellyfin, effectue cette simulation **avant de démarrer le service** :

```sh
docker compose pull
docker compose run --rm ce-soir --dry-run
docker compose up -d
```

### 4. Ouvrir la collection

Sur la télévision : **Jellyfin → Collections → Films à la télé ce soir**. La collection est créée au premier passage qui trouve au moins un film correspondant.

Si nécessaire, quitte puis rouvre l'application. Vérifie que le compte a accès à la bibliothèque Collections et aux films concernés. La présentation dépend de l'application ; l'extension ne force pas l'affichage de cette collection en rangée d'accueil.

## Placer la collection en premier

Une fois la collection créée :

1. Depuis un navigateur, connecte-toi à Jellyfin comme administrateur et ouvre la collection.
2. Clique sur **⋮ → Éditer les métadonnées**.
3. Dans **Titre de tri**, inscris `000 - Films à la télé ce soir` et enregistre.
4. Sur Android TV, choisis le tri des collections par **Nom**, en ordre croissant.

Le nom affiché reste « Films à la télé ce soir » ; elle se classe avant les noms alphabétiques habituels. L'extension ne réécrit pas ce réglage lors des mises à jour.

## Image Docker et versions

```text
ghcr.io/turiko313/docker-tele-ce-soir-jellyfin:latest
```

| Étiquette | Contenu |
| --- | --- |
| `latest` | Dernière version stable publiée. |
| `1.3.0` | Version précise, à utiliser pour figer une installation. |
| `1.2`, `1` | Dernière version publiée dans cette branche de versions. |
| `edge` | Dernier commit de `main` ayant passé les tests. |
| `sha-…` | Image associée à un commit précis. |

Pour figer une version, indique par exemple `CESOIR_VERSION=1.3.0` dans `.env`. Pour appliquer une nouvelle image :

```sh
docker compose pull
docker compose up -d
```

Les données de suivi sont conservées dans le volume `ce-soir-data`.

## Régler les chaînes et les horaires

Modifie `config.json`, puis redémarre le conteneur avec `docker compose restart ce-soir`. Conserve un JSON valide avec ses guillemets et virgules.

| Réglage | Rôle |
| --- | --- |
| `start`, `end` | Plage de début des diffusions, par défaut `"20:00"` à `"04:00"`. Les variables Docker `TV_START` et `TV_END` sont prioritaires sur le fichier. |
| `timezone` | Fuseau horaire, `"Europe/Paris"` par défaut. |
| `channels` | `[]` prend toutes les chaînes du fichier choisi ; une liste limite la sélection. |
| `include_tv_movies` | `true` inclut les téléfilms ; `false` les écarte. |
| `metadata_lookup` | `true` recherche aussi les traductions via les fournisseurs de métadonnées Jellyfin. `METADATA_LOOKUP=false` dans l'environnement Docker désactive cette étape, même sans fichier de configuration monté. |
| `approximate_matching` | `true` permet les variantes ou fautes légères avec une année connue identique et des contrôles supplémentaires. `APPROXIMATE_MATCHING=false` désactive ce rapprochement automatique. |
| `collection_name` | Nom de la collection ; s'il est modifié, ajuste aussi le nom de la collection existante dans Jellyfin. |
| `collection_id` | Facultatif : identifiant d'une collection existante dont tu confies explicitement tout le contenu à l'extension. |
| `interval_seconds` | Intervalle de vérification, 900 secondes par défaut, au minimum 60. |
| `guide_url` | URL HTTPS du guide XMLTV, simple ou compressé en `.gz` / `.zip`. |
| `guide_refresh_hours` | Intervalle de rafraîchissement du guide, 12 heures par défaut. |
| `guide_max_age_hours` | Âge maximal du cache de secours, 48 heures par défaut. |
| `title_overrides` | Correspondances manuelles entre un titre TV et un identifiant Jellyfin. |

Exemple de sélection de chaînes :

```json
"channels": ["TF1.fr", "France2.fr", "France3.fr", "M6.fr", "Arte.fr"]
```

Consulte la [liste des chaînes du guide TNT](https://xmltvfr.fr/channels.php?guide=tnt) pour les identifiants. Le guide peut aussi inclure des chaînes payantes ; sélectionne celles qui t'intéressent. Limites de téléchargement : 24 Mio compressés et 128 Mio décompressés. Le fournisseur reste un service tiers dont la disponibilité et la qualité des données peuvent varier.

### Retrouver les traductions et corriger un titre non reconnu

La reconnaissance combine plusieurs niveaux de preuves :

1. Correspondances manuelles, puis identifiants IMDb/TMDb du guide et de la médiathèque. Les identifiants présents dans un nom de fichier standard, comme `[tmdbid-123]`, peuvent compléter une fiche incomplète ; une contradiction avec la fiche n'est pas écrasée.
2. Titres français et originaux, normalisés sans perdre les caractères non latins. Les mentions de diffusion comme `(VF)`, `(version restaurée)` et les années entre parenthèses sont distinguées du titre. Les chiffres romains des suites sont rapprochés des chiffres arabes, et les ordinaux `1re / 1ère partie` sont reconnus sans confondre les parties différentes.
3. Nom de fichier, si son année concorde avec celle du guide et ne contredit pas la fiche. Un nom comme `Film (2025) [tmdbid-123].mkv` ou `Film.2025.1080p.BluRay.mkv` peut ainsi aider lorsque le nom affiché est incorrect.
4. Recherche des titres et de leurs variantes en français et anglais via les fournisseurs de métadonnées déjà configurés dans Jellyfin, par exemple TMDb. Les titres TV sont transmis via Jellyfin à ces fournisseurs. Cela utilise la [recherche de métadonnées Jellyfin](https://github.com/jellyfin/jellyfin/blob/master/Jellyfin.Api/Controllers/ItemLookupController.cs), sans nouvelle clé ni extension à installer, et sans appliquer de métadonnées aux films.
5. En dernier recours, titres très proches ou différences d'article : année connue et identique, similarité d'au moins 94 %, numéros de suites identiques, titres suffisamment longs en cas de faute, et absence d'un autre candidat trop proche. Les titres courts, les remakes sans année et les suites différentes ne sont pas ajoutés par ce mécanisme.

La recherche de métadonnées doit confirmer un identifiant présent dans le catalogue. Elle peut accepter un écart de production/sortie d'un an lorsque l'œuvre est identifiée sans ambiguïté. Elle peut aussi exploiter un réalisateur indiqué dans le guide ou un synopsis suffisamment distinctif : au moins cinq mots informatifs communs, couverture d'au moins 45 % des mots informatifs du synopsis TV et avance d'au moins 18 points sur le résultat suivant. Des résumés très proches de remakes restent ambigus. Une recherche sans année renvoyant au moins vingt résultats nécessite ces éléments supplémentaires pour départager les œuvres.

L'extension n'ajoute que des entrées de films déjà présentes dans le catalogue Jellyfin. Elle ne vérifie pas les octets des vidéos et ne modifie pas leurs fiches. Les rapprochements de titres restent des heuristiques : ils réduisent les oublis sans garantir une reconnaissance parfaite. La méthode et, le cas échéant, le score de similarité sont indiqués dans le rapport.

Les recherches sont mises en cache pendant 24 heures, jusqu'à 500 entrées. Si l'API de recherche échoue, un cache de moins de sept jours peut servir de secours ; à défaut, la synchronisation échoue et la collection précédente est conservée. Si le fournisseur renvoie des résultats vides ou ambigus, les diffusions concernées sont écartées normalement. Pour revenir aux seules correspondances locales, définis `METADATA_LOOKUP: "false"` dans `environment` de ton Compose OMV, ou `"metadata_lookup": false` dans `config.json`.

Pour désactiver également les titres proches automatiques, ajoute `APPROXIMATE_MATCHING: "false"`. Les suggestions restent consultables dans `report.json` et ne sont jamais ajoutées simplement parce qu'elles apparaissent parmi les suggestions.

Depuis la version **1.3.0**, les alias bilingues comme `L'Intermédiaire (Relay)` servent aussi aux recherches. Le titre français et le titre original doivent être reliés à la même œuvre ; enlever arbitrairement un sous-titre ne suffit pas. Les résultats TMDb et IMDb peuvent être rapprochés via les paires d'identifiants cohérentes des fiches Jellyfin.

Les genres seuls (« Comédie », « Drame », etc.) sont désormais des candidats. Lorsqu'ils ne fournissent ni année ni identifiant, une vérification distante évite de remplacer, par exemple, un film de 1991 absent par son remake de 2019 présent. Si `METADATA_LOOKUP=false`, ils sont écartés avec le motif **identité à confirmer** ; une correspondance manuelle dans `title_overrides` reste possible. Les titres sans année recherchés dans les métadonnées sont vérifiés sur l'ensemble des résultats français et anglais avant sélection.

Le guide XMLTVFR reste la source de grille par défaut. Les autres flux évalués n'ont pas apporté d'enrichissement fiable dans l'échantillon ; aucun flux n'est ajouté automatiquement. Un guide sans catégorie de programme est refusé, avec conservation de la collection et utilisation du cache valide si possible. Les résultats et limites de la relecture des cinq soirées figurent dans la [validation de la version 1.3.0](docs/validation-1.3.0.md).

**Passage de 2 h à 4 h :** si le conteneur utilise la configuration intégrée à l'image, la nouvelle plage s'applique après sa mise à jour. Si un ancien `config.json` est monté dans Docker, remplace `"end": "02:00"` par `"end": "04:00"`, ou ajoute `TV_END: "04:00"` dans `environment` de ton Compose OMV. Cela permet de modifier la plage sans réécrire le fichier monté.

Une traduction différente peut être associée manuellement à un film :

```json
"title_overrides": {
  "Le titre utilisé dans le programme TV": "0123456789abcdef0123456789abcdef"
}
```

Remplace l'identifiant d'exemple par celui de ton film, visible dans l'adresse de sa fiche ouverte depuis le navigateur. La cible doit être un film trouvé dans ta médiathèque.

## Données et comportement en cas de panne

L'extension gère uniquement les **liens vers des films dans sa collection**. Elle ne supprime pas de vidéos et ne modifie pas les titres, résumés ou affiches des films.

La collection est partagée au niveau du serveur : une seule instance de l'extension suffit pour tous les profils. Chaque profil doit avoir accès à la bibliothèque Collections et aux films concernés. Jellyfin applique les droits et restrictions de chaque utilisateur ; l'extension ne gère pas de sélection personnelle par compte.

Si la lecture du guide ou de la médiathèque échoue, la sélection précédente est conservée. Elle peut donc correspondre à une ancienne soirée pendant une panne. Le cache ne sert que s'il couvre encore la soirée et reste assez récent. Si un guide valide couvre la soirée mais qu'aucun film ne correspond, la collection existante est vidée de ses liens.

Le volume `ce-soir-data` contient :

- `state.json` : serveur et collection gérée, à conserver entre les redémarrages.
- `report.json` : dernier résultat réussi, films, chaînes, horaires et correspondances écartées.
- `preview.json` : dernière simulation.
- `guide.xml` et `guide-cache.json` : programme mis en cache.
- `health.json` : résultat du dernier passage, utilisé pour l'état de santé Docker.
- `service.json` : dernier démarrage du service, pour identifier les relances rapprochées.
- `metadata-cache.json` : titres TV recherchés et identifiants publics retournés par les fournisseurs, sans clé API.

Une seule instance peut utiliser ce volume. Pour une simulation après installation, arrête d'abord le service avec `docker compose stop ce-soir`, lance la commande `--dry-run`, puis redémarre avec `docker compose up -d`.

## Dépannage

Depuis la version 1.0.3, les journaux donnent directement les titres écartés et leur motif : aucun titre ou identifiant correspondant, année différente, homonyme ambigu ou identifiants contradictoires. Une exclusion ne prouve pas à elle seule l'absence physique du fichier : vérifie aussi les titres français et originaux de sa fiche Jellyfin, ou utilise `title_overrides` pour une traduction différente.

Exemple de bilan et de détails :

```text
Collection inchangée — soirée du 2026-10-25 : 4 film(s) disponible(s), 4 diffusion(s) retenue(s) sur 12 ; 8 écartée(s) ; ajouts : 0, retraits : 0.
  RETENU | 25/10 21:10 | TF1 | Doctor Strange in the Multiverse of Madness (2022)
  ÉCARTÉ | 26/10 00:10 | France 2 | Nosferatu — plusieurs œuvres possibles dans les métadonnées ; aucun choix automatique
```

Le nombre de films est distinct de celui des diffusions : un même film peut passer sur plusieurs chaînes ou à plusieurs horaires. Les dates évitent les confusions après minuit. Les détails complets s'affichent au démarrage, en simulation ou lorsque le résultat change ; les contrôles suivants conservent un bilan compact. Le rapport JSON complet reste actualisé à chaque passage réussi.

Le rapport indique aussi le nombre de recherches de traductions, les résultats servis depuis le cache, la méthode utilisée pour chaque film retenu et les suggestions non ajoutées pour les exclusions. Les exclusions distinguent les films identifiés sans identifiant correspondant dans la médiathèque, les recherches sans résultat concluant et les homonymes non départagés. Ces diagnostics ne garantissent pas qu'un fichier ne soit pas présent sous une fiche mal identifiée.

La ligne de version annonce un lancement du programme, pas un contrôle périodique. Deux lignes de démarrage espacées de quelques secondes signalent donc deux lancements (redéploiement OMV, mise à jour Watchtower, commande manuelle, etc.). Un démarrage continu détecté moins de deux minutes après le précédent est explicitement signalé lorsque le même volume `/data` est conservé. Le contrôle de santé Docker ne produit pas cette annonce.

| Symptôme | Vérification |
| --- | --- |
| Clé à renseigner ou HTTP 401 / 403 | Contenu de `jellyfin-api-key.txt`, clé Jellyfin valide, autorisation de gérer les collections. |
| Connexion impossible | IP du NAS, port publié, réseau Docker et éventuel préfixe `/jellyfin`. |
| Guide absent ou incomplet | Source TV disponible, horaires couverts et identifiants de chaînes exacts. |
| Collection absente | Un premier film doit correspondre ; consulte les journaux et les droits du compte sur la TV. |
| Collection du même nom déjà existante | Choisis un autre nom ou renseigne `collection_id` pour lui confier explicitement cette collection. |
| Collection mémorisée supprimée | Renseigne une collection de remplacement ou réinitialise le volume après avoir sauvegardé ce que tu souhaites conserver. |
| Conteneur `unhealthy` | Dernier passage en échec ou trop ancien ; consulte `docker compose logs --tail=100 ce-soir`. |

Si une coupure intervient pendant la création, une collection peut exister sans que son identifiant ait été enregistré. Renseigne alors son `collection_id` pour reprendre son suivi.

Pour arrêter l'extension : `docker compose down`. Le volume et la collection sont conservés. Révoque sa clé API si tu ne souhaites plus l'utiliser.

## Développement et construction locale

La version de l'application est définie dans `cesoir/__init__.py`. Le code utilise la bibliothèque standard Python ; le conteneur ajoute la base des fuseaux horaires et les certificats système.

Avec Python 3.13 ou plus récent et les fuseaux horaires installés :

```sh
python -m unittest discover -s tests -v
```

Pour construire localement au lieu d'utiliser GHCR :

```sh
docker compose -f compose.yaml -f compose.build.yaml build
docker compose -f compose.yaml -f compose.build.yaml up -d
```

### Publication automatique

Le workflow [Tests, Docker et versions](.github/workflows/docker.yml) :

1. Construit l'image et exécute les tests dans un conteneur Linux isolé.
2. Sur `main`, publie l'image `edge` et celle du commit.
3. Sur un tag `vX.Y.Z` correspondant à la version du code, publie les images AMD64 / ARM64 avec leurs étiquettes de version et `latest`.
4. Crée la version GitHub avec une archive d'installation et `SHA256SUMS`.

Les pull requests exécutent les tests sans publier d'image. La publication utilise le `GITHUB_TOKEN` temporaire de GitHub Actions ; aucun secret personnel du NAS n'est nécessaire.

Pour préparer une nouvelle version : mets à jour `cesoir/__init__.py` et `CHANGELOG.md`, committe, puis pousse le commit et son tag correspondant. Exemple après passage du code en `1.2.1` :

```sh
git tag -a v1.2.1 -m "Version 1.2.1"
git push origin main v1.2.1
```

## Validation et limites

Les tests automatiques couvrent notamment la synchronisation sans doublons, les homonymes, les remakes, la pagination, les pannes, le cache, les horaires, l'authentification et la simulation. La lecture du guide TNT réel du 25 octobre 2026 a également été vérifiée.

Les échanges de synchronisation sont testés avec un serveur simulé. Le défaut de lecture des collections avec une clé API a aussi été reproduit et corrigé sur un serveur Jellyfin 12.3.0 local, avec des films factices et deux profils. La validation finale sur ton propre serveur et ton application TV reste à faire après configuration.

Sources techniques : [API des collections](https://github.com/jellyfin/jellyfin/blob/master/Jellyfin.Api/Controllers/CollectionController.cs), [API des éléments](https://github.com/jellyfin/jellyfin/blob/master/Jellyfin.Api/Controllers/ItemsController.cs), [format XMLTV](https://github.com/XMLTV/xmltv/blob/master/xmltv.dtd).

Licence [MIT](LICENSE).
