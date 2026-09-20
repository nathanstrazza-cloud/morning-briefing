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

    # cf. rss_sources.fetch_feed : chaque flux RSS interrogé (actu + sport) ajoute ici une
    # entrée décrivant son statut (ok/vide/erreur, code HTTP, détail) -- remonté ensuite
    # jusqu'à status.json par main.py (cf. cahier §22 journalisation). Permet de voir d'un
    # coup d'œil quels flux sont morts sans rouvrir les logs bruts.
    rss_diagnostics: list[dict] = []

    news = rss_sources.fetch_all_news(config, depuis=depuis, diagnostics=rss_diagnostics)
    sport = sports.fetch_sport(config, depuis=depuis, diagnostics=rss_diagnostics)
    marches = markets.fetch_all_markets(config)
    meteo = weather.fetch_all_weather(config)

    total_news = sum(len(v) for v in news.values())
    total_sport = sum(len(v) for v in sport.values())
    sources_en_erreur = [d["source"] for d in rss_diagnostics if d["statut"] == "erreur"]
    logger.info(
        "Collecte terminée: %d actualités, %d items sport, %d indices, %d villes météo",
        total_news, total_sport, len(marches.get("indices", [])), len(meteo),
    )
    if sources_en_erreur:
        logger.warning("Flux RSS en échec ce run: %s", ", ".join(sources_en_erreur))

    return {
        "news": news,        # {"france": [...], "monde": [...], "economie": [...], "sciences": [...]}
        "sport": sport,      # {"football": [...], "basketball": [...], ...}
        "marches": marches,  # {"indices": [...], "matieres_premieres": [...]}
        "meteo": meteo,      # [{"ville": ..., ...}, ...]
        "rss_diagnostics": rss_diagnostics,  # cf. ci-dessus, propagé jusqu'à status.json
    }
