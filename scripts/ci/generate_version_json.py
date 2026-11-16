#!/usr/bin/env python3
"""Genera version.json y las notas del release a partir del build actual.

La versión se toma de app/version.py (X.Y.Z) y el instalador se publica en
GitHub Releases. Las notas se construyen con los commits no-merge desde el
release anterior.

Uso:
    python scripts/ci/generate_version_json.py \
        --version 0.2.0 \
        --tag v0.2.0 \
        --repository Louis-Du/sena-certificacion-app \
        --installer dist/installer/SENACertificacion-Setup-0.2.0.exe \
        --output dist/installer/version.json \
        --notes-output dist/installer/release_notes.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

MAX_COMMITS = 50
FALLBACK_COMMITS = 20
MAX_SUBJECT_LENGTH = 200


def run_git(*args: str) -> str:
    """Ejecuta git y devuelve stdout; una cadena vacía si el comando falla."""
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def previous_release_tag(current_tag: str) -> str | None:
    """Tag de release inmediatamente anterior alcanzable desde HEAD^."""
    tag = run_git("describe", "--tags", "--abbrev=0", "--match", "v*", "HEAD^")
    if tag and tag != current_tag:
        return tag
    return None


def commit_subjects(previous_tag: str | None) -> list[str]:
    """Asuntos de commits no-merge desde el release anterior (o el inicio)."""
    range_spec = f"{previous_tag}..HEAD" if previous_tag else "HEAD"
    output = run_git(
        "log",
        "--no-merges",
        f"--max-count={MAX_COMMITS}",
        "--pretty=format:%s",
        range_spec,
    )
    subjects = [line.strip() for line in output.splitlines() if line.strip()]

    # Un re-run sobre un tag existente puede dejar el rango vacío; se usa el
    # historial reciente para no publicar notas vacías.
    if not subjects:
        output = run_git(
            "log",
            "--no-merges",
            f"--max-count={FALLBACK_COMMITS}",
            "--pretty=format:%s",
            "HEAD",
        )
        subjects = [line.strip() for line in output.splitlines() if line.strip()]

    cleaned: list[str] = []
    for subject in subjects:
        subject = " ".join(subject.split())
        if len(subject) > MAX_SUBJECT_LENGTH:
            subject = subject[: MAX_SUBJECT_LENGTH - 1].rstrip() + "…"
        cleaned.append(subject)
    return cleaned


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="Versión X.Y.Z del release")
    parser.add_argument("--tag", required=True, help="Tag del release, por ejemplo v0.2.0")
    parser.add_argument("--repository", required=True, help="Repositorio owner/repo")
    parser.add_argument("--installer", required=True, type=Path, help="Instalador .exe generado")
    parser.add_argument("--output", required=True, type=Path, help="Ruta de version.json")
    parser.add_argument("--notes-output", required=True, type=Path, help="Ruta de las notas del release")
    args = parser.parse_args()

    installer = args.installer.resolve()
    if not installer.is_file():
        raise SystemExit(f"No existe el instalador: {installer}")

    url = f"https://github.com/{args.repository}/releases/download/{args.tag}/{installer.name}"
    digest = sha256_of(installer)
    subjects = commit_subjects(previous_release_tag(args.tag))
    notes = "\n".join(f"- {subject}" for subject in subjects) or "- Sin cambios registrados."
    pub_date = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    metadata = {
        "version": args.version,
        "pub_date": pub_date,
        "url": url,
        "notes": notes,
        "sha256": digest,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    release_notes = (
        f"## SENA Certificación {args.version}\n\n"
        "### Cambios\n\n"
        f"{notes}\n\n"
        f"**Instalador:** [{installer.name}]({url})\n\n"
        f"**SHA-256:** `{digest}`\n"
    )
    args.notes_output.parent.mkdir(parents=True, exist_ok=True)
    args.notes_output.write_text(release_notes, encoding="utf-8")

    print(f"version.json: {args.output}")
    print(f"notas:        {args.notes_output}")
    print(f"url:          {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
