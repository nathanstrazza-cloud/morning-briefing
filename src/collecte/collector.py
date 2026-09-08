"""Orchestrateur de l'étape COLLECTE (cf. cahier §17). Appelle tous les sous-collecteurs
et renvoie une structure unique. Chaque sous-collecteur est indépendant et n'échoue jamais
bruyamment : une source en panne ne bloque pas les autres (cf. cahier §21).
"""
from __future__ import annotations

import logging
from datetime import datetime

from . import markets, rss_sources, sports, weather

logger = logging.getLogger("morning_briefing.collecte")


def collect_all(config: dict, depuis: datetime, is_monday: bool) -> dict:
    logger.info("Début de la collecte (depuis=%s, lundi=%s)", depuis.isoformat(), is_monday)

    news = rss_sources.fetch_all_news(config, depuis=depuis)
    sport = sports.fetch_sport(config, depuis=depuis)
    marches = markets.fetch_all_markets(config)
    meteo = weather.fetch_all_weather(config)

    total_news = sum(len(v) for v in news.values())
    total_sport = sum(len(v) for v in sport.values())
    logger.info(
        "Collecte terminée: %d actualités, %d items sport, %d indices, %d villes météo",
        total_news, total_sport, len(marches.get("indices", [])), len(meteo),
    )

    return {
        "news": news,        # {"france": [...], "monde": [...], "economie": [...], "sciences": [...]}
        "sport": sport,      # {"football": [...], "basketball": [...], ...}
        "marches": marches,  # {"indices": [...], "matieres_premieres": [...]}
        "meteo": meteo,      # [{"ville": ..., ...}, ...]
    }
