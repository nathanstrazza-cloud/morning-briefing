"""Garde-fous de la section « Anglais du jour » (point 7 de ANALYSE_RUN_2026-10-01.md).

Problèmes constatés le 01/10 : « centrist » traduit « centré » (au lieu de « centriste »),
vocabulaire trop facile (Prime Minister, lawyer, politician…). Le LLM ne peut pas être
« relu » de façon fiable par un second modèle (quotas) : on applique donc des contrôles
DÉTERMINISTES après sa réponse.

1. `filtrer_mots()` : retire les mots triviaux (liste `MOTS_FACILES`), les mots absents du texte
   source (invention), les doublons, les entrées sans traduction ; plafonne à 8.
2. `GLOSSAIRE` : traductions imposées pour les termes d'actualité à piège (faux amis, suffixes
   « -ist/-iste ») ; la traduction du LLM est remplacée si le mot y figure.
3. `score_apprentissage()` : choisit, parmi les articles NYT du jour, celui qui contient le plus
   de vocabulaire de niveau B2/C1 (mots longs et non triviaux), plutôt que le résumé le plus long.
Aucun appel réseau ; tout est testé dans tests/test_anglais_guard.py.
"""
from __future__ import annotations

import re

MAX_MOTS = 8

# Mots (et expressions) trop faciles pour un apprenant visant B2/C1 : exclus des « mots importants ».
MOTS_FACILES = {
    # fonctionnels / très courants
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "at", "by", "for", "with",
    "from", "about", "after", "before", "between", "over", "under", "new", "old", "big", "small",
    "good", "bad", "first", "last", "year", "years", "day", "days", "week", "month", "time",
    "people", "man", "woman", "men", "women", "child", "children", "family", "home", "house",
    "work", "worker", "workers", "say", "said", "says", "make", "made", "take", "took", "go",
    "went", "come", "came", "get", "got", "give", "gave", "know", "think", "want", "need",
    "find", "found", "tell", "told", "ask", "asked", "use", "try", "call", "called",
    # actualité : vocabulaire de base que le professeur ne doit pas retenir
    "president", "prime minister", "minister", "government", "country", "countries", "city",
    "state", "states", "world", "war", "peace", "police", "court", "judge", "lawyer", "lawyers",
    "politician", "politicians", "politics", "political", "election", "elections", "vote",
    "voters", "party", "leader", "leaders", "official", "officials", "company", "companies",
    "business", "economy", "money", "price", "prices", "market", "news", "report", "reported",
    "attack", "killed", "dead", "death", "died", "army", "military", "soldier", "soldiers",
    "law", "laws", "plan", "plans", "deal", "talks", "meeting", "group", "groups", "million",
    "billion", "percent", "week", "weekend", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday", "united states", "china", "russia", "europe", "israel",
    "ukraine", "trump", "biden",
}

# Traductions imposées (clé en minuscules, forme telle qu'elle apparaît ou sa racine).
GLOSSAIRE = {
    "centrist": "centriste",
    "centrists": "centristes",
    "moderate": "modéré(e) (en politique : un modéré)",
    "incumbent": "sortant(e) (titulaire d'un mandat)",
    "lawmaker": "parlementaire, législateur",
    "lawmakers": "parlementaires, législateurs",
    "ruling": "décision de justice (jugement)",
    "ballot": "bulletin de vote ; scrutin",
    "runoff": "second tour",
    "snap election": "élection anticipée",
    "caretaker": "(gouvernement) intérimaire",
    "stalemate": "impasse",
    "crackdown": "répression, mesures de fermeté",
    "ceasefire": "cessez-le-feu",
    "truce": "trêve",
    "sanction": "sanction (au sens politique : mesure punitive ; attention : « to sanction » peut aussi signifier autoriser)",
    "eventually": "finalement, à terme (faux ami : pas « éventuellement »)",
    "actually": "en réalité (faux ami : pas « actuellement »)",
    "currently": "actuellement",
    "assume": "supposer (faux ami : pas « assumer »)",
    "resume": "reprendre (faux ami : pas « résumer »)",
    "pretend": "faire semblant (faux ami : pas « prétendre »)",
    "demand": "exiger, revendiquer (faux ami : pas « demander »)",
    "attend": "assister à (faux ami : pas « attendre »)",
    "deceive": "tromper",
    "scrutiny": "examen minutieux, contrôle",
    "backlash": "levée de boucliers, réaction hostile",
    "bipartisan": "soutenu par les deux grands partis",
    "filibuster": "obstruction parlementaire",
    "gerrymandering": "découpage électoral partisan",
    "embattled": "en difficulté, assiégé",
    "landmark": "(décision) historique, qui fait date",
}

