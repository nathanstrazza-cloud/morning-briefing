"""Regroupement des articles « sciences » qui parlent du MÊME événement, y compris entre français et anglais
(06/10/2026, point 1 de ANALYSE_RUN_2026-10-06.md).

Problème : le Nobel de médecine était couvert par 4 articles (Le Monde, Nature, etc.). La déduplication classique
(similarité de titres, même langue) ne les regroupait pas ; l'événement avait donc « une seule source non primaire »,
le mode « découverte » était refusé et l'article « approfondi » reposait sur UN seul résumé RSS.

Méthode (fonctions pures, sans réseau ni LLM) : chaque article est réduit à un ensemble de RACINES (5 premières lettres
des mots de 5 lettres ou plus, sans accents) calculées sur titre + résumé. « neurones » et « neurons » donnent la même
racine « neuro », « Nobel » = « nobel ». On ne retient que les racines RARES dans le lot (présentes dans peu
d'articles). Deux articles sont fusionnés s'ils partagent au moins `MIN_PARTAGEES` racines rares.
La fusion conserve le texte de chaque source (`textes_sources`) pour que le rédacteur dispose de plusieurs résumés.
"""
from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger("morning_briefing.analyse.science_events")

MIN_PARTAGEES = 3          # racines rares communes pour fusionner
FREQUENCE_MAX = 5          # une racine présente dans plus d'articles est trop banale
LONGUEUR_RACINE = 5
_MOTS_VIDES = {
    "apres", "avant", "avec", "dans", "pour", "cette", "ainsi", "leur", "leurs", "plus", "sont", "elle", "elles",
    "entre", "selon", "depuis", "comme", "alors", "aussi", "mais", "donc", "dont", "tout", "tous", "toute", "toutes",
    "etude", "etudes", "scien", "chercheurs", "chercheuses", "resultats", "nouvelle", "nouveau", "nouveaux",
    "about", "after", "their", "there", "these", "those", "which", "would", "could", "other", "study", "studies",
    "research", "scientists", "researchers", "while", "where", "being", "years", "first", "since", "using",
}
_RE_MOT = re.compile(r"[a-z0-9]+")


def _fold(txt: str) -> str:
    return unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode("ascii").lower()


def racines(event: dict) -> set[str]:
    texte = _fold(f"{event.get('titre', '')} {event.get('resume', '')}")
    out = set()
    for mot in _RE_MOT.findall(texte):
        if len(mot) < LONGUEUR_RACINE or mot in _MOTS_VIDES or mot.isdigit():
            continue
        r = mot[:LONGUEUR_RACINE]
        if r not in _MOTS_VIDES:
            out.add(r)
    return out


def _texte_source(e: dict) -> dict:
    return {"source": ", ".join(s["nom"] for s in e.get("sources", [])),
            "titre": e.get("titre", ""), "resume": e.get("resume", "")}


def fusionner_evenements_science(events: list[dict]) -> list[dict]:
    """Fusionne les événements partageant >= MIN_PARTAGEES racines rares. N'altère pas la liste d'entrée.
    Chaque événement retourné porte `textes_sources` (liste de {source, titre, resume}) ; le résumé retenu est le plus long."""
    evs = [dict(e, sources=list(e.get("sources", []))) for e in events]
    rac = [racines(e) for e in evs]
    freq: dict[str, int] = {}
    for s in rac:
        for r in s:
            freq[r] = freq.get(r, 0) + 1
    rares = [{r for r in s if freq[r] <= FREQUENCE_MAX} for s in rac]
    gardes: list[int] = []
    for i, e in enumerate(evs):
        e.setdefault("textes_sources", [_texte_source(e)])
        cible = next((j for j in gardes if len(rares[i] & rares[j]) >= MIN_PARTAGEES), None)
        if cible is None:
            gardes.append(i)
            continue
        c = evs[cible]
        deja = {s["nom"] for s in c["sources"]}
        for s in e["sources"]:
            if s["nom"] not in deja:
                c["sources"].append(s)
                deja.add(s["nom"])
        c["nb_sources"] = len(c["sources"])
        c["textes_sources"] = c["textes_sources"] + e["textes_sources"]
        if len(str(e.get("resume") or "")) > len(str(c.get("resume") or "")):
            c["resume"] = e["resume"]
        if len(str(e.get("titre") or "")) > len(str(c.get("titre") or "")):
            c["titre"] = e["titre"]
        dates = [d for d in (c.get("date_publication"), e.get("date_publication")) if d]
        c["date_publication"] = min(dates) if dates else None
        rares[cible] |= rares[i]
        logger.info("Fusion sciences: « %s » -> « %s »", str(e["titre"])[:70], str(c["titre"])[:70])
    logger.info("Fusion sciences: %d événements -> %d", len(events), len(gardes))
    return [evs[i] for i in gardes]
