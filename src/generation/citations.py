"""Citation du jour : tirage DÉTERMINISTE dans une banque de citations vérifiées (config/citations.json).

Pourquoi (analyse du 01/10, point 6) : demander une citation « authentique » à un petit LLM aboutit à
`null` chaque jour (ou, pire, à une attribution douteuse). Le cahier §9 exige l'authenticité : la
banque est écrite et vérifiée à la main, le code ne fait que choisir (jour de l'année modulo taille,
donc aucune répétition avant d'avoir épuisé la banque). Aucun appel réseau ni LLM.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger("morning_briefing.generation")
BANQUE = Path(__file__).resolve().parents[2] / "config" / "citations.json"


def load_bank(path: Path = BANQUE) -> list[dict]:
    try:
        items = json.loads(path.read_text(encoding="utf-8")).get("citations", [])
    except (OSError, ValueError) as exc:
        logger.warning("Banque de citations illisible (%s) : %s", path, exc)
        return []
    return [c for c in items if c.get("texte") and c.get("auteur") and c.get("source")]


def pick_citation(jour: date, bank: list[dict] | None = None) -> dict | None:
    bank = load_bank() if bank is None else bank
    if not bank:
        return None
    c = bank[jour.toordinal() % len(bank)]
    return {"texte": c["texte"], "auteur": c["auteur"], "source": c["source"], "annee": c.get("annee")}
