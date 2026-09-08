"""Collecte des articles via flux RSS (gratuit, sans clé API).

Chaque item retourné est un dict brut, non dédupliqué, non scoré :
{
    "titre": str,
    "resume": str,        # résumé/summary fourni par le flux RSS (peut être vide)
    "url": str,
    "source": str,        # nom lisible de la source (ex: "Le Monde")
    "categorie": str,      # "france" | "monde" | "economie" | "sciences" | "sport_xxx"
    "date_publication": datetime | None,
}
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser

logger = logging.getLogger("morning_briefing.collecte.rss")


def _parse_date(entry) -> datetime | None:
    for field in ("published_parsed", "updated_parsed"):
        value = getattr(entry, field, None)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def fetch_feed(url: str, source_name: str, categorie: str, timeout: int = 15) -> list[dict]:
    """Récupère et parse un flux RSS unique. Ne lève jamais d'exception :
    en cas d'échec, retourne une liste vide et logue un warning (cf. cahier §21)."""
    try:
        parsed = feedparser.parse(url)
        if parsed.bozo and not parsed.entries:
            logger.warning("Flux RSS illisible ou vide: %s (%s)", source_name, url)
            return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Échec de récupération du flux %s (%s): %s", source_name, url, exc)
        return []

    items = []
    for entry in parsed.entries:
        titre = getattr(entry, "title", "").strip()
        if not titre:
            continue
        items.append(
            {
                "titre": titre,
                "resume": getattr(entry, "summary", "").strip(),
                "url": getattr(entry, "link", ""),
                "source": source_name,
                "categorie": categorie,
                "date_publication": _parse_date(entry),
            }
        )
    logger.info("Flux %s (%s): %d articles récupérés", source_name, categorie, len(items))
    return items


def fetch_category(rss_config: dict, categorie: str) -> list[dict]:
    """Récupère tous les flux configurés pour une catégorie donnée (ex: 'france')."""
    sources = rss_config.get(categorie, [])
    items: list[dict] = []
    for src in sources:
        items.extend(fetch_feed(src["url"], src["name"], categorie))
    return items


def fetch_all_news(config: dict, depuis: datetime | None = None) -> dict[str, list[dict]]:
    """Récupère l'actualité France/Monde/Économie/Sciences.

    Filtre optionnellement par date de publication si `depuis` est fourni
    (certains flux ne donnent pas de date -> gardés par prudence plutôt que rejetés,
    cf. cahier §21 : ne pas perdre d'info fiable par excès de filtrage).
    """
    rss_config = config.get("rss", {})
    resultat: dict[str, list[dict]] = {}
    for categorie in ("france", "monde", "economie", "sciences"):
        items = fetch_category(rss_config, categorie)
        if depuis is not None:
            items = [
                it
                for it in items
                if it["date_publication"] is None or it["date_publication"].replace(tzinfo=None) >= depuis.replace(tzinfo=None)
            ]
        resultat[categorie] = items
    return resultat
