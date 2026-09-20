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

import html
import logging
import re
from datetime import datetime, timezone

import feedparser

logger = logging.getLogger("morning_briefing.collecte.rss")

# NB (corrigé le 2026-09-13) : certains flux (Nature News, NYT, CNRS...) renvoient un
# `summary` qui contient du HTML brut (balises, entités, parfois très long). Envoyé tel
# quel au LLM (cf. generation/briefing_generator.py), cela gonflait le payload JSON de la
# requête Groq jusqu'à déclencher une erreur "413 Payload Too Large" (constaté les 2026-09-10
# et 2026-09-11 : la synthèse LLM échouait systématiquement et le pipeline retombait en
# mode fallback sans texte rédigé). On nettoie donc le résumé dès la collecte : suppression
# des balises HTML, des entités, et troncature à une longueur raisonnable (un résumé RSS
# n'a de toute façon pas besoin d'être plus long pour que le LLM comprenne le sujet).
_TAG_RE = re.compile(r"<[^>]+>")
MAX_RESUME_CHARS = 500

# NB (corrigé le 2026-09-20) : plusieurs flux (Le Point, Les Echos...) renvoyaient un
# HTTP 403 systématique. Cause identifiée : ces sites bloquent les requêtes dont le
# User-Agent est celui, par défaut, de la librairie feedparser/urllib (facilement
# reconnaissable comme trafic de robot). Un User-Agent de navigateur standard suffit à
# débloquer la plupart de ces flux sans aucune clé ni compte (cf. cahier §21 : privilégier
# les sources gratuites, ne pas inventer de contournement fragile). On garde quand même le
# diagnostic HTTP (cf. fetch_feed) pour les flux qui resteraient bloqués malgré ce correctif
# (ex: protection anti-bot plus poussée type Cloudflare "managed challenge", qui ne peut pas
# être contournée par un simple en-tête et nécessiterait un vrai navigateur -- hors scope V1
# cf. cahier §19 coût 0€).
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_REQUEST_HEADERS = {
    "Accept": "application/rss+xml, application/xml, text/xml, */*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
}


def _clean_summary(raw: str) -> str:
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_RESUME_CHARS:
        text = text[:MAX_RESUME_CHARS].rsplit(" ", 1)[0] + "…"
    return text


def _parse_date(entry) -> datetime | None:
    for field in ("published_parsed", "updated_parsed"):
        value = getattr(entry, field, None)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def _record(diagnostics: list[dict] | None, **fields) -> None:
    """Ajoute une entrée de diagnostic si une liste a été fournie par l'appelant.
    cf. cahier §22 journalisation : on veut pouvoir dire, pour CHAQUE flux configuré, s'il a
    fonctionné, combien d'articles il a rendus, et pourquoi il a échoué le cas échéant --
    sans avoir à rouvrir les logs bruts de GitHub Actions à chaque fois."""
    if diagnostics is not None:
        diagnostics.append(fields)


def fetch_feed(
    url: str,
    source_name: str,
    categorie: str,
    timeout: int = 15,
    diagnostics: list[dict] | None = None,
) -> list[dict]:
    """Récupère et parse un flux RSS unique. Ne lève jamais d'exception :
    en cas d'échec, retourne une liste vide et logue un warning (cf. cahier §21).

    `diagnostics`, si fourni, reçoit une entrée par flux (source, catégorie, statut HTTP,
    nombre d'articles, détail de l'erreur éventuelle) -- utilisé par collector.py pour
    exposer l'état de chaque source dans status.json (cf. cahier §22)."""
    try:
        # agent= : envoie un User-Agent de navigateur standard (cf. USER_AGENT ci-dessus) --
        # plusieurs sites (Le Point, Les Echos...) bloquaient sinon la requête avec un 403,
        # feedparser utilisant par défaut un User-Agent facilement identifiable comme robot.
        parsed = feedparser.parse(url, agent=USER_AGENT, request_headers=_REQUEST_HEADERS)
        http_status = parsed.get("status")
        if http_status and http_status >= 400:
            logger.warning(
                "Flux RSS %s (%s) a répondu HTTP %s: %s", source_name, categorie, http_status, url
            )
            _record(
                diagnostics, source=source_name, categorie=categorie, url=url,
                articles=0, statut="erreur", http_status=http_status,
                detail=f"HTTP {http_status}",
            )
            return []
        if parsed.bozo and not parsed.entries:
            detail = str(getattr(parsed, "bozo_exception", "flux illisible ou vide"))
            logger.warning("Flux RSS illisible ou vide: %s (%s) -- %s", source_name, url, detail)
            _record(
                diagnostics, source=source_name, categorie=categorie, url=url,
                articles=0, statut="erreur", http_status=http_status, detail=detail,
            )
            return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("Échec de récupération du flux %s (%s): %s", source_name, url, exc)
        _record(
            diagnostics, source=source_name, categorie=categorie, url=url,
            articles=0, statut="erreur", http_status=None, detail=str(exc),
        )
        return []

    items = []
    for entry in parsed.entries:
        titre = getattr(entry, "title", "").strip()
        if not titre:
            continue
        items.append(
            {
                "titre": titre,
                "resume": _clean_summary(getattr(entry, "summary", "")),
                "url": getattr(entry, "link", ""),
                "source": source_name,
                "categorie": categorie,
                "date_publication": _parse_date(entry),
            }
        )
    logger.info("Flux %s (%s): %d articles récupérés", source_name, categorie, len(items))
    _record(
        diagnostics, source=source_name, categorie=categorie, url=url,
        articles=len(items), statut="ok" if items else "vide",
        http_status=parsed.get("status"), detail=None,
    )
    return items


def fetch_category(rss_config: dict, categorie: str, diagnostics: list[dict] | None = None) -> list[dict]:
    """Récupère tous les flux configurés pour une catégorie donnée (ex: 'france')."""
    sources = rss_config.get(categorie, [])
    items: list[dict] = []
    for src in sources:
        items.extend(fetch_feed(src["url"], src["name"], categorie, diagnostics=diagnostics))
    return items


def fetch_all_news(
    config: dict, depuis: datetime | None = None, diagnostics: list[dict] | None = None
) -> dict[str, list[dict]]:
    """Récupère l'actualité France/Monde/Économie/Sciences.

    Filtre optionnellement par date de publication si `depuis` est fourni
    (certains flux ne donnent pas de date -> gardés par prudence plutôt que rejetés,
    cf. cahier §21 : ne pas perdre d'info fiable par excès de filtrage).

    `diagnostics`, si fourni, reçoit l'état de chaque flux RSS interrogé (cf. fetch_feed).
    """
    rss_config = config.get("rss", {})
    resultat: dict[str, list[dict]] = {}
    for categorie in ("france", "monde", "economie", "sciences"):
        items = fetch_category(rss_config, categorie, diagnostics=diagnostics)
        if depuis is not None:
            items = [
                it
                for it in items
                if it["date_publication"] is None or it["date_publication"].replace(tzinfo=None) >= depuis.replace(tzinfo=None)
            ]
        resultat[categorie] = items
    return resultat
