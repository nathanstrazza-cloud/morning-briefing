"""Scoring et sélection SPORT dédiés (point 5 de l'analyse du 01/10, confirmé le 02/10).

Avant : le scoring d'actualité générique (« démission » = 9) était appliqué au sport, puis
`max_sport_total` coupait globalement : le 02/10 le briefing contenait du foot féminin, une chanson
sur Zidane et une démission olympique, aucun match masculin Ligue 1/C1/Europa, aucun Spurs.
Autre bug : `dedup.deduplicate` ne recopie pas `equipe_prioritaire`, donc le bonus Spurs ne
s'appliquait jamais. Ici le périmètre du cahier §6 est explicite et le bonus Spurs est calculé
sur le texte.

Principe : un item hors périmètre ou « people/anecdote » ne passe pas ; on garantit au moins un
item par catégorie quand un item pertinent existe (foot, basket, natation, autres), puis on
complète par score jusqu'à `max_sport_total`. Fonctions pures : voir tests/test_sport_scoring.py.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("morning_briefing.analyse.sport_scoring")

SCORE_MIN = 5
ORDRE_CATEGORIES = ("football", "basketball", "natation", "autres")

_FOOT_PERIMETRE = ["ligue 1", "ligue des champions", "champions league", "europa league", "ligue europa", "psg",
                   "paris sg", "paris saint-germain", "marseille", "olympique de marseille", "om ", "lyon", "monaco",
                   "lille", "losc", "nice", "lens", "rennes", "bleus", "équipe de france", "mbappé", "dembélé"]
_RESULTAT = ["bat ", "battu", "victoire", "s'impose", "s’impose", "défaite", "nul", "match nul", "score", "doublé",
             "triplé", "qualif", "éliminé", "classement", "leader", "but ", "buts", "finale", "revient", "l'emporte"]
_EVENEMENT = ["blessure", "blessé", "forfait", "suspendu", "transfert", "recrut", "prolong", "licenci", "limogé",
              "record", "exploit", "remplaçant", "sélection", "convoqué"]
_FEMININ = ["féminin", "féminine", "lyonnes", "bleues", "paris fc", "wsl", "ligue des champions féminine", "arkema",
            "première ligue"]
_ANECDOTE = ["chanson", "youtube", "clip", "guéguerre", "rivalité", "tiktok", "instagram", "polémique", "buzz",
             "démission", "cheffe de délégation", "olympisme", "cio ", "gala", "people", "mariage", "livre"]
_BASKET_PRIO = ["spurs", "wembanyama", "wemby", "san antonio"]
_BASKET_PERIMETRE = ["nba", "euroligue", "euroleague", "basket", "playoffs", "play-offs", "pré-saison", "preseason",
                     "training camp"]
_NATATION_MAJEUR = ["championnat", "mondiaux", "euro ", "européens", "jeux olympiques", "coupe du monde", "record",
                    "marchand", "manaudou", "médaille", "finale"]
_FR = ["france", "français", "française", "bleus", "bleues", "tricolore"]


def _has(text: str, mots: list[str]) -> bool:
    return any(m in text for m in mots)


def _n(text: str, mots: list[str]) -> int:
    return sum(1 for m in mots if m in text)


def score_sport_event(event: dict, categorie: str, config: dict | None = None) -> int:
    texte = f"{event.get('titre', '')} {event.get('resume', '')}".lower() + " "
    titre = f"{event.get('titre', '')} ".lower()
    inclure_feminin = bool(((config or {}).get("sport") or {}).get("inclure_feminin", False))
    prio = [p.lower() for p in (((config or {}).get("sport") or {}).get("equipes_prioritaires") or {}).get("basketball", [])]

    score = 3
    if categorie == "football":
        if _has(texte, _FOOT_PERIMETRE):
            score += 2
        if _has(texte, ["ligue 1", "ligue des champions", "champions league", "europa league", "ligue europa"]):
            score += 1
        if _has(titre, _RESULTAT):
            score += 2
        if _has(texte, _EVENEMENT):
            score += 1
        if not inclure_feminin and _has(texte, _FEMININ):
            score -= 4
        if not _has(texte, _FOOT_PERIMETRE + _RESULTAT + _EVENEMENT):
            score -= 1
    elif categorie == "basketball":
        if _has(texte, _BASKET_PRIO + prio):
            score += 4
        if _has(texte, _BASKET_PERIMETRE):
            score += 2
        if _has(titre, _RESULTAT) or _has(texte, _EVENEMENT):
            score += 1
    elif categorie == "natation":
        score += 4 if _has(texte, _NATATION_MAJEUR) else -2
    else:  # autres sports : déjà filtrés « France » à la collecte
        if _has(texte, _FR):
            score += 2
        if _has(titre, _RESULTAT) or _has(texte, _EVENEMENT):
            score += 2
        if _has(texte, ["finale", "titre", "champion", "médaille", "qualifi"]):
            score += 1
    if _has(texte, _ANECDOTE):
        score -= 3
    score += min(2, max(0, event.get("nb_sources", 1) - 1))
    return max(0, min(10, score))


def select_sport(raw_events: dict[str, list[dict]], max_total: int, config: dict | None = None,
                 score_min: int = SCORE_MIN) -> dict[str, list[dict]]:
    """`raw_events` : {catégorie: [événements dédupliqués]}. Retourne {catégorie: [événements retenus]}."""
    scored: dict[str, list[dict]] = {}
    for cat, evs in raw_events.items():
        lst = [dict(e, score=score_sport_event(e, cat, config)) for e in evs]
        lst.sort(key=lambda e: e["score"], reverse=True)
        scored[cat] = [e for e in lst if e["score"] >= score_min]

    retenus: dict[str, list[dict]] = {cat: [] for cat in raw_events}
    total = 0
    for cat in ORDRE_CATEGORIES:                      # 1) au moins un item par catégorie pertinente
        if total < max_total and scored.get(cat):
            retenus[cat].append(scored[cat][0])
            total += 1
    reste = sorted((e | {"_cat": c} for c, l in scored.items() for e in l[1:] if c in retenus),
                   key=lambda e: e["score"], reverse=True)
    for e in reste:                                   # 2) complément par score
        if total >= max_total:
            break
        retenus[e.pop("_cat")].append(e)
        total += 1
    logger.info("Sport: %d retenu(s) %s (seuil=%d)", total, {c: len(v) for c, v in retenus.items()}, score_min)
    return retenus
