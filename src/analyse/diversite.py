"""Diversité de la sélection d'actualité + fusion des doublons par entités (05/10/2026).

Problèmes corrigés (ANALYSE_RUN_2026-10-05.md, points 6 et 7) :
- plusieurs événements du MÊME sujet (ex. 6 articles sur la présidentielle brésilienne, 3 sur les midterms)
  occupaient tous les 5 emplacements d'une zone ;
- un même événement présenté par deux médias avec des titres différents n'était pas fusionné
  (« Christa Pike… » : similarité de titres sous le seuil).

Deux fonctions pures, sans LLM ni réseau :
- `fusionner_par_entites` : fusionne les événements qui partagent >= 2 entités RARES (noms propres peu fréquents
  dans le lot : « Christa » + « Pike »). Une entité présente dans plus de `FREQUENCE_MAX` titres est trop banale
  (Trump, Macron…) pour prouver une identité d'événement.
- `selectionner_diversifie` : garde les `n` meilleurs en limitant à `MAX_PAR_ENTITE` le nombre d'événements
  d'une même entité ; complète ensuite avec les restants si la liste reste trop courte.
"""
from __future__ import annotations

import logging
import re
import unicodedata

from src.analyse import zones

logger = logging.getLogger("morning_briefing.analyse.diversite")

FREQUENCE_MAX = 3
MAX_PAR_ENTITE = 2
_BANALES = {"selon", "avec", "dans", "pour", "apres", "avant", "entre", "contre", "depuis", "alors", "mais",
            "cette", "comme", "tout", "tous", "plus", "dont", "leur", "leurs", "nous", "vous", "etat", "etats"}


def _sans_accents(txt: str) -> str:
    return unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode("ascii").lower()


_RE_MOT_CAP = re.compile(r"[A-ZÀ-ÖØ-Þ][\w'’-]{3,}")


def entites(titre: str) -> set[str]:
    """Entités d'un titre : noms propres (mots capitalisés hors 1er mot) + marqueurs pays/personnes de zones.py."""
    titre = titre or ""
    out: set[str] = set()
    mots = titre.split(None, 1)
    reste = mots[1] if len(mots) > 1 else ""
    # 1er mot : retenu seulement s'il forme un NOM avec le suivant (« Christa Pike… »), pas pour « Guerre », « Pluies »…
    suite = _RE_MOT_CAP.match(reste)
    if mots and suite and _RE_MOT_CAP.fullmatch(re.sub(r"[,:;]$", "", mots[0])):
        k0 = _sans_accents(mots[0]).strip("'’-,:;")
        if k0 and k0 not in _BANALES:
            out.add(k0)
    for m in _RE_MOT_CAP.findall(reste):
        k = _sans_accents(m).strip("'’-")
        if k and k not in _BANALES:
            out.add(k)
    for m in zones.marqueurs_monde(titre):
        out.add(_sans_accents(m))
    return out


def _fusionner(cible: dict, autre: dict) -> None:
    deja = {s["nom"] for s in cible["sources"]}
    for src in autre["sources"]:
        if src["nom"] not in deja:
            cible["sources"].append(src)
            deja.add(src["nom"])
    cible["nb_sources"] = len(cible["sources"])
    if len(autre.get("titre", "")) > len(cible.get("titre", "")):
        cible["titre"] = autre["titre"]
    if not cible.get("resume") and autre.get("resume"):
        cible["resume"] = autre["resume"]
    dates = [d for d in (cible.get("date_publication"), autre.get("date_publication")) if d]
    cible["date_publication"] = min(dates) if dates else None


def fusionner_par_entites(events: list[dict]) -> list[dict]:
    """Fusionne les événements partageant >= 2 entités rares. Ne modifie pas la liste d'entrée."""
    evs = [dict(e, sources=list(e["sources"])) for e in events]
    ents = [entites(e["titre"]) for e in evs]
    freq: dict[str, int] = {}
    for s in ents:
        for x in s:
            freq[x] = freq.get(x, 0) + 1
    rares = [{x for x in s if freq[x] <= FREQUENCE_MAX} for s in ents]
    gardes: list[int] = []
    n_fusions = 0
    for i, e in enumerate(evs):
        cible = next((j for j in gardes if len(rares[i] & rares[j]) >= 2), None)
        if cible is None:
            gardes.append(i)
            continue
        _fusionner(evs[cible], e)
        rares[cible] |= rares[i]
        n_fusions += 1
        logger.info("Fusion par entités: « %s » -> « %s »", str(e["titre"])[:70], str(evs[cible]["titre"])[:70])
    logger.info("Fusion par entités: %d événement(s) fusionné(s)", n_fusions)
    return [evs[i] for i in gardes]


def selectionner_diversifie(events_tries: list[dict], n: int, max_par_entite: int = MAX_PAR_ENTITE) -> list[dict]:
    """`events_tries` : déjà triés par importance décroissante. Retourne au plus `n` événements."""
    retenus: list[dict] = []
    compte: dict[str, int] = {}
    restants: list[dict] = []
    for e in events_tries:
        if len(retenus) >= n:
            break
        es = entites(e["titre"])
        if any(compte.get(x, 0) >= max_par_entite for x in es):
            restants.append(e)
            continue
        retenus.append(e)
        for x in es:
            compte[x] = compte.get(x, 0) + 1
    # complément seulement si la zone est trop courte (jamais au détriment d'un sujet différent)
    for e in restants:
        if len(retenus) >= n:
            break
        retenus.append(e)
    ecartes = len(events_tries) - len(retenus)
    logger.info("Sélection diversifiée: %d retenu(s) sur %d (limite %d par entité)", len(retenus), len(events_tries),
                max_par_entite)
    return retenus
