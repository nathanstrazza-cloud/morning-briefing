"""Garde-fou « actualité » appliqué par le CODE après la rédaction LLM (point 3 de l'analyse du 01/10).

Constat (briefings des 01 et 02/10) : malgré « n'invente rien », les petits modèles ajoutent des
éléments absents des données (« l'ancien président » pour Trump, « première échec depuis 2023 »,
« les autorités n'ont pas encore commenté », « tensions syndicales »). Ce module compare chaque
texte rédigé aux données d'entrée (titre + résumé de l'événement correspondant) et :
- retire les phrases contenant un nombre significatif absent de la source ;
- retire les phrases contenant un marqueur « risqué » (ancien, première fois, pas encore commenté…)
  absent de la source ;
- préfixe « Hypothèse : » aux conséquences (cahier §14 : une conséquence n'est pas un fait) ;
- impose le statut de vérification calculé par le code (nombre de sources), pas celui du LLM ;
- si le résumé est vidé, retombe sur le résumé source.
Fonctions pures, sans réseau : voir tests/test_actu_guard.py.
"""
from __future__ import annotations

import re

from ..analyse.dedup import _similarity
from .science_guard import _SENT_SPLIT, source_numbers, unsupported_numbers

MATCH_MIN = 0.3
# Marqueurs qui sont de l'information ajoutée dès qu'ils n'apparaissent pas dans la source.
_RISKY = re.compile(
    r"\b(ancien(?:ne)?s?|ex-\w+|premi[èe]re? (?:fois|échec|échecs)|pour la premi[èe]re fois|"
    r"pas encore (?:comment|réagi|répondu)\w*|n['’]ont pas (?:encore )?(?:comment|réagi)\w*|"
    r"sans précédent|historique)\b",
    re.I,
)


def _risky_terms(sentence: str) -> set[str]:
    return {m.group(0).lower() for m in _RISKY.finditer(sentence)}


def best_source(titre: str, source_events: list[dict]) -> dict | None:
    best, score = None, 0.0
    for e in source_events:
        sc = _similarity(titre or "", e.get("titre", ""))
        if sc > score:
            best, score = e, sc
    return best if score >= MATCH_MIN else None


def clean_text(text: str | None, source_text: str, allowed: set[str]) -> tuple[str | None, list[str]]:
    """Retire les phrases non étayées. Retourne (texte nettoyé ou None, phrases retirées)."""
    if not text:
        return text, []
    low_source = source_text.lower()
    kept, removed = [], []
    for s in _SENT_SPLIT.split(text.strip()):
        bad_num = unsupported_numbers(s, allowed)
        bad_terms = [t for t in _risky_terms(s) if t not in low_source]
        if bad_num or bad_terms:
            removed.append(s.strip())
        else:
            kept.append(s)
    out = " ".join(kept).strip()
    return (out or None), removed


def guard_events(llm_events: list[dict], source_events: list[dict]) -> tuple[list[dict], list[str]]:
    """`llm_events` : liste rédigée par le LLM ; `source_events` : événements d'entrée (titre/resume/statut_verification)."""
    result, all_removed = [], []
    for ev in llm_events or []:
        ev = dict(ev)
        src = best_source(ev.get("titre", ""), source_events)
        if src is not None:
            source_text = f"{src.get('titre', '')} {src.get('resume', '')}"
            ev["statut"] = src.get("statut_verification", ev.get("statut"))
        else:
            # Pas de correspondance sûre : référence = ensemble des données de la zone (contrôle plus faible).
            source_text = " ".join(f"{e.get('titre', '')} {e.get('resume', '')}" for e in source_events)
        allowed = source_numbers(source_text, ev.get("titre", ""))
        for champ in ("resume", "pourquoi_important", "consequences"):
            nouveau, removed = clean_text(ev.get(champ), source_text, allowed)
            all_removed += removed
            ev[champ] = nouveau
        if not ev.get("resume") and src is not None and src.get("resume"):
            ev["resume"] = src["resume"]
        # « Pourquoi c'est important » est de l'analyse : étayé par la source -> tel quel ; sinon marqué comme hypothèse.
        pi = ev.get("pourquoi_important")
        if pi and not re.match(r"\s*hypoth[èe]se", pi, re.I) and overlap_ratio(pi, source_text) < 0.5:
            ev["pourquoi_important"] = "Hypothèse : " + pi[0].lower() + pi[1:]
        if ev.get("consequences") and not re.match(r"\s*hypoth[èe]se", ev["consequences"], re.I):
            ev["consequences"] = "Hypothèse : " + ev["consequences"][0].lower() + ev["consequences"][1:]
        result.append(ev)
    return result, all_removed


# --- Marchés (03/10/2026) -----------------------------------------------------------------
# Constat du Dev Test du 03/10 : le LLM expliquait la hausse du Nasdaq/DAX par « l'augmentation des
# dépenses de défense russe », cause sans rapport avec les articles économiques fournis. Règle :
# une explication n'est conservée que si l'essentiel de ses mots se retrouve dans ces articles ;
# les variations affichées viennent TOUJOURS des données chiffrées, jamais du LLM.
_STOP = {"dans", "avec", "pour", "cette", "ainsi", "leur", "leurs", "plus", "sont", "être", "elle", "elles",
         "après", "avant", "entre", "selon", "depuis", "comme", "aussi", "mais", "dont", "tout", "tous"}
EXPLICATION_MIN_OVERLAP = 0.5
RESUME_MARCHES_SANS_CAUSE = "Aucune cause fiable n'a pu être établie à partir des articles collectés ce matin."


def _mots(texte: str) -> set[str]:
    return {m for m in re.findall(r"[a-zàâäéèêëïîôöùûüç0-9]+", (texte or "").lower()) if len(m) > 3 and m not in _STOP}


def overlap_ratio(texte: str, source_text: str) -> float:
    mots = _mots(texte)
    return (len(mots & _mots(source_text)) / len(mots)) if mots else 0.0


def guard_marches(m: dict, analysed: dict | None) -> dict:
    """`m` : dict marchés normalisé (resume_court, mouvements_notables). Retourne une copie corrigée."""
    if not analysed:
        return m
    out = dict(m)
    data = analysed.get("marches_data") or {}
    quotes = {q["name"].lower(): q for q in (data.get("indices") or []) + (data.get("matieres_premieres") or [])
              if q.get("name") and q.get("variation_pct") is not None}
    eco_text = " ".join(f"{e.get('titre', '')} {e.get('resume', '')}" for e in analysed.get("actualite_economie") or [])
    mouvements, gardees = [], 0
    for x in out.get("mouvements_notables") or []:
        q = quotes.get(str(x.get("nom", "")).lower())
        if q is None:
            continue                                   # mouvement inconnu des données chiffrées : écarté
        expl = x.get("explication")
        if expl and overlap_ratio(expl, eco_text) < EXPLICATION_MIN_OVERLAP:
            expl = None
        gardees += 1 if expl else 0
        mouvements.append({"nom": q["name"], "variation_pct": q["variation_pct"], "explication": expl})
    out["mouvements_notables"] = mouvements
    resume, _ = clean_text(out.get("resume_court"), eco_text, source_numbers(eco_text))
    if mouvements and gardees == 0:
        resume = RESUME_MARCHES_SANS_CAUSE
    out["resume_court"] = resume or ""
    return out
