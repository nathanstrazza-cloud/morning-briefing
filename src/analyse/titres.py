"""Nettoyage des titres/résumés bruts des flux (11/10/2026, ANALYSE_RUN_2026-10-11.md §2.3-2.4).

Constat : « EN DIRECT … » et « … » (titre coupé par le flux) étaient affichés tels quels, et un résumé de direct
(« Suivez avec nous les informations… ») n'apporte aucun fait. Fonctions pures, sans réseau.
"""
from __future__ import annotations

import re

_PREFIXE = re.compile(r"^\s*(?:EN\s+DIRECT|DIRECT|LIVE|EN\s+IMAGES|VID[ÉE]O|REPLAY|[ÀA]\s+SUIVRE)\s*[,:;–—-]*\s*", re.I)
_EMOJI_DEBUT = re.compile(r"^[^\w«\"“'‘’(\[]+")
_ELLIPSE_FIN = re.compile(r"\s*(?:…|\.{3,})\s*$")
_RESUME_DIRECT = re.compile(r"^\s*(?:suivez|retrouvez|notre direct|dans ce direct|suivre en direct)\b", re.I)


def nettoyer_titre(titre: str) -> str:
    """Retire emoji/préfixes « EN DIRECT », ellipse finale ; majuscule initiale. Titre trop court après nettoyage = inchangé."""
    original = str(titre or "").strip()
    t = original
    for _ in range(3):
        n = _EMOJI_DEBUT.sub("", t)
        n = _PREFIXE.sub("", n)
        if n == t:
            break
        t = n
    t = _ELLIPSE_FIN.sub("", t).strip()
    if len(t) < 12:
        return original
    return t[0].upper() + t[1:]


def nettoyer_resume(resume: str) -> str:
    """Un résumé de direct (« Suivez avec nous… ») ne contient aucun fait : on le vide."""
    r = str(resume or "").strip()
    return "" if _RESUME_DIRECT.match(r) else r


def nettoyer_items(items: list[dict]) -> list[dict]:
    """Copies des items avec titre/résumé nettoyés (les listes d'entrée ne sont pas modifiées)."""
    out = []
    for it in items:
        c = dict(it)
        c["titre"] = nettoyer_titre(c.get("titre", ""))
        c["resume"] = nettoyer_resume(c.get("resume", ""))
        out.append(c)
    return out
