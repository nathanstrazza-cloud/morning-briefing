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


def compute_session_change(result: dict) -> dict | None:
    """Calcule la variation d'UNE séance à partir de la réponse Yahoo « chart ».

    Correctif du 02/10/2026 : l'ancien code utilisait `meta.previousClose or
    meta.chartPreviousClose`. Avec `range=5d`, `chartPreviousClose` est la clôture
    d'AVANT le début de la plage (~5 séances plus tôt) : la variation affichée était
    donc hebdomadaire (CAC -3,0 % au lieu d'environ -1 %), et le LLM l'expliquait
    avec l'actualité du jour. On utilise désormais le tableau des clôtures journalières.

    Règle : on compare le cours courant (`regularMarketPrice`) à la clôture de la séance
    PRÉCÉDENTE. Si la dernière barre journalière est celle de la séance du cours courant
    (cas général), la référence est l'avant-dernière clôture ; sinon (barre du jour pas
    encore créée) c'est la dernière clôture.

    Retourne None si les données sont insuffisantes (jamais de valeur inventée).
    """
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    meta = result.get("meta") or {}
    cours = meta.get("regularMarketPrice")
    timestamps = result.get("timestamp") or []
    quotes = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quotes.get("close") or []
    if cours is None or len(timestamps) != len(closes):
        return None

    try:
        tz = ZoneInfo(meta.get("exchangeTimezoneName") or "UTC")
    except Exception:  # noqa: BLE001
        tz = timezone.utc
    barres = [
        (datetime.fromtimestamp(t, tz).date(), float(c))
        for t, c in zip(timestamps, closes)
        if c is not None
    ]
    if not barres:
        return None

    rmt = meta.get("regularMarketTime")
    date_cours = datetime.fromtimestamp(rmt, tz).date() if rmt else barres[-1][0]
    if barres[-1][0] == date_cours:
        if len(barres) < 2:
            return None
        ref_date, reference = barres[-2]
    else:
        ref_date, reference = barres[-1]
    if not reference:
        return None
    cours_f = float(cours)
    return {
        "cours": cours_f,
        "cloture_veille": reference,
        "date_reference": ref_date.isoformat(),
        "date_cours": date_cours.isoformat(),
        "variation_pct": round((cours_f - reference) / reference * 100, 2),
    }


def fetch_quote(
    name: str, symbol: str, timeout: int = 10, diagnostics: list[dict] | None = None
) -> dict | None:
    """Récupère la dernière cotation (cours actuel + clôture précédente) pour un symbole
    Yahoo Finance (ex: ^FCHI, ^GSPC, BZ=F...).

    Retourne None en cas d'échec (ne jamais inventer une valeur, cf. cahier §21).
    `diagnostics`, si fourni, reçoit une entrée par symbole (cf. rss_sources.fetch_feed,
    même logique -- cf. cahier §22 journalisation)."""
    def _record(statut: str, detail: str | None, http_status: int | None = None) -> None:
        if diagnostics is not None:
            diagnostics.append({
                "source": name, "symbol": symbol, "statut": statut,
                "http_status": http_status, "detail": detail,
            })

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
            _record("erreur", f"pas de résultat: {erreur}", resp.status_code)
            return None

        meta = result[0].get("meta") or {}
        change = compute_session_change(result[0])

        if change is None:
            logger.warning("Données Yahoo Finance incomplètes pour %s (%s): %s", name, symbol, meta)
            _record(
                "erreur",
                f"champs manquants/insuffisants (cours={meta.get('regularMarketPrice')!r}, "
                f"marketState={meta.get('marketState')!r})",
                resp.status_code,
            )
            return None

        # Journalisation de contrôle (cahier §22) : permet de vérifier a posteriori la base
        # de calcul (hypothèse du 01/10 : ancienne base = 5 séances).
        logger.info(
            "Marché %s: cours=%s ref=%s (%s) var=%s%% | meta.chartPreviousClose=%s previousClose=%s",
            name, change["cours"], change["cloture_veille"], change["date_reference"],
            change["variation_pct"], meta.get("chartPreviousClose"), meta.get("previousClose"),
        )
        _record("ok", None, resp.status_code)
        return {
            "name": name,
            "symbol": symbol,
            "cours": change["cours"],
            "cloture_veille": change["cloture_veille"],
            "date_reference": change["date_reference"],
            "variation_pct": change["variation_pct"],
            "devise": meta.get("currency"),
        }
    except (ValueError, KeyError, TypeError) as exc:
        # Inclut json.JSONDecodeError (sous-classe de ValueError) : cas où Yahoo renvoie
        # une page HTML de consentement/erreur au lieu du JSON attendu.
        logger.warning("Réponse Yahoo Finance illisible pour %s (%s): %s", name, symbol, exc)
        _record("erreur", f"réponse illisible: {exc}")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Échec récupération cotation %s (%s): %s", name, symbol, exc)
        _record("erreur", str(exc))
        return None


def fetch_all_markets(config: dict, diagnostics: list[dict] | None = None) -> dict[str, list[dict]]:
    marches_config = config.get("marches", {})
    resultat: dict[str, list[dict]] = {"indices": [], "matieres_premieres": []}

    for entry in marches_config.get("indices", []):
        quote = fetch_quote(entry["name"], entry["symbol"], diagnostics=diagnostics)
        if quote:
            resultat["indices"].append(quote)

    for entry in marches_config.get("matieres_premieres", []):
        quote = fetch_quote(entry["name"], entry["symbol"], diagnostics=diagnostics)
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
