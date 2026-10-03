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

SIMILARITY_THRESHOLD = 0.28

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


def merge_zones(events_france: list[dict], events_monde: list[dict]) -> tuple[list[dict], list[dict]]:
    """Déduplication INTER-zones (correctif du 03/10/2026, point 4 de l'analyse du 01/10).

    Avant : `deduplicate` était appelé séparément pour France et Monde, donc un même événement
    (Powell/Fed, Hegseth, Christa Pike...) apparaissait dans les deux zones, parfois avec deux
    statuts différents (fait confirmé côté Monde, information rapportée côté France).

    Règle : un événement présent dans les deux flux est international (le flux « monde » l'a
    couvert) -> il est conservé dans MONDE avec l'union des sources (donc le bon nombre de
    sources pour la vérification) et retiré de FRANCE. Les événements propres à chaque zone
    ne bougent pas. Fonction pure : ne modifie pas les listes passées en entrée.
    """
    monde = [dict(e, sources=list(e["sources"])) for e in events_monde]
    france: list[dict] = []
    fusionnes = 0
    for ef in events_france:
        cible = next((em for em in monde if _similarity(ef["titre"], em["titre"]) >= SIMILARITY_THRESHOLD), None)
        if cible is None:
            france.append(ef)
            continue
        fusionnes += 1
        deja = {x["nom"] for x in cible["sources"]}
        for src in ef["sources"]:
            if src["nom"] not in deja:
                cible["sources"].append(src)
                deja.add(src["nom"])
        cible["nb_sources"] = len(cible["sources"])
        if not cible.get("resume") and ef.get("resume"):
            cible["resume"] = ef["resume"]
        dates = [d for d in (cible.get("date_publication"), ef.get("date_publication")) if d]
        cible["date_publication"] = min(dates) if dates else None
    logger.info("Déduplication inter-zones: %d événement(s) France fusionné(s) dans Monde", fusionnes)
    return france, monde