_WORD = re.compile(r"[a-zA-Z][a-zA-Z'\-]*")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().strip(".,;:!?\"'()[]").lower())


def _tokens(texte: str) -> list[str]:
    return [t.lower() for t in _WORD.findall(texte or "")]


def _dans_source(mot: str, texte_source: str) -> bool:
    """Le mot/l'expression figure bien dans le titre+résumé (tolère pluriel/conjugaison)."""
    m = _norm(mot)
    if not m:
        return False
    low = (texte_source or "").lower()
    if m in low:
        return True
    toks = _tokens(m)
    if not toks:
        return False
    # chaque jeton doit avoir sa racine (au moins 5 lettres, sinon forme exacte) dans la source
    src = set(_tokens(low))
    for t in toks:
        racine = t[:-1] if len(t) <= 5 else t[: max(5, len(t) - 3)]
        if t not in src and not any(s.startswith(racine) for s in src):
            return False
    return True


def _est_facile(mot: str) -> bool:
    m = _norm(mot)
    if m in MOTS_FACILES:
        return True
    toks = _tokens(m)
    # une expression de plusieurs mots n'est « facile » que si tous ses mots le sont
    return bool(toks) and all(t in MOTS_FACILES for t in toks)


def filtrer_mots(mots, titre: str, resume: str) -> tuple[list[dict], dict]:
    """Retourne (mots_filtrés, stats). Ne lève jamais : une entrée invalide est simplement retirée."""
    source = f"{titre or ''} {resume or ''}"
    stats = {"recus": 0, "faciles": 0, "absents_source": 0, "sans_traduction": 0, "doublons": 0,
             "glossaire": 0}
    if not isinstance(mots, list):
        return [], stats
    vus, out = set(), []
    for m in mots:
        stats["recus"] += 1
        if not isinstance(m, dict):
            continue
        mot, trad = str(m.get("mot") or "").strip(), str(m.get("traduction") or "").strip()
        if not mot or not trad or _norm(trad) == _norm(mot):
            stats["sans_traduction"] += 1
            continue
        cle = _norm(mot)
        if cle in vus:
            stats["doublons"] += 1
            continue
        if _est_facile(mot):
            stats["faciles"] += 1
            continue
        if not _dans_source(mot, source):
            stats["absents_source"] += 1
            continue
        vus.add(cle)
        entree = {"mot": mot, "traduction": trad, "exemple": str(m.get("exemple") or "").strip()}
        imposee = GLOSSAIRE.get(cle)
        if imposee and _norm(imposee) != _norm(trad):
            entree["traduction"] = imposee
            stats["glossaire"] += 1
        out.append(entree)
        if len(out) >= MAX_MOTS:
            break
    return out, stats


def score_apprentissage(titre: str, resume: str) -> float:
    """Score d'intérêt pédagogique d'un extrait : nombre de mots distincts de niveau soutenu
    (>= 8 lettres, non triviaux) + mots du glossaire, avec une longueur de résumé utile
    (80 à 400 caractères ; trop court = peu de matière, trop long = écrasant)."""
    texte = f"{titre or ''} {resume or ''}"
    toks = set(_tokens(texte))
    soutenus = {t for t in toks if len(t) >= 8 and t not in MOTS_FACILES}
    glossaire = {t for t in toks if t in GLOSSAIRE}
    longueur = len(resume or "")
    bonus = 2.0 if 80 <= longueur <= 400 else 0.0
    return len(soutenus) + 2 * len(glossaire) + bonus
