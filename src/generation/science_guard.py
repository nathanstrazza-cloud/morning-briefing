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
    liens = [l for l in (contenu_source.get("liens_sources") or []) if l.get("nom")]
    lignes = ["## Sources"]
    if liens:
        for l in liens:
            lignes.append(f"- {l['nom']}" + (f" — {l['url']}" if l.get("url") else ""))
    else:
        nom = ", ".join(contenu_source.get("sources") or []) or "source indiquée"
        url = contenu_source.get("url") or ""
        lignes.append(f"- Article source : {contenu_source.get('titre', '')} ({nom})" + (f" — {url}" if url else ""))
    lignes.append("- Les chiffres et affirmations de cet article se limitent à ceux de ces sources ; "
                  "les détails de l'étude sont à consulter sur les liens ci-dessus.")
    return "\n".join(lignes)


# --- 06/10/2026 (ANALYSE_RUN_2026-10-06.md, point 1) -------------------------------------------------
# Constat : l'article du Nobel contenait (a) des identifiants techniques absents de la source (ArchT, ChR2, AAV),
# (b) des phrases qui parlent du « résumé » (fuite interne), (c) un « : » orphelin après suppression de puces,
# (d) une section « Données » vide ou ne parlant que du résumé. Fonctions pures, sans réseau.
_META_RE = re.compile(r"\b(le|ce|du|au|dans le|dans ce|ce que dit le) r[ée]sum[ée]\b|\br[ée]sum[ée] (disponible|fourni|indique|ne pr[ée]cise)|"
                      r"\bnous ne disposons (pas|que)\b|\bsource fournie\b|\bl'extrait (fourni|disponible)\b", re.I)
_ID_MIXTE = re.compile(r"\b(?=[A-Za-z0-9-]*\d)(?=[A-Za-z0-9-]*[A-Za-z])[A-Za-z][A-Za-z0-9-]{2,}\b|\b[a-z]{1,3}[A-Z][A-Za-z0-9]*\b|\b[A-Z][a-z]+[A-Z][A-Za-z0-9]*\b")
_ACRONYME = re.compile(r"\b[A-Z]{3,6}\b")
# Sigles de culture générale tolérés même absents de la source (manuel) ; tout autre sigle doit figurer dans la source.
_SIGLES_TOLERES = {"ADN", "ARN", "ATP", "IRM", "EEG", "ECG", "GPS", "USA", "ONU", "OMS", "UE", "CNRS", "NASA", "ESA", "CERN",
                   "LED", "LASER", "VIH", "SIDA", "COVID", "CO2", "NASA", "INSERM", "AVC", "TDAH", "PIB", "GIEC", "OTAN"}
