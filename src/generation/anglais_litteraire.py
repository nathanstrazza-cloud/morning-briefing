"""Anglais du jour (refonte du 10/10/2026) : passage littéraire du DOMAINE PUBLIC avec traductions EN LIGNE.

Demande de l'utilisateur : un texte d'une dizaine de lignes, avec seulement la traduction des mots difficiles
entre parenthèses (« …I like mot_compliqué (= traduction) blabla »), sans liste de vocabulaire ; l'ancienne version
(titre + résumé RSS du NYT, 2 lignes) était trop courte, trop simple, avec des mots transparents, et reprenait
souvent une actualité déjà présente dans la section Actualité.

Choix : banque `config/anglais_textes.json` (comme la citation du jour) -> aucun LLM, aucun quota, texte exact
(pas de traduction inventée, droit d'auteur respecté : œuvres de plus de 70 ans). Tirage déterministe par date.
Le mode « actualité » n'est PAS repris : un flux RSS ne fournit que 2 lignes et le texte complet d'un article est
protégé ; voir SUIVI_CORRECTIFS.md pour les pistes (Wikinews, CC BY).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path

logger = logging.getLogger("morning_briefing.generation")
BANQUE = Path(__file__).resolve().parents[2] / "config" / "anglais_textes.json"


def load_bank(path: Path = BANQUE) -> list[dict]:
    try:
        items = json.loads(path.read_text(encoding="utf-8")).get("passages", [])
    except (OSError, ValueError) as exc:
        logger.warning("Banque anglais illisible (%s) : %s", path, exc)
        return []
    return [p for p in items if p.get("texte") and p.get("oeuvre") and p.get("auteur")]


def build_segments(texte: str, mots: list[dict]) -> list[dict]:
    """Découpe `texte` en segments {"t": texte, "g": traduction|None} : la glose suit la 1re occurrence (mot entier)
    de chaque expression. Une expression absente ou chevauchant une précédente est ignorée (journalisée)."""
    reperes = []
    for m in mots:
        en, fr = m.get("en", ""), m.get("fr", "")
        hit = re.search(r"(?<!\w)" + re.escape(en) + r"(?!\w)", texte, re.IGNORECASE) if en and fr else None
        if hit is None:
            logger.warning("Anglais : expression %r absente du texte, ignorée", en)
            continue
        reperes.append((hit.start(), hit.end(), fr))
    reperes.sort()
    segments, pos = [], 0
    for debut, fin, fr in reperes:
        if debut < pos:
            logger.warning("Anglais : glose chevauchante ignorée (%r)", texte[debut:fin])
            continue
        segments.append({"t": texte[pos:fin], "g": fr})
        pos = fin
    if pos < len(texte):
        segments.append({"t": texte[pos:], "g": None})
    return segments


def passage_du_jour(jour: date, bank: list[dict] | None = None) -> dict | None:
    bank = load_bank() if bank is None else bank
    if not bank:
        return None
    p = bank[jour.toordinal() % len(bank)]
    segments = build_segments(p["texte"], p.get("mots", []))
    return {
        "mode": "litterature",
        "oeuvre": p["oeuvre"], "auteur": p["auteur"], "annee": p.get("annee"),
        "segments": segments,
        "texte_glose": "".join(s["t"] + (f" (= {s['g']})" if s["g"] else "") for s in segments),
    }
