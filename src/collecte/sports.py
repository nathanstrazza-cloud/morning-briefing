"""Collecte sportive généraliste (refonte du 05/10/2026) : TOUS les sports, sans préférence utilisateur.

Config `sport.sources` : liste de flux `{name, url, sport?}`. `sport` est un indice facultatif (flux
dédié à un sport) ; sans indice, le sport est détecté par mots-clés (analyse/sport_scoring.detecter_sport).
Plus de filtre « France », plus d'équipe prioritaire. Retourne une LISTE d'items bruts avec le champ `sport`.
"""
from __future__ import annotations

import logging
from datetime import datetime

from ..analyse.sport_scoring import detecter_sport
from .rss_sources import fetch_feed

logger = logging.getLogger("morning_briefing.collecte.sports")


def fetch_sport(config: dict, depuis: datetime | None = None, diagnostics: list[dict] | None = None) -> list[dict]:
    sources = (config.get("sport") or {}).get("sources") or []
    items: list[dict] = []
    for src in sources:
        for it in fetch_feed(src["url"], src["name"], "sport", diagnostics=diagnostics):
            if depuis is not None and it["date_publication"] is not None and it["date_publication"] < depuis:
                continue
            it["sport"] = detecter_sport(it["titre"], it["resume"], src.get("sport"))
            items.append(it)
    par_sport: dict[str, int] = {}
    for it in items:
        par_sport[it["sport"]] = par_sport.get(it["sport"], 0) + 1
    logger.info("Sport collecté: %d items %s", len(items), par_sport)
    return items
