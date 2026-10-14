"""Sujets pédagogiques du mode science « approfondi » (cahier §7, mode 2) — 11/10/2026.

Pourquoi : jusqu'ici, sans découverte qualifiée, l'article « approfondi » était écrit à partir d'UN résumé RSS de
2 lignes (cas du 11/10 : interview d'un neuroscientifique, article de 1 400 mots dont les analyses étaient attribuées
sans source). Désormais : un sujet pédagogique tiré de `config/science_sujets.json`, avec pour TEXTE SOURCE un extrait
réel de Wikipédia FR (API MediaWiki, gratuite, sans clé) récupéré à chaque run. Le rédacteur ne reçoit que ce texte ;
`science_guard` vérifie nombres/noms/termes contre lui ; la section Sources (construite par le code) cite l'article.
Wikipédia n'est PAS une source primaire : le texte final le dit. Si rien n'est récupérable -> mode « indisponible »
(note honnête, jamais d'article inventé).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests

logger = logging.getLogger("morning_briefing.collecte.encyclopedie")

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "science_sujets.json"
API_URL = "https://fr.wikipedia.org/w/api.php"
USER_AGENT = "morning-briefing/1.0 (https://github.com/nathanstrazza-cloud/morning-briefing)"
MAX_CARACTERES = 6000
MIN_CARACTERES = 2500
HISTORIQUE_JOURS = 45
MAX_ESSAIS = 6
_FIN_ARTICLE = re.compile(r"\n+\s*(Voir aussi|Notes et références|Liens externes|Bibliographie|Articles connexes|Annexes?)\s*\n", re.I)


def charger_sujets(path: Path = CONFIG_PATH) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("Sujets pédagogiques illisibles (%s)", exc)
        return []
    return [s for s in data.get("sujets", []) if s.get("id") and s.get("wiki")]


def nettoyer_extrait(texte: str, max_chars: int = MAX_CARACTERES) -> str:
    """Retire les sections de fin et coupe proprement (fin de paragraphe) à `max_chars`."""
    t = (texte or "").replace("\r", "")
    m = _FIN_ARTICLE.search(t)
    if m:
        t = t[:m.start()]
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    if len(t) <= max_chars:
        return t
    coupe = t[:max_chars]
    i = coupe.rfind("\n\n")
    if i < max_chars // 2:
        i = max(coupe.rfind(". "), coupe.rfind(".\n")) + 1
    return coupe[:i].strip() if i > 0 else coupe.strip()


def recuperer_extrait(titre_wiki: str, timeout: int = 15) -> dict | None:
    """{'titre','url','texte'} ou None (page absente, réseau, texte trop court)."""
    params = {"action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "plain",
              "redirects": 1, "format": "json", "formatversion": 2, "titles": titre_wiki}
    try:
        r = requests.get(API_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        r.raise_for_status()
        pages = (r.json().get("query") or {}).get("pages") or []
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Wikipédia indisponible pour « %s » : %s", titre_wiki, exc)
        return None
    if not pages or pages[0].get("missing") or not pages[0].get("extract"):
        logger.warning("Wikipédia : article « %s » introuvable", titre_wiki)
        return None
    titre = pages[0].get("title", titre_wiki)
    texte = nettoyer_extrait(pages[0]["extract"])
    if len(texte) < MIN_CARACTERES:
        logger.warning("Wikipédia : « %s » trop court (%d caractères)", titre, len(texte))
        return None
    return {"titre": titre, "url": "https://fr.wikipedia.org/wiki/" + quote(titre.replace(" ", "_")), "texte": texte}


def sujets_deja_utilises(dossiers: list[Path] | None = None, n: int = HISTORIQUE_JOURS) -> set[str]:
    """Identifiants `science.sujet_id` des `n` derniers briefings (rotation sans répétition)."""
    if dossiers is None:
        from src.stockage import storage
        dossiers = [storage.resolve_data_dir(), storage.PROD_DATA_DIR]
    fichiers: dict[str, Path] = {}
    # + sous-dossier archives/ (rotation des briefings, 14/10/2026) : la mémoire des sujets dépasse les 30 publiés.
    for d in [x for base in dossiers for x in (Path(base), Path(base) / "archives")]:
        for f in Path(d).glob("20??-??-??.json"):
            fichiers.setdefault(f.name, f)
    ids: set[str] = set()
    for nom in sorted(fichiers, reverse=True)[:n]:
        try:
            sid = (json.loads(fichiers[nom].read_text(encoding="utf-8")).get("briefing", {}).get("science") or {}).get("sujet_id")
        except (OSError, ValueError):
            continue
        if sid:
            ids.add(str(sid))
    return ids


def ordre_du_jour(sujets: list[dict], jour: date, utilises: set[str]) -> list[dict]:
    """Rotation déterministe par date ; les sujets récents passent en dernier recours."""
    if not sujets:
        return []
    k = jour.toordinal() % len(sujets)
    tournes = sujets[k:] + sujets[:k]
    return [s for s in tournes if s["id"] not in utilises] + [s for s in tournes if s["id"] in utilises]


def choisir_sujet_pedagogique(jour: date | None = None, sujets: list[dict] | None = None,
                              utilises: set[str] | None = None, fetch=recuperer_extrait) -> dict | None:
    """Sujet « approfondi » prêt pour le rédacteur (format `science_topic`), ou None."""
    jour = jour or date.today()
    sujets = charger_sujets() if sujets is None else sujets
    utilises = sujets_deja_utilises() if utilises is None else utilises
    for s in ordre_du_jour(sujets, jour, utilises)[:MAX_ESSAIS]:
        ex = fetch(s["wiki"])
        if not ex:
            continue
        logger.info("Science : sujet pédagogique « %s » (%d caractères de source)", s["titre"], len(ex["texte"]))
        return {
            "mode": "approfondi",
            "contenu_source": {
                "titre": s["titre"], "resume": ex["texte"][:600], "url": ex["url"],
                "origine": "encyclopedie", "sujet_id": s["id"], "matiere": "suffisante",
                "sources": ["Wikipédia (fr)"],
                "liens_sources": [{"nom": f"Wikipédia (fr) — {ex['titre']}", "url": ex["url"]}],
                "textes_sources": [{"source": "Wikipédia (fr)", "titre": ex["titre"], "resume": ex["texte"]}],
            },
        }
    return None
