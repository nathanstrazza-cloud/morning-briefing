"""Étape STOCKAGE (cf. cahier §16-17) : sauvegarde du briefing sous forme JSON structurée,
conserve l'historique, ne supprime jamais d'anciens briefings.

Fichiers produits dans data/briefings/ :
- YYYY-MM-DD.json   : le briefing complet de ce jour (permanent, jamais écrasé)
- latest.json       : copie du dernier briefing réussi (lu par la page d'accueil)
- index.json        : liste de toutes les dates disponibles, pour l'historique (§16)
- status.json       : statut du dernier run (succès/échec) affiché par le frontend (§21)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("morning_briefing.stockage")

# Les données vivent sous docs/ pour que GitHub Pages (mode "Deploy from branch -> /docs")
# puisse servir le frontend ET les données JSON ensemble, gratuitement, sans workflow de
# déploiement supplémentaire (cf. README §6).
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "data" / "briefings"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_briefing(briefing: dict, date_iso: str, last_update_iso: str) -> None:
    """Sauvegarde le briefing du jour + met à jour latest.json et index.json.
    N'écrase JAMAIS un fichier de date existant avec un contenu vide (sécurité supplémentaire)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    enveloppe = {
        "date": date_iso,
        "derniere_mise_a_jour": last_update_iso,
        "briefing": briefing,
    }

    day_path = DATA_DIR / f"{date_iso}.json"
    _write_json(day_path, enveloppe)
    _write_json(DATA_DIR / "latest.json", enveloppe)

    _update_index(date_iso)
    _write_status(succes=True, date_iso=date_iso, last_update_iso=last_update_iso)
    logger.info("Briefing sauvegardé: %s", day_path)


def _update_index(date_iso: str) -> None:
    index_path = DATA_DIR / "index.json"
    index = _read_json(index_path) or {"dates": []}
    if date_iso not in index["dates"]:
        index["dates"].append(date_iso)
        index["dates"].sort(reverse=True)
    _write_json(index_path, index)


def _write_status(succes: bool, date_iso: str, last_update_iso: str, erreur: str | None = None) -> None:
    _write_json(
        DATA_DIR / "status.json",
        {
            "derniere_execution": last_update_iso,
            "date_visee": date_iso,
            "succes": succes,
            "erreur": erreur,
        },
    )


def record_failure(date_iso: str, last_update_iso: str, erreur: str) -> None:
    """Cf. cahier §21 : si tout échoue, on NE TOUCHE PAS à latest.json — le dernier
    briefing valide reste affiché. On journalise seulement l'échec dans status.json."""
    logger.error("Échec du run pour %s: %s — dernier briefing valide conservé.", date_iso, erreur)
    _write_status(succes=False, date_iso=date_iso, last_update_iso=last_update_iso, erreur=erreur)
