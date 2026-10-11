"""Articles de SPORT arrivés par les flux d'actualité (11/10/2026, ANALYSE_RUN_2026-10-11.md §2.2).

Constat : « Lens renoue avec la victoire contre Lyon pour le retour de la Ligue 1 », « Paul Seixas remporte le Tour de
Lombardie » ou les Mondiaux de judo arrivaient par Le Monde/France Info/Libération (flux actualité) : la section Sport ne
les voyait pas, et l'actualité les traitait comme des nouvelles générales. On les déplace vers le pool sport.
Règle STRICTE (pas de faux positifs « combat contre le cancer ») : un mot-clé d'événement sportif doit figurer dans le TITRE.
Fonctions pures, sans réseau.
"""
from __future__ import annotations

import re

from .sport_scoring import detecter_sport

MOTS_TITRE = [
    "ligue 1", "ligue 2", "ligue des champions", "ligue europa", "europa league", "premier league", "liga", "serie a",
    "bundesliga", "coupe de france de football", "tour de lombardie", "tour de france", "tour d'espagne", "giro",
    "vuelta", "paris-roubaix", "roland-garros", "wimbledon", "us open", "masters 1000", "atp", "wta", "nba", "wnba",
    "top 14", "xv de france", "six nations", "formule 1", "grand prix", "motogp", "mondiaux de", "championnats du monde de",
    "championnat du monde de", "championnats d'europe de", "ballon d'or", "psg", "euroligue", "coupe du monde de rugby",
    "coupe du monde de football", "jeux paralympiques", "para taekwondo", "judo", "natation", "marathon de",
]
_RE = re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(m) for m in sorted(MOTS_TITRE, key=len, reverse=True)) + r")(?![\w-])", re.I)


# Directs / comptes rendus de match dont le titre ne cite ni compétition ni sport (« Suivez ce choc électrique avec nous »,
# vu le 11/10 sur Liverpool - Manchester City) : stades connus et vocabulaire de match, TITRE uniquement.
_RE_MATCH = re.compile(r"suivez ce (?:choc|match|derby|classico)|\b(?:mi-temps|coup d'envoi|prolongations|tirs au but)\b|"
                       r"\b(?:anfield|old trafford|camp nou|parc des princes|santiago bernab[ée]u|allianz arena|stade v[ée]lodrome)\b", re.I)


def est_sport(item: dict) -> bool:
    titre = str(item.get("titre", ""))
    return bool(_RE.search(titre) or _RE_MATCH.search(titre))


def separer_sport(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """(items d'actualité restants, items sport au format du pool sport : champs `sport` et `categorie='sport'`)."""
    reste, sport = [], []
    for it in items:
        if est_sport(it):
            sport.append(dict(it, categorie="sport", sport=detecter_sport(it.get("titre", ""), it.get("resume", ""))))
        else:
            reste.append(it)
    return reste, sport
