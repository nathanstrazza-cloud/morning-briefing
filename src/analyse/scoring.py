"""Score d'importance 0-10 par événement (cf. cahier §13).

Heuristique déterministe, sans LLM ni réseau. Sert de PREMIER filtre avant la rédaction.

Révision du 05/10/2026 (point 5 de ANALYSE_RUN_2026-10-05.md) : l'ancienne version cherchait des
SOUS-CHAÎNES (« mort » dans « Mortier », « loi » dans « emploi ») et donnait 9 au décès d'un écrivain
(« est mort à 98 ans ») devant une présidentielle ou une alerte sanitaire. Maintenant :
- les mots-clés sont des MOTS ENTIERS (regex), plus de faux positifs par sous-chaîne ;
- les termes ambigus (« mort », « tués », « record »…) ne comptent plus seuls comme « majeurs » ;
  un événement est majeur s'il relève d'un THÈME d'importance (guerre, élection nationale, catastrophe,
  santé publique, crise économique…) ;
- des MALUS pour les formats de faible valeur d'information (tribune, interview, portrait, fait divers,
  culture/people, nécrologie) ;
- à score égal, départage stable par nombre de sources puis fraîcheur (le tri n'est plus l'ordre du flux).
Fonctions pures : voir tests/test_scoring.py.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

logger = logging.getLogger("morning_briefing.analyse.scoring")


def _re(mots: list[str]) -> re.Pattern:
    """Mots ENTIERS (frontières tolérant accents/apostrophes/traits d'union), insensible à la casse."""
    return re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(m) for m in sorted(mots, key=len, reverse=True)) + r")(?![\w-])",
                      re.IGNORECASE | re.UNICODE)


# --- Thèmes MAJEURS (9) : un seul suffit ---------------------------------------------------------------
MOTS_MAJEURS = [
    "guerre", "attentat", "attentats", "séisme", "tremblement de terre", "tsunami", "ouragan", "cyclone",
    "inondations", "catastrophe", "coup d'état", "invasion", "frappes", "bombardements", "bombardé",
    "offensive", "cessez-le-feu", "accord historique", "pandémie", "épidémie", "ebola", "crise majeure",
    "prise d'otages", "otages", "explosion", "démission du gouvernement", "motion de censure",
    "dissolution", "état d'urgence", "krach", "récession", "défaut de paiement", "sanctions",
    "élection présidentielle", "présidentielle", "législatives", "premier tour", "second tour", "référendum",
    "résultats", "scrutin", "midterms", "mid-terms",
]

# --- Thèmes IMPORTANTS (7) -----------------------------------------------------------------------------
MOTS_IMPORTANTS = [
    "gouvernement", "premier ministre", "ministre", "parlement", "assemblée nationale", "sénat", "budget",
    "loi", "grève", "manifestation", "manifestations", "sommet", "otan", "onu", "union européenne", "banque centrale",
    "fed", "bce", "inflation", "taux directeur", "chômage", "croissance", "nucléaire", "diplomatie",
    "visite", "négociations", "accord", "traité", "tarifs douaniers", "droits de douane", "intelligence artificielle",
    "vaccin", "vaccination", "cancer", "climat", "canicule", "incendie", "incendies",
]

MOTS_INTERESSANTS = [
    "étude", "rapport", "annonce", "partenariat", "victoire", "défaite", "classement", "enquête", "procès",
]

# --- MALUS : formats / sujets à faible valeur d'information pour un briefing d'actualité --------------
# (pas d'exclusion : un événement majeur (guerre, élection…) garde son score malgré ces mots)
MALUS_FORMAT = [
    "tribune", "éditorial", "chronique", "billet", "opinion", "point de vue", "carnet", "portrait",
    "entretien", "interview", "témoignage", "reportage", "analyse", "décryptage", "podcast", "newsletter",
    "quiz", "en images", "diaporama", "revue de presse",
]
# Un titre qui se termine par « : » + citation, ou qui contient un guillemet d'interview, est un signal faible.
MALUS_FAIT_DIVERS = [
    "fait divers", "conflit de voisinage", "voisin", "voisins", "cambriolage", "agression", "rixe", "noyade",
    "accident de la route", "chien", "chat", "animal", "météo", "horoscope", "recette",
]
MALUS_CULTURE = [
    "écrivain", "romancier", "chanteur", "chanteuse", "acteur", "actrice", "cinéma", "film", "série", "album",
    "concert", "festival", "exposition", "livre", "littérature", "roman", "hommage", "nécrologie", "raï",
    "people", "mode", "gastronomie",
]
# Expressions FIGURÉES contenant un mot « majeur » (retirées avant le comptage : « guerre ouverte » entre voisins
# n'est pas une guerre).
EXPRESSIONS_FIGUREES = ["guerre ouverte", "guerre des étoiles", "guerre des prix", "guerre de tranchées", "guerre des nerfs",
                        "guerre des boutons", "guerre froide entre"]
