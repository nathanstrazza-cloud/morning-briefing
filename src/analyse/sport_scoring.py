"""Scoring et sélection SPORT généralistes (refonte du 05/10/2026).

Principe : la section sport ne dépend PLUS de l'utilisateur. Aucune équipe prioritaire (Spurs...),
aucun filtre « équipe de France », aucune liste fixe de sports : on collecte des flux multi-sports,
on détecte le sport de chaque article (`detecter_sport`) et on retient ce qui est objectivement le
plus important (grandes compétitions, résultats, finales, records, blessures/transferts majeurs),
avec une diversité entre sports (`max_par_sport`). Fonctions pures : voir tests/test_sport_scoring.py.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("morning_briefing.analyse.sport_scoring")

SCORE_MIN = 5
MAX_PAR_SPORT = 2

# sport -> mots-clés (minuscules). Premier sport dont un mot apparaît dans le TITRE, sinon dans le texte.
SPORTS = {
    "football": ["football", "ligue 1", "ligue des champions", "champions league", "europa league", "premier league",
                 "liga", "serie a", "bundesliga", "mondial 20", "coupe du monde de football", "psg", "uefa", "fifa",
                 "ballon d'or", "soccer"],
    "basketball": ["basket", "nba", "euroligue", "euroleague", "wnba", "playoffs nba"],
    "tennis": ["tennis", "atp", "wta", "roland-garros", "wimbledon", "us open", "open d'australie", "grand chelem",
               "coupe davis", "masters 1000"],
    "rugby": ["rugby", "top 14", "six nations", "xv de france", "pro d2", "coupe du monde de rugby"],
    "cyclisme": ["cyclisme", "tour de france", "giro", "vuelta", "paris-roubaix", "cycliste", "peloton"],
    "natation": ["natation", "nageur", "nageuse", "bassin", "mondiaux de natation"],
    "athlétisme": ["athlétisme", "athletics", "marathon", "100 m", "diamond league", "perche", "saut en"],
    "handball": ["handball", "hand ", "lidl starligue"],
    "volley-ball": ["volley"],
    "formule 1": ["formule 1", "f1 ", "grand prix", "verstappen", "ferrari", "mclaren"],
    "sports mécaniques": ["motogp", "rallye", "wrc", "24 heures du mans", "moto gp"],
    "golf": ["golf", "ryder cup", "pga", "masters d'augusta"],
    "football américain": ["nfl", "super bowl", "football américain"],
    "baseball": ["mlb", "baseball", "world series"],
    "hockey sur glace": ["nhl", "hockey"],
    "boxe et combat": ["boxe", "ufc", "mma", "judo", "combat"],
    "sports d'hiver": ["ski", "biathlon", "snowboard", "patinage"],
    "jeux olympiques": ["jeux olympiques", "jo de", "olympique", "paralympique", "cio "],
}

_COMPETITION_MAJEURE = [
    "ligue des champions", "champions league", "europa league", "coupe du monde", "world cup", "jeux olympiques",
    "mondiaux", "championnat du monde", "championnats du monde", "championnat d'europe", "euro 20", "grand chelem",
    "roland-garros", "wimbledon", "us open", "open d'australie", "tour de france", "grand prix", "super bowl",
    "finales nba", "nba finals", "playoffs", "play-offs", "ryder cup", "six nations", "premier league", "ligue 1",
    "liga", "serie a", "bundesliga", "top 14", "euroligue", "nba", "masters", "ballon d'or", "finale",
]
_RESULTAT = ["bat ", "battu", "victoire", "s'impose", "s’impose", "défaite", "nul", "score", "doublé", "triplé",
             "qualif", "éliminé", "classement", "leader", "buts", "revient", "l'emporte", "sacré", "titre",
             "remporte", "beat", "wins", "win ", "defeat", "lose", "loses", "advance", "champion"]
_EVENEMENT = ["blessure", "blessé", "forfait", "suspendu", "transfert", "recrut", "prolong", "licenci", "limogé",
              "record", "exploit", "retraite", "injury", "injured", "ruled out", "signs", "sacked"]
_ANECDOTE = ["chanson", "youtube", "clip", "guéguerre", "rivalité", "tiktok", "instagram", "polémique", "buzz",
             "gala", "people", "mariage", "livre", "interview", "portrait", "podcast", "documentaire", "séries",
             "mercato", "rumeur", "rumour", "gossip"]


def _has(text: str, mots: list[str]) -> bool:
    return any(m in text for m in mots)


def detecter_sport(titre: str, resume: str = "", indice: str | None = None) -> str:
    """Sport d'un article : indice de la source si fourni, sinon mots-clés (titre d'abord), sinon « autres »."""
    if indice:
        return indice.strip().lower()
    t, r = f"{titre} ".lower(), f"{resume} ".lower()
    for zone in (t, t + r):
        for sport, mots in SPORTS.items():
            if _has(zone, mots):
                return sport
    return "autres"


def score_sport_event(event: dict, categorie: str | None = None, config: dict | None = None) -> int:
    """Importance 0-10 d'un événement sportif, sans aucune préférence personnelle.
    `categorie` est conservé pour compatibilité d'appel, le score ne dépend pas du sport."""
    titre = f"{event.get('titre', '')} ".lower()
    texte = f"{event.get('titre', '')} {event.get('resume', '')} ".lower()
    score = 3
    if _has(texte, _COMPETITION_MAJEURE):
        score += 2
    if _has(titre, _RESULTAT):
        score += 2
    if _has(texte, _EVENEMENT):
        score += 1
    if _has(texte, ["record", "historique", "inédit", "first time", "history"]):
        score += 1
    if _has(texte, ["finale", "final ", "titre", "médaille", "champion", "trophée"]):
        score += 1
    if not _has(texte, _COMPETITION_MAJEURE + _RESULTAT + _EVENEMENT):
        score -= 1
    if _has(texte, _ANECDOTE):
        score -= 3
    score += min(2, max(0, event.get("nb_sources", 1) - 1))
    return max(0, min(10, score))


