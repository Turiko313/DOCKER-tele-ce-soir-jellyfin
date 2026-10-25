# Historique des versions

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