# Un titre qui ANNONCE un résultat (plutôt qu'un avant-scrutin / une analyse) : +1 (point 6 du 05/10).
MOTS_RESULTAT = ["frôle la victoire", "remporte", "l'emporte", "est élu", "est élue", "réélu", "réélue", "largement devant",
                 "en tête", "victoire de", "résultats", "bilan"]

_RE_MAJEURS = _re(MOTS_MAJEURS)
_RE_IMPORTANTS = _re(MOTS_IMPORTANTS)
_RE_INTERESSANTS = _re(MOTS_INTERESSANTS)
_RE_MALUS_FORMAT = _re(MALUS_FORMAT)
_RE_MALUS_FAITS_DIVERS = _re(MALUS_FAIT_DIVERS)
_RE_MALUS_CULTURE = _re(MALUS_CULTURE)
_RE_FIGUREES = _re(EXPRESSIONS_FIGUREES)
_RE_RESULTAT = _re(MOTS_RESULTAT)


def _count_matches(text: str, regex: re.Pattern) -> int:
    """Nombre de mots-clés DISTINCTS trouvés (mots entiers)."""
    return len({m.lower() for m in regex.findall(text or "")})


def score_event(event: dict) -> int:
    """Retourne un score entier 0-10 (cf. barème cahier §13)."""
    titre = _RE_FIGUREES.sub(" ", str(event.get("titre", "") or ""))
    resume = _RE_FIGUREES.sub(" ", str(event.get("resume", "") or ""))
    text = f"{titre} {resume}"

    n_maj, n_imp, n_int = (_count_matches(text, r) for r in (_RE_MAJEURS, _RE_IMPORTANTS, _RE_INTERESSANTS))
    # Les mots du TITRE pèsent plus que ceux du résumé : un mot « majeur » seulement dans le résumé
    # d'un article d'une autre nature ne fait pas un événement majeur.
    n_maj_titre = _count_matches(titre, _RE_MAJEURS)

    base = 4
    if n_maj_titre >= 1 or n_maj >= 2:
        base = 9
    elif n_maj == 1:
        base = 8
    elif n_imp >= 1:
        base = 7
    elif n_int >= 1:
        base = 5

    # Malus de format / nature (cumulables, plafonnés à -5). Un thème majeur (9) reste donc au-dessus du seuil
    # (5) avec UN malus (« Guerre en Ukraine : entretien avec… » = 6) mais pas avec deux.
    malus = 0
    if _count_matches(titre, _RE_MALUS_FORMAT) or _count_matches(resume, _RE_MALUS_FORMAT) >= 2:
        malus += 3
    if _count_matches(text, _RE_MALUS_FAITS_DIVERS):
        malus += 3
    if _count_matches(text, _RE_MALUS_CULTURE):
        malus += 2
    if re.search(r"\bpar\s+\d+\s+(?:anciens|ex-)", titre, re.IGNORECASE):  # tribune collective signée
        malus += 5
    base -= min(5, malus)
    if _count_matches(titre, _RE_RESULTAT):
        base += 1

    # Convergence de sources : plusieurs médias indépendants = signal d'importance (et de fiabilité, §11).
    nb_sources = event.get("nb_sources", 1)
    if nb_sources >= 4:
        base += 2
    elif nb_sources >= 3:
        base += 1
        base += 1 if base < 9 else 0
    elif nb_sources >= 2:
        base += 1

    return max(0, min(10, base))


def _cle_tri(event: dict) -> tuple:
    """Tri décroissant : score, nombre de sources, fraîcheur (date la plus récente d'abord)."""
    d = event.get("date_publication")
    ts = d.timestamp() if isinstance(d, datetime) else 0.0
    return (event.get("score", 0), event.get("nb_sources", 1), ts)


def score_events(events: list[dict]) -> list[dict]:
    for event in events:
        event["score"] = score_event(event)
    events.sort(key=_cle_tri, reverse=True)
    logger.info("Scoring terminé pour %d événements", len(events))
    return events


def filter_by_threshold(events: list[dict], seuil: int) -> list[dict]:
    return [e for e in events if e["score"] >= seuil]
