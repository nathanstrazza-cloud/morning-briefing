"""Affectation FRANCE / MONDE par CONTENU (et non plus seulement par flux RSS).

Problème (SUIVI_CORRECTIFS.md, constats du Dev Test du 03/10/2026) : les flux « Le Monde — Une »,
Libération, France Info… sont classés `france` par flux, alors qu'ils parlent aussi de la Russie,
de la Corée du Nord, etc. À l'inverse un flux « international » peut traiter d'un sujet purement
français.

Règle (heuristique lexicale, déterministe, sans LLM ni réseau) :
- on compte les marqueurs « France » (institutions, personnalités stables, villes) et les marqueurs
  « étranger » (pays, adjectifs de nationalité, organisations internationales, dirigeants) ;
  un marqueur du TITRE compte 2, du RÉSUMÉ 1 ;
- si l'écart est d'au moins 2 points, la zone suit le contenu ; sinon on GARDE la zone du flux
  (cas mixtes : « Macron et Trump… » reste dans la zone d'origine) ;
- les items en anglais (New York Times) restent en Monde : le lexique est français.
Chaque réaffectation est loggée (titre, ancienne -> nouvelle zone).
"""
from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger("morning_briefing.analyse.zones")

ECART_MIN = 2
POIDS_TITRE = 2
POIDS_RESUME = 1

MARQUEURS_FRANCE = [
    "france", "français", "française", "françaises", "hexagone", "paris", "élysée", "matignon",
    "macron", "le pen", "bardella", "mélenchon", "assemblée nationale", "députés", "député",
    "conseil constitutionnel", "conseil d'état", "cour de cassation", "insee", "bercy", "sncf", "ratp",
    "préfet", "préfecture", "marseille", "lyon", "toulouse", "bordeaux", "lille", "nantes", "strasbourg",
    "nice", "montpellier", "rennes", "grenoble", "outre-mer", "corse", "rn", "lfi", "baccalauréat",
    "éducation nationale", "sécurité sociale", "assurance-maladie", "urssaf", "loi de finances",
    "projet de loi", "réforme des retraites", "gendarmerie", "tribunal judiciaire",
]

MARQUEURS_MONDE = [
    # pays (formes françaises) et adjectifs
    "états-unis", "américain", "américaine", "américains", "washington", "maison-blanche", "trump",
    "biden", "russie", "russe", "russes", "moscou", "poutine", "kremlin", "ukraine", "ukrainien",
    "ukrainienne", "kiev", "gaza", "israël", "israélien", "israélienne", "hamas", "hezbollah", "iran",
    "iranien", "téhéran", "chine", "chinois", "chinoise", "pékin", "xi jinping", "taïwan", "corée du nord",
    "corée du sud", "pyongyang", "séoul", "japon", "japonais", "inde", "indien", "pakistan", "afghanistan",
    "syrie", "syrien", "liban", "irak", "yémen", "arabie saoudite", "turquie", "turc", "égypte", "soudan",
    "éthiopie", "nigeria", "afrique du sud", "sahel", "mali", "niger", "burkina", "congo", "libye",
    "algérie", "algérien", "maroc", "tunisie", "royaume-uni", "britannique", "londres", "allemagne",
    "allemand", "berlin", "italie", "italien", "rome", "espagne", "espagnol", "madrid", "pologne",
    "hongrie", "orban", "bruxelles", "canada", "mexique", "brésil", "argentine", "venezuela", "cuba",
    "colombie", "australie", "indonésie", "philippines", "vietnam", "thaïlande", "birmanie",
    "onu", "otan", "oms", "fmi", "g7", "g20", "brics", "conseil de sécurité", "cpi", "zelensky",
    "netanyahou", "kim jong", "erdogan", "modi", "starmer", "merz", "meloni",
    # États américains / institutions US (05/10 : l'exécution de Christa Pike, Tennessee, restait classée France)
    "tennessee", "texas", "floride", "californie", "new york", "cnn", "pentagone", "congrès américain",
    "cour suprême des états-unis", "sénat américain", "gouverneur du", "midterms", "lula", "bolsonaro",
    "ebola", "rdc", "kinshasa", "lettonie",
]


def _sans_accents(txt: str) -> str:
    """Minuscules sans accents : « Etats-Unis » (sans accent, fréquent dans les flux) = « États-Unis »."""
    return unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode("ascii").lower()


def _compile(mots: list[str]) -> re.Pattern:
    # Marqueurs ET textes comparés SANS ACCENTS (05/10/2026 : « Aux Etats-Unis » ne matchait pas « états-unis »).
    # frontières de mots tolérant les apostrophes / traits d'union.
    return re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(_sans_accents(m)) for m in sorted(mots, key=len, reverse=True)) + r")(?![\w-])",
                      re.UNICODE)


_RE_FR = _compile(MARQUEURS_FRANCE)
_RE_MONDE = _compile(MARQUEURS_MONDE)


def _score(regex: re.Pattern, titre: str, resume: str) -> int:
    t = set(regex.findall(_sans_accents(titre)))
    r = set(regex.findall(_sans_accents(resume))) - t
    return POIDS_TITRE * len(t) + POIDS_RESUME * len(r)


def _est_anglais(item: dict) -> bool:
    return "new york times" in str(item.get("source", "")).lower()


def zone_par_contenu(item: dict, zone_flux: str) -> str:
    """Zone (« france » | « monde ») d'un item, d'après son contenu ; `zone_flux` si indécidable."""
    if _est_anglais(item):
        return "monde"
    titre, resume = item.get("titre", ""), item.get("resume", "")
    fr, mo = _score(_RE_FR, titre, resume), _score(_RE_MONDE, titre, resume)
    if fr - mo >= ECART_MIN:
        return "france"
    if mo - fr >= ECART_MIN:
        return "monde"
    return zone_flux


def assigner_zones(items_france: list[dict], items_monde: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """Réaffecte chaque item brut à sa zone de contenu. N'altère pas les listes d'entrée.

    Retourne (france, monde, stats) ; `stats` = {"vers_monde": n, "vers_france": n}. Les items déplacés
    sont copiés avec `categorie` mis à jour (la dédup ne regroupe que des items de même catégorie)."""
    france, monde = [], []
    stats = {"vers_monde": 0, "vers_france": 0}
    for zone_flux, items in (("france", items_france), ("monde", items_monde)):
        for it in items:
            zone = zone_par_contenu(it, zone_flux)
            if zone != zone_flux:
                stats["vers_monde" if zone == "monde" else "vers_france"] += 1
                logger.info("Zone par contenu: %s -> %s | %s", zone_flux, zone, str(it.get("titre", ""))[:90])
                it = dict(it, categorie=zone)
            (france if zone == "france" else monde).append(it)
    logger.info("Affectation France/Monde par contenu: %s", stats)
    return france, monde, stats


def marqueurs_monde(texte: str) -> list[str]:
    """Marqueurs « étranger » trouvés dans `texte` (utilisé par diversite.py pour repérer les sujets)."""
    return sorted(set(_RE_MONDE.findall(_sans_accents(texte))))
