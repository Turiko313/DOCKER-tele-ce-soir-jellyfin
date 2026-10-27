# Historique des versions

## 1.3.0 — 2026-10-27

- Détection des films classés seulement « Comédie », « Drame », « Comédie dramatique », « Western » et autres genres de cinéma ; maintien de l'exclusion des séries, documentaires et spectacles.
- Vérification d'identité via les métadonnées pour ces nouveaux genres lorsque l'année et les identifiants manquent, même si un seul titre identique est possédé. Une version absente n'est pas remplacée par un remake présent ; les correspondances manuelles restent prioritaires.
- Reconnaissance des variantes françaises d'ordinaux (`1re` / `1ère partie`), avec conservation des numéros de parties et de suites.
- Recherche des alias bilingues entre parenthèses, comme `L'Intermédiaire (Relay)` : les deux noms doivent désigner la même œuvre. Le titre original de la fiche locale peut compléter un résultat distant incomplet uniquement via un identifiant confirmé et une année compatible.
- Rapprochement des résultats TMDb et IMDb par les paires d'identifiants cohérentes déjà connues de Jellyfin, sans fusionner des œuvres sur leur seul titre ou leur année.
- Vérification de tous les lots de recherche d'un titre sans année avant de conclure ; prise en compte des synopsis courts suffisamment distinctifs pour départager les homonymes.
- Refus d'un guide dépourvu de catégories pour éviter de vider la collection sur un flux incompatible ; recours au guide en cache valide lorsqu'il existe.
- Rapport et journaux indiquant les candidats détectés par leur genre et les identités à confirmer lorsque la recherche de métadonnées est désactivée.
- Cas de régression issus de l'audit sur cinq soirées ; validation complémentaire des captures, documentée dans `docs/validation-1.3.0.md`. Aucun nouveau fournisseur de grille activé.

## 1.2.0 — 2026-10-26

- Plage par défaut étendue à 20 h–4 h, avec maintien de la soirée précédente après minuit jusqu'à 4 h. Surcharge possible par `TV_START` et `TV_END` dans Compose.
- Reconnaissance des titres avec année, mentions VF/VOST/version restaurée, chiffres romains et caractères non latins.
- Secours par nom de fichier et année ; prise en compte des identifiants TMDb/IMDb présents dans les noms de fichiers, sans écraser les identifiants contradictoires de Jellyfin.
- Recherche des titres alternatifs en français et anglais ; seconde recherche sans filtre d'année pour vérifier les écarts de production/sortie d'un an à l'aide des identifiants.
- Exploitation des réalisateurs du guide et des résumés suffisamment distinctifs pour départager les homonymes ; maintien du refus lorsque plusieurs versions restent possibles.
- Comparaison prudente des titres proches : année connue identique, similarité d'au moins 94 %, nombres de suites identiques et écart suffisant avec les autres candidats. Désactivable avec `APPROXIMATE_MATCHING=false`.
- Suggestions de films proches dans le rapport et les journaux, explicitement non ajoutées lorsqu'elles ne remplissent pas les conditions.
- Renforcement des contrôles d'identité : un identifiant commun ne masque plus un identifiant contradictoire chez un autre fournisseur, et une recherche de métadonnées ne se rabat plus sur un titre local en prétendant avoir confirmé un identifiant.
- Exclusion des making-of classés seulement « cinéma / doc cinéma », conservation des films documentaires explicitement identifiés comme films.
- Cache de recherche mis à jour pour inclure la langue et les résumés ; caches bornés des formes de titres pour éviter les calculs répétés.

## 1.1.0 — 2026-10-25

- Recherche des titres TV non reconnus via les fournisseurs de métadonnées déjà configurés dans Jellyfin, sans nouvelle clé API.
- Correspondance entre traductions uniquement si un résultat exact et non ambigu fournit un identifiant TMDb/IMDb présent dans la médiathèque ; vérification de l'année lorsqu'elle est fournie.
- Rejet des remakes et homonymes non départagés, des titres seulement ressemblants et des identifiants contradictoires.
- Cache de recherche de 24 heures, limité à 500 recherches ; secours de sept jours en cas de panne, puis conservation de la collection si les recherches restent indisponibles.
- Motifs distinguant un film identifié sans identifiant local, une recherche non concluante et des métadonnées ambiguës.
- Fonction activée par défaut, désactivable avec `metadata_lookup: false` ou `METADATA_LOOKUP=false`. Aucune application de métadonnées aux films.
- API de recherche vérifiée sur le serveur Jellyfin ; simulation de la soirée et contrôle des homonymes sans modification de la médiathèque.

## 1.0.3 — 2026-10-25

- Journaux détaillant chaque diffusion retenue ou écartée : date, horaire, chaîne, titre, année disponible et motif d'exclusion.
- Bilan distinguant le nombre de films, les diffusions et les changements réellement effectués ; une collection sans modification est annoncée comme inchangée.
- Détails affichés au démarrage ou lors d'un changement ; bilan compact aux contrôles identiques suivants.
- Rapport enrichi avec les horaires des exclusions, les motifs regroupés et le nombre de diffusions retenues.
- Démarrages rapprochés identifiés, intervalle de contrôle affiché et arrêt normal signalé pour faciliter le diagnostic des relances Docker/OMV.
- Conservation des règles prudentes de correspondance : aucun ajout fondé sur un titre simplement ressemblant.

## 1.0.2 — 2026-10-25

- Correction de la lecture des collections avec une clé API : les films liés sont maintenant récupérés avec une requête récursive, sans regroupement en collections.
- Confirmation des ajouts avant le retrait des anciens films, avec de brèves nouvelles lectures si la mise à jour n'est pas encore visible.
- Messages de vérification indiquant les nombres d'éléments attendus, manquants et inattendus.
- Affichage de la version de l'extension au démarrage.
- Problème reproduit puis correction vérifiée sur un serveur Jellyfin 12.3.0 local avec deux profils.

## 1.0.1 — 2026-10-25

- Dépôt renommé en `Turiko313/DOCKER-tele-ce-soir-jellyfin`.
- Image publiée sous `ghcr.io/turiko313/docker-tele-ce-soir-jellyfin`.
- README et fichiers Docker alignés sur le nom définitif.

## 1.0.0 — 2026-10-25

- Création et actualisation d'une collection Jellyfin « Films à la télé ce soir ».
- Films de la médiathèque diffusés entre 20 h et 2 h, à partir du guide XMLTV TNT.
- Correspondances par identifiants ou titres normalisés, avec rejet des homonymes ambigus.
- Cache du programme, gestion des fuseaux horaires, simulation et rapports locaux.
- Images Docker AMD64 et ARM64 construites automatiquement par GitHub Actions.
- Publication des versions GitHub et des images sur GHCR après réussite des tests.
- Notice française et explication du titre de tri pour placer la collection en tête de liste.
