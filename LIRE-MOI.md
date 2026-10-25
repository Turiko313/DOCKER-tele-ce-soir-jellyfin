# Installation rapide

La notice complète est dans le [README en français](README.md).

1. Copie `.env.example` vers `.env` et renseigne l'adresse de ton Jellyfin.
2. Copie `jellyfin-api-key.txt.example` vers `jellyfin-api-key.txt` et remplace son contenu par une clé API créée dans Jellyfin.
3. Crée un projet Docker sur ton NAS avec le fichier `compose.yaml`, puis démarre-le.
4. Sur la télévision, ouvre **Jellyfin → Collections → Films à la télé ce soir**.

Avec un terminal, après avoir rempli les deux fichiers :

```sh
docker compose pull
docker compose up -d
docker compose logs --tail=50 ce-soir
```

L'image Docker publiée est `ghcr.io/turiko313/ce-soir-jellyfin:latest`. Elle est proposée pour les NAS AMD64 et ARM64.

Pour placer la collection avant les noms alphabétiques habituels : depuis Jellyfin dans un navigateur, ouvre **⋮ → Éditer les métadonnées** sur la collection, puis mets `000 - Films à la télé ce soir` dans **Titre de tri**. Sur Android TV, choisis le tri par **Nom** en ordre croissant.
