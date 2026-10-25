"""Package tracked sources only. Local credentials and data are never included."""
from pathlib import Path
import hashlib
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cesoir import __version__


def main():
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    tracked = [name for name in tracked if name]
    forbidden = [name for name in tracked if name in {".env", "jellyfin-api-key.txt"}
                 or any(part in {"data", "dist", "__pycache__", "temporary"} for part in Path(name).parts)]
    if forbidden:
        raise SystemExit("Fichiers locaux interdits dans la version : " + ", ".join(forbidden))
    if not {"README.md", "compose.yaml", ".env.example", "jellyfin-api-key.txt.example"} <= set(tracked):
        raise SystemExit("Le dépôt ne contient pas tous les fichiers d'installation attendus.")
    output = ROOT / "dist"
    output.mkdir(exist_ok=True)
    archive = output / f"ce-soir-jellyfin-{__version__}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name in sorted(tracked):
            package.write(ROOT / name, "ce-soir-jellyfin/" + name)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (output / "SHA256SUMS").write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = f"## {__version__} —"
    sections = changelog.split("\n## ")
    changes = next((section.split("\n", 1)[1].strip() for section in sections[1:]
                    if ("## " + section).startswith(heading) and "\n" in section), "")
    if not changes:
        raise SystemExit(f"Entrée CHANGELOG.md absente pour {__version__}.")
    (output / "release-notes.md").write_text(
        f"Version **{__version__}** de Films à la télé ce soir.\n\n" + changes + "\n\n"
        "```sh\n"
        f"docker pull ghcr.io/turiko313/ce-soir-jellyfin:{__version__}\n"
        "```\n\n"
        "Téléchargez l'archive, copiez les deux fichiers `.example` vers leurs noms sans `.example`, "
        "renseignez l'adresse et la clé API de votre Jellyfin, puis lancez `docker compose up -d`.\n\n"
        "Consultez le [README](https://github.com/Turiko313/ce-soir-jellyfin#readme) pour l'installation, "
        "le tri de la collection et les réglages. Les données de votre NAS ne sont pas incluses.\n",
        encoding="utf-8",
    )
    print(f"Archive créée : {archive.name} ({len(tracked)} fichiers)")


if __name__ == "__main__":
    main()
