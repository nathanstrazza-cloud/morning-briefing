"""Déduplication : plusieurs médias qui parlent du même événement doivent devenir
1 seul événement avec plusieurs sources associées (cf. cahier §12).

Approche V1 volontairement simple (heuristique par similarité de titres), pas de LLM ni
d'embeddings pour rester à 0€ et rapide. À affiner en roadmap si les faux doublons/négatifs
sont trop fréquents (cf. README §7).
"""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

logger = logging.getLogger("morning_briefing.analyse.dedup")

SIMILARITY_THRESHOLD = 0.4

STOPWORDS_FR = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "en", "sur", "pour",
    "dans", "au", "aux", "à", "que", "qui", "ce", "cette", "ces", "son", "sa", "ses",
    "avec", "par", "est", "sont", "a", "ont", "se", "il", "elle", "ils", "elles",
}


def _normalize(text: str) -> set[str]:
    words = re.findall(r"[a-zàâäéèêëïîôöùûüç0-9]+", text.lower())
    return {w for w in words if w not in STOPWORDS_FR and len(w) > 2}


def _similarity(a: str, b: str) -> float:
    set_a, set_b = _normalize(a), _normalize(b)
    if not set_a or not set_b:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
    jaccard = len(set_a & set_b) / len(set_a | set_b)
    return jaccard


def deduplicate(items: list[dict]) -> list[dict]:
    """Regroupe les items similaires en 'événements' avec une liste de sources.

    Entrée : liste d'items bruts (cf. rss_sources.py pour le format).
    Sortie : liste d'événements :
    {
        "titre": str,               # titre représentatif (le plus long, souvent le plus complet)
        "resume": str,
        "url_principale": str,
        "categorie": str,
        "sources": [{"nom": str, "url": str}, ...],
        "nb_sources": int,
        "date_publication": datetime | None,   # la plus ancienne connue
    }
    """
    events: list[dict] = []

    for item in items:
        match = None
        for event in events:
            if event["categorie"] != item["categorie"]:
                continue
            if _similarity(event["titre"], item["titre"]) >= SIMILARITY_THRESHOLD:
                match = event
                break

        if match is None:
            events.append(
                {
                    "titre": item["titre"],
                    "resume": item["resume"],
                    "url_principale": item["url"],
                    "categorie": item["categorie"],
                    "sources": [{"nom": item["source"], "url": item["url"]}],
                    "nb_sources": 1,
                    "date_publication": item["date_publication"],
                }
            )
        else:
            already = {s["nom"] for s in match["sources"]}
            if item["source"] not in already:
                match["sources"].append({"nom": item["source"], "url": item["url"]})
                match["nb_sources"] += 1
            if len(item["titre"]) > len(match["titre"]):
                match["titre"] = item["titre"]
            if not match["resume"] and item["resume"]:
                match["resume"] = item["resume"]
            if item["date_publication"] and (
                match["date_publication"] is None or item["date_publication"] < match["date_publication"]
            ):
                match["date_publication"] = item["date_publication"]

    logger.info("Déduplication: %d items bruts -> %d événements uniques", len(items), len(events))
    return events
