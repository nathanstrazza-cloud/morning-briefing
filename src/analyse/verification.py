"""Classification du statut de vérification (cf. cahier §11) :

- "fait_confirme"     : plusieurs sources fiables concordent (>=2 sources indépendantes)
- "information_rapportee" : une seule source, à formuler avec "Selon [source], ..."
- "incertaine"        : jugée insuffisamment fiable (V1 : réservé, cf. note ci-dessous)

Note V1 : sans fact-checking sémantique par LLM, on ne peut pas distinguer de façon fiable
"incertaine"/"rumeur" du reste par du texte seul. En V1, tout événement collecté depuis une
source RSS reconnue (cf. config sources_preferees / flux configurés) est donc classé au
minimum "information_rapportee", jamais "rumeur" (cf. cahier §11: rumeur = ne pas publier
sauf nécessité exceptionnelle -> en V1 on ne publie donc aucune rumeur, par construction,
puisqu'on ne collecte que des flux de médias établis, cf. config.yaml).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("morning_briefing.analyse.verification")

SEUIL_FAIT_CONFIRME = 2  # nombre minimum de sources indépendantes concordantes


def classify_event(event: dict) -> str:
    nb_sources = event.get("nb_sources", 1)
    if nb_sources >= SEUIL_FAIT_CONFIRME:
        return "fait_confirme"
    return "information_rapportee"


def classify_events(events: list[dict]) -> list[dict]:
    for event in events:
        event["statut_verification"] = classify_event(event)
    n_confirmes = sum(1 for e in events if e["statut_verification"] == "fait_confirme")
    logger.info(
        "Vérification: %d/%d événements classés 'fait confirmé' (>= %d sources)",
        n_confirmes, len(events), SEUIL_FAIT_CONFIRME,
    )
    return events


def format_prefix(event: dict) -> str:
    """Formulation à utiliser en rédaction (cf. cahier §11)."""
    if event["statut_verification"] == "fait_confirme":
        return ""
    source = event["sources"][0]["nom"] if event.get("sources") else "une source"
    return f"Selon {source}, "