_NOM_MOT = re.compile(r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ'’-]{2,}")
_FALLBACK_DONNEES = ("Les données chiffrées détaillées ne sont pas reprises ici : elles sont à consulter "
                     "dans l'article source indiqué ci-dessous.")


def _fold(txt: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", txt or "").encode("ascii", "ignore").decode("ascii").lower()


def source_full_text(contenu_source: dict) -> str:
    """Titre + résumé + tous les textes des sources fusionnées : l'ensemble de ce que le rédacteur a réellement reçu."""
    parts = [contenu_source.get("titre", ""), contenu_source.get("resume", "")]
    for t in contenu_source.get("textes_sources") or []:
        parts += [t.get("titre", ""), t.get("resume", "")]
    return " ".join(str(p) for p in parts if p)


def _map_sentences(text: str, keep) -> tuple[str, list[str]]:
    """Applique `keep(phrase) -> bool` à chaque phrase des lignes de texte (titres inchangés). Retourne (texte, retirées)."""
    removed: list[str] = []
    out: list[str] = []
    for line in text.splitlines():
        if not line.strip() or _HEADING_RE.match(line.strip()):
            out.append(line)
            continue
        prefix = re.match(r"^\s*([-*•]|\d+[.)])?\s*", line).group(0)
        body = line[len(prefix):]
        kept = []
        for sent in _SENT_SPLIT.split(body):
            if keep(sent):
                kept.append(sent)
            else:
                removed.append(sent.strip())
        if kept:
            out.append(prefix + " ".join(kept))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip(), removed


_ABSOLU_RE = re.compile(r"\bnon[- ]invasi\w+|\bsans (aucun |le moindre )?(risque|effet secondaire|danger)s?\b|"
                        r"\b(100 ?%|totalement|parfaitement) (sûr|sans danger|inoffensif)\b", re.I)
_STUB_RE = re.compile(r"^\W*(par exemple|notamment|comme suit|en voici|voici)\W*$", re.I)


def remove_meta_leaks(text: str) -> tuple[str, list[str]]:
    """Retire les phrases qui parlent du « résumé » / de la source fournie (fuite de la mécanique interne), les
    affirmations absolues non sourcées (« non invasif », « sans risque ») et les amorces vides (« Par exemple. »)."""
    return _map_sentences(text, lambda sent: not (_META_RE.search(sent) or _ABSOLU_RE.search(sent) or _STUB_RE.match(sent.strip())))


def unsupported_terms(sentence: str, source_text: str) -> list[str]:
    """Identifiants techniques (ChR2, ArchT, Cas9…), sigles hors liste tolérée et « Prénom Nom » absents de la source."""
    src = _fold(source_text)
    src_tokens = set(re.findall(r"[a-z0-9]+", src))
    bad: list[str] = []
    for m in _ID_MIXTE.finditer(sentence):
        mot = m.group()
        if _fold(mot) not in src and _fold(mot).strip("-") not in src_tokens and mot.upper() not in _SIGLES_TOLERES:
            bad.append(mot)
    for m in _ACRONYME.finditer(sentence):
        mot = m.group()
        if mot not in _SIGLES_TOLERES and _fold(mot) not in src_tokens:
            bad.append(mot)
    mots = list(re.finditer(r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ'’-]{2,}(?![\w])|\S+", sentence))
    for i in range(1, len(mots) - 1):          # le 1er mot de la phrase ne prouve rien (majuscule de début)
        a, b = mots[i].group(), mots[i + 1].group()
        if _NOM_MOT.fullmatch(a) and _NOM_MOT.fullmatch(b):
            if not (_fold(a).strip("'’-") in src_tokens and _fold(b).strip("'’-") in src_tokens):
                bad.append(f"{a} {b}")
    return bad


def remove_unsupported_terms(text: str, source_text: str) -> tuple[str, list[str]]:
    return _map_sentences(text, lambda sent: not unsupported_terms(sent, source_text))


def fix_orphan_colons(text: str) -> str:
    """« …comme des « interrupteurs » : » suivi d'un paragraphe (puces retirées) -> le « : » devient « . »."""
    lignes = text.splitlines()
    for i, l in enumerate(lignes):
        if l.rstrip().endswith(":") and not _HEADING_RE.match(l.strip()):
            suivante = next((x for x in lignes[i + 1:] if x.strip()), "")
            if not suivante or _HEADING_RE.match(suivante.strip()) or not re.match(r"^\s*([-*•]|\d+[.)])\s", suivante):
                lignes[i] = l.rstrip()[:-1].rstrip() + "."
    return "\n".join(lignes)


def ensure_sections_not_empty(text: str) -> str:
    """Section « Données » vidée -> phrase standard ; toute autre section vide -> supprimée (jamais un titre sans texte)."""
    lignes = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lignes):
        l = lignes[i]
        m = _HEADING_RE.match(l.strip())
        if m:
            j = i + 1
            corps = []
            while j < len(lignes) and not _HEADING_RE.match(lignes[j].strip()):
                corps.append(lignes[j])
                j += 1
            if not any(c.strip() for c in corps):
                if re.search(r"donn[ée]es", m.group(2), re.I):
                    out += [l, "", _FALLBACK_DONNEES, ""]
                i = j
                continue
        out.append(l)
        i += 1
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


# --- 08/10/2026 (ANALYSE_RUN_2026-10-08.md, point 1) -----------------------------------------------------------
# Constat : à partir d'UN résumé RSS, le rédacteur a écrit « aucun effet indésirable grave », « maintenues plusieurs
# mois », « dix patients dans trois pays »… Les nombres et les noms propres étaient contrôlés, pas ces AFFIRMATIONS
# sur l'étude. Règle : une phrase qui AFFIRME un résultat d'essai (sécurité, durée de suivi, participants, phase,
# placebo…) est retirée si le thème n'apparaît nulle part dans les textes sources. Les phrases prudentes (« reste à
# démontrer », « pourrait ») ne sont pas touchées : elles n'affirment rien.
_THEMES_ETUDE = {
    "sécurité/effets": re.compile(r"effets? (indésirables?|secondaires?)|toxicit|tol[ée]rance|sécurité|innocuit", re.I),
    "durée/suivi": re.compile(r"\bsuivi\b|durabl|maintenu|persist|à long terme|pendant (plusieurs|des) (mois|années|ans)", re.I),
    "participants": re.compile(r"\b(participants?|volontaires|patients?|sujets)\b", re.I),
    "essai": re.compile(r"essai (clinique|randomis|de phase)|randomis|placebo|double aveugle|phase (I|II|III|1|2|3)\b", re.I),
    "pays/centres": re.compile(r"\b(centres?|hôpitaux|hopitaux|sites?) (en|aux|au|dans)\b|\b(en|aux|au) (France|États-Unis|Royaume-Uni)\b.*\b(et|,)\b", re.I),
}
_PRUDENT_RE = re.compile(r"pas encore|reste à|restent? à|n'est pas|ne sont pas|ne (permet|permettent) pas|incertain|aucune donnée|"
                         r"non (démontr|établi|confirm)|à confirmer|à vérifier|pourrai(t|ent)|pourrait|peut-être|\bsi\b|"
                         r"question|inconnu|manque|limit", re.I)


def remove_unsourced_study_claims(text: str, source_text: str) -> tuple[str, list[str]]:
    src = source_text or ""
    absents = {nom: rx for nom, rx in _THEMES_ETUDE.items() if not rx.search(src)}

    def keep(sent: str) -> bool:
        if _PRUDENT_RE.search(sent):
            return True
        return not any(rx.search(sent) for rx in absents.values())
    return _map_sentences(text, keep)


def guard_science_article(contenu: str, contenu_source: dict) -> tuple[str, list[str]]:
    """Pipeline complet. `contenu` = moitiés A+B concaténées. Retourne (texte final, phrases retirées)."""
    full = source_full_text(contenu_source)
    allowed = source_numbers(full)
    t = strip_markers(contenu)
    t = normalize_headings(t)
    t = remove_llm_sources(t)
    t, r_meta = remove_meta_leaks(t)
    t, r_num = remove_unsupported_numbers(t, allowed)
    t, r_terms = remove_unsupported_terms(t, full)
    t, r_claims = remove_unsourced_study_claims(t, full)
    t = fix_orphan_colons(t)
    t = ensure_sections_not_empty(t)
    removed = ([f"[fuite interne] {x}" for x in r_meta] + r_num + [f"[terme non sourcé] {x}" for x in r_terms]
               + [f"[affirmation d'étude non sourcée] {x}" for x in r_claims])
    return (t + "\n\n" + build_sources_section(contenu_source)).strip(), removed