def select_sport(raw_events, max_total: int, config: dict | None = None, score_min: int = SCORE_MIN,
                 max_par_sport: int | None = None) -> dict[str, list[dict]]:
    """Sélection généraliste. `raw_events` : liste d'événements dédupliqués (chacun avec `sport`),
    OU dict {sport: [événements]} (ancien format, aplati). Retourne {sport: [événements retenus]},
    triés par importance, max `max_par_sport` par sport (diversité) et `max_total` au total."""
    cfg = (config or {}).get("sport") or {}
    plafond = max_par_sport or int(cfg.get("max_par_sport", MAX_PAR_SPORT))
    if isinstance(raw_events, dict):
        flat = [dict(e, sport=e.get("sport") or s) for s, evs in raw_events.items() for e in evs]
    else:
        flat = [dict(e) for e in raw_events]
    for e in flat:
        e["sport"] = e.get("sport") or detecter_sport(e.get("titre", ""), e.get("resume", ""))
        e["score"] = score_sport_event(e, e["sport"], config)
    flat = [e for e in flat if e["score"] >= score_min]
    flat.sort(key=lambda e: (e["score"], e.get("nb_sources", 1),
                             e["date_publication"].timestamp() if e.get("date_publication") else 0), reverse=True)
    retenus: dict[str, list[dict]] = {}
    total = 0
    for e in flat:
        if total >= max_total:
            break
        if len(retenus.get(e["sport"], [])) >= plafond:
            continue
        retenus.setdefault(e["sport"], []).append(e)
        total += 1
    logger.info("Sport: %d retenu(s) %s (seuil=%d, max %d/sport)", total,
                {c: len(v) for c, v in retenus.items()}, score_min, plafond)
    return retenus
