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
import unicodedata

from ..analyse.dedup import _similarity
from .science_guard import _SENT_SPLIT, source_numbers, unsupported_numbers

MATCH_MIN = 0.3
PI_MIN_OVERLAP = 0.4        # part des mots de « pourquoi_important » retrouvés dans la source pour le garder
_CREUX = re.compile(r"\b(met(?:tent)? en lumière|soulève(?:nt)? des questions|illustre(?:nt)?|reste(?:nt)? à suivre|"
                    r"enjeux? (?:majeurs?|importants?)|pourrait avoir des (?:conséquences|répercussions)|"
                    r"suscite(?:nt)? des débats|controverses?)\b", re.I)
# Marqueurs qui sont de l'information ajoutée dès qu'ils n'apparaissent pas dans la source.
_RISKY = re.compile(
    r"\b(ancien(?:ne)?s?|ex-\w+|premi[èe]re? (?:fois|échec|échecs)|pour la premi[èe]re fois|"
    r"pas encore (?:comment|réagi|répondu)\w*|n['’]ont pas (?:encore )?(?:comment|réagi)\w*|"
    r"sans précédent|historique)\b",
    re.I,
)


# --- Noms propres (05/10/2026, point 1 de ANALYSE_RUN_2026-10-05.md) -------------------------------
# Constat : « visite du chancelier allemand Olaf Scholz » alors que la source disait « Merz ». Le garde-fou ne
# contrôlait que les nombres. Règle : tout mot capitalisé HORS début de phrase (nom de personne, d'institution,
# de lieu) doit figurer dans la source (titre + résumé), comparaison sans accents ni casse ; sinon la phrase est retirée.
# Mots capitalisés tolérés sans preuve (génériques, pas une information ajoutée) : voir _NOMS_TOLERES.
_NOMS_TOLERES = {
    "france", "français", "française", "europe", "européenne", "européen", "etat", "etats", "unis", "etat-unis",
    "republique", "gouvernement", "assemblee", "nationale", "senat", "parlement", "president", "premier", "ministre",
    "monde", "union", "conseil", "cour", "tribunal", "ministere", "nation", "nations", "pays", "ville",
}
_RE_NOM = re.compile(r"(?<![\w'’-])([A-ZÀ-ÖØ-Þ][\wÀ-ÿ'’-]{2,})")


def _fold(txt: str) -> str:
    return unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode("ascii").lower()


def _jetons_source(source_text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _fold(source_text)))


def unsupported_names(sentence: str, source_tokens: set[str]) -> list[str]:
    """Noms propres (mots capitalisés hors début de phrase) absents de la source. Fonction pure."""
    bad = []
    for m in _RE_NOM.finditer(sentence):
        if m.start() <= 1:                            # 1er mot de la phrase : la majuscule ne prouve rien
            continue
        mot = m.group(1)
        base = _fold(mot).strip("'’-")
        if base in _NOMS_TOLERES:
            continue
        jetons = [j for j in re.findall(r"[a-z0-9]+", base) if len(j) > 2 and j not in _NOMS_TOLERES]
        # « Jean-Noël » = 2 jetons : il suffit qu'ils soient TOUS dans la source pour accepter
        if jetons and not all(j in source_tokens or j.rstrip("s") in source_tokens for j in jetons):
            bad.append(mot)
    return bad


