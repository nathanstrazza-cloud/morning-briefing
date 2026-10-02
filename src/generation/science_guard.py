"""Garde-fous « science » appliqués par le CODE après la rédaction LLM (cahier §1, §7, §11).

Pourquoi (cf. ANALYSE_RUN_2026-10-01.md §1, confirmé le 02/10/2026) : les rédacteurs ne reçoivent
que le titre + le résumé RSS d'UN article, mais le plan exige « Données et résultats… ». Les petits
modèles comblent avec des chiffres plausibles et de fausses sources. Le prompt seul ne suffit pas :
ce module (1) retire toute phrase contenant un nombre absent de la source, (2) supprime les
marqueurs internes, (3) harmonise les titres, (4) remplace la section « Sources » écrite par le LLM
par une section construite à partir des liens réellement fournis.

Fonctions pures, sans réseau : voir tests/test_science_guard.py.
"""
from __future__ import annotations

import re

_NUM_RE = re.compile(r"\d[\d\s\u00a0\u202f.,]*\d|\d")
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[«\"A-ZÀ-Ý0-9*])")
_MARKER_RE = re.compile(r"^\W*\(?\s*(fin de la moiti|la suite (abordera|sera)|suite (de l'article )?dans)", re.I)
_HEADING_RE = re.compile(r"^(#{1,6})\s*(.*)$")


def _norm_number(tok: str) -> str:
    t = re.sub(r"[\s\u00a0\u202f]", "", tok).replace(",", ".")
    t = t.strip(".")
    # « 18.542 » (séparateur de milliers) et « 18542 » doivent être équivalents ; « 3.5 » reste décimal.
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        t = t.replace(".", "")
    return t


def _significant(tok: str, context_after: str) -> bool:
    n = _norm_number(tok)
    digits = n.replace(".", "")
    if "." in n or context_after.lstrip().startswith("%") or "%" in context_after[:2]:
        return True
    return len(digits) >= 2          # un chiffre isolé (« 3 facteurs ») n'est pas une donnée


def source_numbers(*texts: str) -> set[str]:
    nums: set[str] = set()
    for t in texts:
        for m in _NUM_RE.finditer(t or ""):
            nums.add(_norm_number(m.group()))
    return nums


def unsupported_numbers(sentence: str, allowed: set[str]) -> list[str]:
    bad = []
    for m in _NUM_RE.finditer(sentence):
        if _significant(m.group(), sentence[m.end():m.end() + 2]) and _norm_number(m.group()) not in allowed:
            bad.append(m.group().strip())
    return bad


def strip_markers(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not _MARKER_RE.match(l.strip()))


def normalize_headings(text: str) -> str:
    """`## **Introduction**` / `## 5. Données` -> `## Introduction` / `## Données` (format unique)."""
    out = []
    for line in text.splitlines():
        m = _HEADING_RE.match(line.strip())
        if m:
            titre = m.group(2).replace("*", "").strip()
            titre = re.sub(r"^\d+\s*[.)]\s*", "", titre)
            out.append(f"## {titre}" if titre else "")
        else:
            out.append(line)
    # `---` isolés en tête/doublons : bruit des modèles
    txt = "\n".join(out)
    txt = re.sub(r"^\s*---\s*\n", "", txt)
    return re.sub(r"\n{3,}", "\n\n", txt).strip()


def remove_llm_sources(text: str) -> str:
    """Retire la section « Sources » rédigée par le LLM (jusqu'à la fin) : elle est refaite par le code."""
    lines = text.splitlines()
    for i, l in enumerate(lines):
        m = _HEADING_RE.match(l.strip())
        if m and re.search(r"\bsources?\b|références", m.group(2), re.I):
            return "\n".join(lines[:i]).strip()
    return text


def remove_unsupported_numbers(text: str, allowed: set[str]) -> tuple[str, list[str]]:
    """Supprime les phrases contenant un nombre significatif absent de la source. Retourne (texte, phrases retirées)."""
    removed: list[str] = []
    out: list[str] = []
    for line in text.splitlines():
        if not line.strip() or _HEADING_RE.match(line.strip()):
            out.append(line)
            continue
        prefix = re.match(r"^\s*([-*•]|\d+[.)])?\s*", line).group(0)
        body = line[len(prefix):]
        kept = []
        for s in _SENT_SPLIT.split(body):
            if unsupported_numbers(s, allowed):
                removed.append(s.strip())
            else:
                kept.append(s)
        if kept:
            out.append(prefix + " ".join(kept))
        # sinon : ligne entièrement retirée
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip(), removed


def build_sources_section(contenu_source: dict) -> str:
    nom = ", ".join(contenu_source.get("sources") or []) or "source indiquée"
    url = contenu_source.get("url") or ""
    lignes = ["## Sources", f"- Article source : {contenu_source.get('titre', '')} ({nom})" + (f" — {url}" if url else "")]
    lignes.append("- Les chiffres et affirmations de cet article se limitent à ceux de cette source ; "
                  "les détails de l'étude sont à consulter sur le lien ci-dessus.")
    return "\n".join(lignes)


def guard_science_article(contenu: str, contenu_source: dict) -> tuple[str, list[str]]:
    """Pipeline complet. `contenu` = moitiés A+B concaténées. Retourne (texte final, phrases retirées)."""
    allowed = source_numbers(contenu_source.get("titre", ""), contenu_source.get("resume", ""))
    t = strip_markers(contenu)
    t = normalize_headings(t)
    t = remove_llm_sources(t)
    t, removed = remove_unsupported_numbers(t, allowed)
    return (t + "\n\n" + build_sources_section(contenu_source)).strip(), removed
