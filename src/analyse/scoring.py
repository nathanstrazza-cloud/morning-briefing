"""Score d'importance 0-10 par événement (cf. cahier §13).

Heuristique volontairement simple en V1 : mots-clés + nombre de sources indépendantes qui
en parlent. Ne prétend pas à une précision parfaite — sert de PREMIER filtre avant que le
LLM ne rédige (le LLM peut encore choisir de ne pas retenir un item mal classé). L'important
est de ne jamais laisser passer un score artificiellement gonflé pour "remplir" une section
(cf. cahier §4 règle: ne pas chercher à remplir artificiellement une section).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("morning_briefing.analyse.scoring")

MOTS_MAJEURS = [
    "guerre", "attentat", "séisme", "tremblement de terre", "catastrophe", "mort", "morts",
    "tués", "explosion", "coup d'état", "démission", "élection présidentielle", "nucléaire",
    "pandémie", "crise majeure", "invasion", "cessez-le-feu", "accord historique",
]

MOTS_IMPORTANTS = [
    "gouvernement", "président", "ministre", "parlement", "loi", "grève", "manifestation",
    "sommet", "otan", "onu", "union européenne", "banque centrale", "inflation", "taux directeur",
    "record", "champion", "finale", "blessure grave", "transfert",
]

MOTS_INTERESSANTS = [
    "étude", "rapport", "annonce", "partenariat", "victoire", "défaite", "classement",
]


def _count_matches(text: str, mots: list[str]) -> int:
    text_low = text.lower()
    return sum(1 for m in mots if m in text_low)


def score_event(event: dict) -> int:
    """Retourne un score entier 0-10 (cf. barème cahier §13)."""
    text = f"{event.get('titre', '')} {event.get('resume', '')}"

    base = 4  # score plancher neutre
    if _count_matches(text, MOTS_MAJEURS) > 0:
        base = 9
    elif _count_matches(text, MOTS_IMPORTANTS) > 0:
        base = 7
    elif _count_matches(text, MOTS_INTERESSANTS) > 0:
        base = 5

    # Bonus convergence de sources : plusieurs médias indépendants qui traitent le même
    # événement est un signal de son importance réelle (et de sa fiabilité, cf. §11).
    nb_sources = event.get("nb_sources", 1)
    if nb_sources >= 4:
        base = min(10, base + 2)
    elif nb_sources >= 2:
        base = min(10, base + 1)

    return max(0, min(10, base))


def score_events(events: list[dict]) -> list[dict]:
    for event in events:
        event["score"] = score_event(event)
    events.sort(key=lambda e: e["score"], reverse=True)
    logger.info("Scoring terminé pour %d événements", len(events))
    return events


def filter_by_threshold(events: list[dict], seuil: int) -> list[dict]:
    return [e for e in events if e["score"] >= seuil]
