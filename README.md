# Films à la télé ce soir

[![Tests et Docker](https://github.com/Turiko313/ce-soir-jellyfin/actions/workflows/docker.yml/badge.svg)](https://github.com/Turiko313/ce-soir-jellyfin/actions/workflows/docker.yml)
[![Version](https://img.shields.io/github/v/release/Turiko313/ce-soir-jellyfin)](https://github.com/Turiko313/ce-soir-jellyfin/releases/latest)

Retrouve dans **Jellyfin → Collections → Films à la télé ce soir** les films de ta médiathèque qui passent à la télévision pendant la soirée.

L'extension compare le programme TV à ta médiathèque et actualise une collection Jellyfin. Sur Android TV, tu retrouves les affiches, les fiches et la lecture de tes propres fichiers, à l'heure qui te convient.

Elle tourne dans un conteneur Docker supplémentaire sur le NAS et utilise l'API de Jellyfin. La page est celle d'une collection : elle n'ajoute pas d'onglet ou de rangée personnalisée à l'accueil de l'application TV. Les chaînes et horaires sont disponibles dans les journaux et le rapport de l'extension, pas sur les affiches.

## Fonctionnement par défaut

- Programme du [guide TNT de XML TV Fr](https://xmltvfr.fr/xmltv.php), sans clé de fournisseur TV.
- Films et téléfilms dont la diffusion commence entre **20 h et 2 h**, heure de Paris.
- Mise à jour toutes les **15 minutes** ; rafraîchissement du programme toutes les **12 heures** en fonctionnement normal.
- Après minuit, conservation de la soirée précédente jusqu'à 2 h.
- Affichage des seuls films déjà présents dans la médiathèque ; aucun téléchargement de films.
- Correspondances par IMDb/TMDb, ou par titre normalisé et année lorsque les données sont disponibles. Les homonymes ambigus sont écartés.
- Images Docker pour **Linux AMD64 et ARM64**, construites automatiquement après réussite des tests.

## Installation Docker sur le NAS

### 1. Télécharger le projet

Télécharge l'archive de la [dernière version](https://github.com/Turiko313/ce-soir-jellyfin/releases/latest) et extrais-la dans un dossier du NAS, par exemple `docker/ce-soir-jellyfin`.

Tu peux aussi cloner le dépôt :

```sh
git clone https://github.com/Turiko313/ce-soir-jellyfin.git
cd ce-soir-jellyfin
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
ghcr.io/turiko313/ce-soir-jellyfin:latest
```

| Étiquette | Contenu |
| --- | --- |
| `latest` | Dernière version stable publiée. |
| `1.0.0` | Version précise, à utiliser pour figer une installation. |
| `1.0`, `1` | Dernière version publiée dans cette branche de versions. |
| `edge` | Dernier commit de `main` ayant passé les tests. |
| `sha-…` | Image associée à un commit précis. |

Pour figer une version, indique par exemple `CESOIR_VERSION=1.0.0` dans `.env`. Pour appliquer une nouvelle image :

```sh
docker compose pull
docker compose up -d
```

Les données de suivi sont conservées dans le volume `ce-soir-data`.

## Régler les chaînes et les horaires

Modifie `config.json`, puis redémarre le conteneur avec `docker compose restart ce-soir`. Conserve un JSON valide avec ses guillemets et virgules.

| Réglage | Rôle |
| --- | --- |
| `start`, `end` | Plage de début des diffusions, par défaut `"20:00"` à `"02:00"`. |
| `timezone` | Fuseau horaire, `"Europe/Paris"` par défaut. |
| `channels` | `[]` prend toutes les chaînes du fichier choisi ; une liste limite la sélection. |
| `include_tv_movies` | `true` inclut les téléfilms ; `false` les écarte. |
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

### Corriger un titre non reconnu

Le titre français ou original doit être identique après normalisation des accents, de la casse et de la ponctuation. Si deux films portent le même titre sans informations suffisantes pour les distinguer, l'extension les écarte.

Une traduction différente peut être associée manuellement à un film :

```json
"title_overrides": {
  "Le titre utilisé dans le programme TV": "0123456789abcdef0123456789abcdef"
}
```

Remplace l'identifiant d'exemple par celui de ton film, visible dans l'adresse de sa fiche ouverte depuis le navigateur. La cible doit être un film trouvé dans ta médiathèque.

## Données et comportement en cas de panne

L'extension gère uniquement les **liens vers des films dans sa collection**. Elle ne supprime pas de vidéos et ne modifie pas les titres, résumés ou affiches des films.

La collection est partagée au niveau du serveur. Jellyfin applique les droits et restrictions de chaque utilisateur ; l'extension ne gère pas de sélection personnelle par compte.

Si la lecture du guide ou de la médiathèque échoue, la sélection précédente est conservée. Elle peut donc correspondre à une ancienne soirée pendant une panne. Le cache ne sert que s'il couvre encore la soirée et reste assez récent. Si un guide valide couvre la soirée mais qu'aucun film ne correspond, la collection existante est vidée de ses liens.

Le volume `ce-soir-data` contient :

- `state.json` : serveur et collection gérée, à conserver entre les redémarrages.
- `report.json` : dernier résultat réussi, films, chaînes, horaires et correspondances écartées.
- `preview.json` : dernière simulation.
- `guide.xml` et `guide-cache.json` : programme mis en cache.
- `health.json` : résultat du dernier passage, utilisé pour l'état de santé Docker.

Une seule instance peut utiliser ce volume. Pour une simulation après installation, arrête d'abord le service avec `docker compose stop ce-soir`, lance la commande `--dry-run`, puis redémarre avec `docker compose up -d`.

## Dépannage

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

Pour préparer une nouvelle version : mets à jour `cesoir/__init__.py` et `CHANGELOG.md`, committe, puis pousse le commit et son tag correspondant. Exemple après passage du code en `1.0.1` :

```sh
git tag -a v1.0.1 -m "Version 1.0.1"
git push origin main v1.0.1
```

## Validation et limites

31 tests automatiques couvrent notamment la synchronisation sans doublons, les homonymes, les remakes, la pagination, les pannes, le cache, les horaires, l'authentification et la simulation. La lecture du guide TNT réel du 25 octobre 2026 a également été vérifiée.

Les échanges de synchronisation sont testés avec un serveur Jellyfin simulé et les routes ont été vérifiées dans le code officiel. La validation finale sur ton propre serveur et ton application TV reste à faire après configuration.

Sources techniques : [API des collections](https://github.com/jellyfin/jellyfin/blob/master/Jellyfin.Api/Controllers/CollectionController.cs), [API des éléments](https://github.com/jellyfin/jellyfin/blob/master/Jellyfin.Api/Controllers/ItemsController.cs), [format XMLTV](https://github.com/XMLTV/xmltv/blob/master/xmltv.dtd).

Licence [MIT](LICENSE).
