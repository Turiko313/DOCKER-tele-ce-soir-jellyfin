# Historique des versions

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