def _est_creux(texte: str) -> bool:
    """Formules passe-partout sans information (le LLM les génère faute de matière)."""
    return bool(_CREUX.search(texte or ""))


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
    tokens = _jetons_source(source_text)
    kept, removed = [], []
    for s in _SENT_SPLIT.split(text.strip()):
        bad_num = unsupported_numbers(s, allowed)
        bad_terms = [t for t in _risky_terms(s) if t not in low_source]
        bad_names = unsupported_names(s, tokens)
        if bad_num or bad_terms or bad_names:
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
        # « Pourquoi c'est important » (05/10/2026, point 4) : l'ancien préfixe « Hypothèse : » était apposé sur TOUS les
        # items (formule creuse : « met en lumière les controverses… »). Désormais : étayé par la source -> conservé
        # tel quel ; sinon SUPPRIMÉ (null) — l'interface n'affiche rien plutôt qu'un remplissage. Les conséquences,
        # elles, restent des hypothèses (cahier §14) et gardent leur préfixe ci-dessous.
        pi = ev.get("pourquoi_important")
        if pi and (_est_creux(pi) or overlap_ratio(pi, source_text) < PI_MIN_OVERLAP):
            all_removed.append(f"[pourquoi_important non étayé] {pi}")
            ev["pourquoi_important"] = None
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


# Ancrage marché (05/10/2026, point 2 de ANALYSE_RUN_2026-10-05.md) : le DAX et l'Euro Stoxx étaient « expliqués » par
# « le budget 2027 prévoit des garanties pour les réacteurs nucléaires » — un article France sans rapport avec un
# indice, mais dont les mots se retrouvaient dans le lot d'articles économie (recouvrement global >= 50 %).
# Désormais l'explication doit être étayée par UN SEUL article qui (a) parle explicitement de ce marché ou de la
# Bourse en général et (b) contient l'essentiel des mots de l'explication.
_ALIAS_MARCHE = {
    "cac 40": ["cac 40", "cac40", "cac", "bourse de paris", "place parisienne"],
    "s&p 500": ["s&p 500", "s&p500", "wall street", "bourse de new york", "bourses américaines"],
    "nasdaq": ["nasdaq", "wall street", "technologiques", "valeurs technologiques", "bourse de new york"],
    "dax": ["dax", "francfort", "bourse allemande", "bourses européennes", "bourse européenne", "euro stoxx"],
    "euro stoxx 50": ["euro stoxx", "stoxx", "bourses européennes", "bourse européenne", "dax", "cac 40"],
    "pétrole (brent)": ["brent", "baril", "pétrole", "opep", "opep+", "cours du brut", "brut"],
    "or": ["once d'or", "cours de l'or", "l'or ", "métal jaune", "valeur refuge", "valeurs refuges"],
}
_GENERIQUE_MARCHE = ["bourse", "bourses", "séance", "séances", "wall street", "investisseurs", "indice boursier",
                     "indices boursiers", "boursier", "boursiers", "cotation", "cotations", "marchés actions",
                     "marchés financiers", "marché des actions"]


def _article_ancre(article_text: str, nom_mouvement: str) -> bool:
    low = f" {_fold(article_text)} "
    alias = [_fold(a) for a in _ALIAS_MARCHE.get(str(nom_mouvement).lower(), [str(nom_mouvement).lower()])]
    gen = [_fold(g) for g in _GENERIQUE_MARCHE]
    return any(a in low for a in alias + gen)


def explication_etayee(expl: str, nom_mouvement: str, articles: list[dict]) -> bool:
    """Vrai si au moins un article économique (a) mentionne ce marché / la Bourse et (b) recouvre l'explication."""
    for a in articles or []:
        txt = f"{a.get('titre', '')} {a.get('resume', '')}"
        if _article_ancre(txt, nom_mouvement) and overlap_ratio(expl, txt) >= EXPLICATION_MIN_OVERLAP:
            return True
    return False


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
        if expl and not explication_etayee(expl, q["name"], analysed.get("actualite_economie") or []):
            expl = None
        gardees += 1 if expl else 0
        mouvements.append({"nom": q["name"], "variation_pct": q["variation_pct"], "explication": expl})
    out["mouvements_notables"] = mouvements
    resume, _ = clean_text(out.get("resume_court"), eco_text, source_numbers(eco_text))
    if mouvements and gardees == 0:
        resume = RESUME_MARCHES_SANS_CAUSE
    out["resume_court"] = resume or ""
    return out
