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

Révision du 10/10/2026 (point 2 de ANALYSE_RUN_2026-10-08.md) : une page « Qui sont les candidats déclarés à la
présidentielle 2027 ? » (liste) et un entretien culturel « De quoi la vague de films sur la Seconde Guerre mondiale
est-elle le nom ? » passaient pour des événements majeurs (« présidentielle », « guerre » dans le titre). Maintenant :
- MALUS LISTE / EXPLICATEUR (-5, -3 si l'événement est repris par >= 2 sources) : titres « Qui sont… », « N questions
  sur… », « Ce qu'il faut savoir », « De quoi… est-il le nom », « la liste de… » ; -2 de plus pour un titre
  interrogatif (« …? ») ;
- ENTRETIEN : les marqueurs forts (entretien, interview, propos recueillis, « se confie ») comptent aussi dans le
  RÉSUMÉ (1 occurrence suffit), et un titre qui commence par une citation est traité comme un propos rapporté ;
- pluriels des mots de culture (films, séries, livres…) ; plafond de malus porté de -5 à -6.
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
    "prise d'otages", "otages", "explosion", "peste", "choléra", "épidémique", "démission du gouvernement", "motion de censure",
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
    "films", "séries", "albums", "livres", "romans", "écrivains", "romanciers", "chanteurs", "acteurs", "concerts",
    "festivals", "expositions",
]
# Expressions FIGURÉES contenant un mot « majeur » (retirées avant le comptage : « guerre ouverte » entre voisins
# n'est pas une guerre).
EXPRESSIONS_FIGUREES = ["guerre ouverte", "guerre des étoiles", "guerre des prix", "guerre de tranchées", "guerre des nerfs",
                        "guerre des boutons", "guerre froide entre", "résidence présidentielle", "garde présidentielle"]
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

# --- MALUS 10/10/2026 : listes / pages explicatives et entretiens -------------------------------------
# Titres de type liste, « mode d'emploi » ou explicateur : ce ne sont pas des événements (la page recense ou
# explique, elle n'annonce pas un fait nouveau).
_NOMBRES = r"(?:\d+|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|douze)"
_RE_LISTE = re.compile(
    r"^\s*(?:qui sont|quels? sont|quelles? sont|que sait-on|que savons-nous|ce que (?:l['’]on |nous )?sait"
    r"|ce qu['’]il faut (?:savoir|retenir)|tout (?:savoir|comprendre)|tout ce qu['’]il faut)"
    r"|\bde quoi\b.{3,90}\best-(?:il|elle|ils|elles) le nom\b"
    r"|\b" + _NOMBRES + r"\s+(?:questions|choses|raisons|infos|informations|points|chiffres|photos|idées|clés"
    r"|enseignements|leçons|films|livres|séries|candidats)\b"
    r"|\ben " + _NOMBRES + r"\s+(?:questions|points|chiffres|dates)\b"
    r"|\bla liste (?:complète|des|de tous|de toutes)\b|\b(?:découvrez|voici|retrouvez|consultez)\b.{0,40}\bliste\b"
    r"|\bpalmarès\b|\bclassement des\b|\bles dates clés\b|\bde a à z\b|\brécapitulatif\b",
    re.IGNORECASE | re.UNICODE,
)
# Marqueurs FORTS d'entretien / propos rapportés : une seule occurrence (titre OU résumé) suffit.
_RE_INTERVIEW = re.compile(
    r"(?<![\w-])(?:entretien|interview|propos recueillis|se confie|nous confie|confie au|confie à)(?![\w-])",
    re.IGNORECASE | re.UNICODE,
)
_RE_TITRE_CITATION = re.compile(r"^\s*[«\"“]")
MALUS_MAX = 6


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
    nb_sources = event.get("nb_sources", 1)
    malus = 0
    if (_count_matches(titre, _RE_MALUS_FORMAT) or _count_matches(resume, _RE_MALUS_FORMAT) >= 2
            or _RE_INTERVIEW.search(text) or _RE_TITRE_CITATION.search(titre)):
        malus += 3
    if _count_matches(text, _RE_MALUS_FAITS_DIVERS):
        malus += 3
    if _count_matches(text, _RE_MALUS_CULTURE):
        malus += 2
    if re.search(r"\bpar\s+\d+\s+(?:anciens|ex-)", titre, re.IGNORECASE):  # tribune collective signée
        malus += 5
    # Liste / explicateur (10/10) : reprise par >= 2 médias = signal d'un vrai sujet derrière la page -> malus réduit.
    if _RE_LISTE.search(titre):
        malus += 3 if nb_sources >= 2 else 5
    if titre.rstrip().endswith("?"):
        malus += 2
    base -= min(MALUS_MAX, malus)
    if _count_matches(titre, _RE_RESULTAT):
        base += 1

    # Convergence de sources : plusieurs médias indépendants = signal d'importance (et de fiabilité, §11).
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
