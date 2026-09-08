"""Collecte des marchés financiers via Stooq (CSV public, gratuit, sans clé API).

cf. cahier §5 : ne pas se contenter de la variation chiffrée, chercher une explication
si le mouvement est inhabituel. Ce module fournit uniquement les CHIFFRES bruts et fiables
(cours actuel, cours précédent, variation %). L'explication ("pourquoi le marché a bougé")
est déléguée au LLM en génération, à partir des articles économiques collectés par
rss_sources.py — jamais inventée ici.
"""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger("morning_briefing.collecte.markets")

STOOQ_URL = "https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"


def fetch_quote(name: str, symbol: str, timeout: int = 10) -> dict | None:
    """Récupère la dernière cotation (clôture + veille) pour un symbole Stooq.

    Retourne None en cas d'échec (ne jamais inventer une valeur, cf. cahier §21).
    """
    try:
        resp = requests.get(STOOQ_URL.format(symbol=symbol), timeout=timeout)
        resp.raise_for_status()
        lines = resp.text.strip().splitlines()
        if len(lines) < 2:
            logger.warning("Réponse Stooq vide pour %s (%s)", name, symbol)
            return None
        headers = [h.strip().lower() for h in lines[0].split(",")]
        values = lines[1].split(",")
        row = dict(zip(headers, values))

        close = row.get("close")
        open_ = row.get("open")
        if close in (None, "N/D", "") or open_ in (None, "N/D", ""):
            logger.warning("Données Stooq incomplètes pour %s (%s): %s", name, symbol, row)
            return None

        close_f = float(close)
        open_f = float(open_)
        variation_pct = ((close_f - open_f) / open_f) * 100 if open_f else None

        return {
            "name": name,
            "symbol": symbol,
            "cours": close_f,
            "ouverture": open_f,
            "variation_pct": round(variation_pct, 2) if variation_pct is not None else None,
            "date": row.get("date"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Échec récupération cotation %s (%s): %s", name, symbol, exc)
        return None


def fetch_all_markets(config: dict) -> dict[str, list[dict]]:
    marches_config = config.get("marches", {})
    resultat: dict[str, list[dict]] = {"indices": [], "matieres_premieres": []}

    for entry in marches_config.get("indices", []):
        quote = fetch_quote(entry["name"], entry["symbol"])
        if quote:
            resultat["indices"].append(quote)

    for entry in marches_config.get("matieres_premieres", []):
        quote = fetch_quote(entry["name"], entry["symbol"])
        if quote:
            resultat["matieres_premieres"].append(quote)

    logger.info(
        "Marchés collectés: %d indices, %d matières premières",
        len(resultat["indices"]),
        len(resultat["matieres_premieres"]),
    )
    return resultat


def significant_moves(markets: dict, seuil_pct: float) -> list[dict]:
    """Filtre les mouvements jugés dignes d'être commentés (cf. cahier §5)."""
    all_quotes = markets.get("indices", []) + markets.get("matieres_premieres", [])
    return [q for q in all_quotes if q.get("variation_pct") is not None and abs(q["variation_pct"]) >= seuil_pct]
