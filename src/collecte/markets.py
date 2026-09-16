"""Collecte des marchés financiers via l'endpoint public "chart" de Yahoo Finance
(gratuit, sans clé API, sans CAPTCHA).

NB (corrigé le 2026-09-13) : Stooq exige désormais une clé API obtenue manuellement via
CAPTCHA (changement constaté en avril 2026, cf. erreurs 404 sur tous les symboles dans les
logs depuis cette date) — cette source n'est donc plus utilisable gratuitement et sans
intervention humaine (cf. cahier §19 : 0€, pas de dépendance à une action manuelle
récurrente). Remplacée par l'API "chart" non-officielle de Yahoo Finance
(query1.finance.yahoo.com/v8/finance/chart/{symbol}), qui ne nécessite ni clé ni CAPTCHA et
reste la source gratuite la plus fiable à ce jour (c'est celle qu'utilise la librairie
`yfinance`). Elle reste non-officielle : Yahoo peut renvoyer un 429 en cas de sur-sollicitation
(peu probable ici, un run/jour, 7 symboles) ou, pour certaines IP UE, une page de consentement
HTML au lieu du JSON attendu — dans les deux cas le code ci-dessous échoue proprement
(JSON invalide/champs manquants -> None, jamais de valeur inventée, cf. cahier §21). Si cette
source devient à son tour peu fiable, prochaine option à explorer : Twelve Data (clé gratuite,
quota limité) ou Alpha Vantage (clé gratuite, quota très limité).

cf. cahier §5 : ne pas se contenter de la variation chiffrée, chercher une explication
si le mouvement est inhabituel. Ce module fournit uniquement les CHIFFRES bruts et fiables
(cours actuel, clôture veille, variation %). L'explication ("pourquoi le marché a bougé")
est déléguée au LLM en génération, à partir des articles économiques collectés par
rss_sources.py — jamais inventée ici.
"""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger("morning_briefing.collecte.markets")

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# Un User-Agent de navigateur est nécessaire : Yahoo bloque/soupçonne les requêtes sans
# UA d'être des scripts (indépendamment de tout abus réel), cf. doc README §7.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def fetch_quote(name: str, symbol: str, timeout: int = 10) -> dict | None:
    """Récupère la dernière cotation (cours actuel + clôture précédente) pour un symbole
    Yahoo Finance (ex: ^FCHI, ^GSPC, BZ=F...).

    Retourne None en cas d'échec (ne jamais inventer une valeur, cf. cahier §21).
    """
    try:
        resp = requests.get(
            YAHOO_CHART_URL.format(symbol=symbol),
            params={"range": "5d", "interval": "1d"},
            headers=_HEADERS,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        result = (data.get("chart") or {}).get("result") or []
        if not result:
            erreur = (data.get("chart") or {}).get("error")
            logger.warning("Réponse Yahoo Finance sans résultat pour %s (%s): %s", name, symbol, erreur)
            return None

        meta = result[0].get("meta") or {}
        cours = meta.get("regularMarketPrice")
        cloture_veille = meta.get("previousClose") or meta.get("chartPreviousClose")

        if cours is None or cloture_veille in (None, 0):
            logger.warning("Données Yahoo Finance incomplètes pour %s (%s): %s", name, symbol, meta)
            return None

        cours_f = float(cours)
        cloture_veille_f = float(cloture_veille)
        variation_pct = ((cours_f - cloture_veille_f) / cloture_veille_f) * 100 if cloture_veille_f else None

        return {
            "name": name,
            "symbol": symbol,
            "cours": cours_f,
            "cloture_veille": cloture_veille_f,
            "variation_pct": round(variation_pct, 2) if variation_pct is not None else None,
            "devise": meta.get("currency"),
        }
    except (ValueError, KeyError, TypeError) as exc:
        # Inclut json.JSONDecodeError (sous-classe de ValueError) : cas où Yahoo renvoie
        # une page HTML de consentement/erreur au lieu du JSON attendu.
        logger.warning("Réponse Yahoo Finance illisible pour %s (%s): %s", name, symbol, exc)
        return None
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
