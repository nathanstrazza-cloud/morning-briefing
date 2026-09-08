"""Collecte sportive : football, basketball (Spurs prioritaire), natation, autres sports
uniquement si la France est concernée (cf. cahier §6).

Utilise les mêmes flux RSS que rss_sources.py mais applique les règles métier du cahier
des charges (équipe prioritaire, sports conditionnels à la présence de la France).
"""
from __future__ import annotations

import logging
from datetime import datetime

from .rss_sources import fetch_feed

logger = logging.getLogger("morning_briefing.collecte.sports")


def _contains_any(text: str, keywords: list[str]) -> bool:
    text_low = text.lower()
    return any(kw.lower() in text_low for kw in keywords)


def fetch_sport(config: dict, depuis: datetime | None = None) -> dict[str, list[dict]]:
    sport_config = config.get("sport", {})
    equipes_prio = sport_config.get("equipes_prioritaires", {})
    sports_conditionnels = sport_config.get("sports_conditionnels", [])
    mots_france = sport_config.get("mot_cle_france", ["France"])

    resultat: dict[str, list[dict]] = {}

    for categorie in ("football", "basketball", "natation", "autres"):
        sources = sport_config.get(categorie, [])
        items: list[dict] = []
        for src in sources:
            items.extend(fetch_feed(src["url"], src["name"], f"sport_{categorie}"))

        if depuis is not None:
            items = [
                it
                for it in items
                if it["date_publication"] is None
                or it["date_publication"].replace(tzinfo=None) >= depuis.replace(tzinfo=None)
            ]

        if categorie == "basketball":
            spurs_kw = equipes_prio.get("basketball", [])
            for it in items:
                it["equipe_prioritaire"] = _contains_any(it["titre"] + " " + it["resume"], spurs_kw)

        resultat[categorie] = items

    # "Autres sports" (tennis, hand, volley, cyclisme, rugby) : ne garder que si la France
    # est explicitement mentionnée (cf. cahier §6 "Ne pas produire de veille quotidienne...").
    resultat["autres"] = [
        it for it in resultat.get("autres", []) if _contains_any(it["titre"] + " " + it["resume"], mots_france)
    ]

    logger.info(
        "Sport collecté: foot=%d basket=%d natation=%d autres(France)=%d",
        len(resultat.get("football", [])),
        len(resultat.get("basketball", [])),
        len(resultat.get("natation", [])),
        len(resultat.get("autres", [])),
    )
    return resultat
