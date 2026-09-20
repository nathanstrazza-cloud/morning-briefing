"""Étape STOCKAGE (cf. cahier §16-17) : sauvegarde du briefing sous forme JSON structurée,
conserve l'historique, ne supprime jamais d'anciens briefings.

Fichiers produits dans data/briefings/ :
- YYYY-MM-DD.json     : le briefing complet de ce jour (permanent, jamais écrasé)
- latest.json         : copie du dernier briefing réussi (lu par la page d'accueil)
- index.json          : liste de toutes les dates disponibles, pour l'historique (§16)
- status.json         : statut du dernier run (succès/échec) affiché par le frontend (§21)
- status_history.json : historique des statuts, un par date (2026-09-19, cf. onglet "Erreurs"
                         du site) -- status.json seul ne montre que le run le plus récent, ce
                         qui ne permet pas de voir "y a-t-il eu des erreurs récemment ?" sans
                         rouvrir les logs GitHub Actions un par un.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("morning_briefing.stockage")

# Les données vivent sous docs/ pour que GitHub Pages (mode "Deploy from branch -> /docs")
# puisse servir le frontend ET les données JSON ensemble, gratuitement, sans workflow de
# déploiement supplémentaire (cf. README §6).
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "docs" / "data" / "briefings"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def day_briefing_exists(date_iso: str) -> bool:
    """True si un briefing a déjà été sauvegardé avec succès pour cette date.

    Utilisé par main.py comme garde d'idempotence : évite de relancer tout le pipeline
    (et de refaire un appel LLM) si le workflow GitHub Actions se déclenche deux fois le
    même jour (double cron été/hiver, cf. briefing.yml) ou est retardé puis relancé.
    """
    return (DATA_DIR / f"{date_iso}.json").exists()


def save_briefing(
    briefing: dict, date_iso: str, last_update_iso: str, rss_diagnostics: list[dict] | None = None
) -> None:
    """Sauvegarde le briefing du jour + met à jour latest.json et index.json.
    N'écrase JAMAIS un fichier de date existant avec un contenu vide (sécurité supplémentaire)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    enveloppe = {
        "date": date_iso,
        "derniere_mise_a_jour": last_update_iso,
        "briefing": briefing,
    }

    day_path = DATA_DIR / f"{date_iso}.json"
    _write_json(day_path, enveloppe)
    _write_json(DATA_DIR / "latest.json", enveloppe)

    _update_index(date_iso)
    # NB (corrigé le 2026-09-19) : jusqu'ici status.json indiquait toujours succes=True dès
    # que le pipeline se terminait, même quand la synthèse LLM avait échoué et qu'on était
    # tombé en mode fallback (cf. briefing["_genere_par_llm"]) -- l'échec LLM était alors
    # invisible sans rouvrir les logs du run. status.json distingue maintenant les deux :
    # le run reste "succes" (cf. cahier §21 : le fallback est un succès du point de vue
    # robustesse, jamais un crash), mais `synthese_llm`/`erreur_llm` exposent séparément si
    # la rédaction LLM elle-même a fonctionné.
    _write_status(
        succes=True,
        date_iso=date_iso,
        last_update_iso=last_update_iso,
        synthese_llm=briefing.get("_genere_par_llm"),
        erreur_llm=briefing.get("_erreur_llm"),
        rss_diagnostics=rss_diagnostics,
    )
    logger.info("Briefing sauvegardé: %s", day_path)


def _update_index(date_iso: str) -> None:
    index_path = DATA_DIR / "index.json"
    index = _read_json(index_path) or {"dates": []}
    if date_iso not in index["dates"]:
        index["dates"].append(date_iso)
        index["dates"].sort(reverse=True)
    _write_json(index_path, index)


def _write_status(
    succes: bool,
    date_iso: str,
    last_update_iso: str,
    erreur: str | None = None,
    synthese_llm: bool | None = None,
    erreur_llm: str | None = None,
    rss_diagnostics: list[dict] | None = None,
) -> None:
    # cf. collecte/rss_sources.py + collector.py : un résumé compact suffit ici (le détail
    # complet par flux est déjà dans les logs GitHub Actions) -- on garde surtout la liste
    # des sources en échec, pour que l'onglet "Erreurs" du site les affiche sans qu'il soit
    # nécessaire de rouvrir les logs bruts (cf. cahier §22).
    sources_en_erreur = None
    if rss_diagnostics is not None:
        sources_en_erreur = [
            {"source": d["source"], "categorie": d["categorie"], "detail": d.get("detail")}
            for d in rss_diagnostics
            if d.get("statut") == "erreur"
        ]

    entry = {
        "derniere_execution": last_update_iso,
        "date_visee": date_iso,
        "succes": succes,
        "erreur": erreur,
        # cf. save_briefing : distinct de "succes" -- un run peut réussir globalement
        # (fallback) tout en ayant une synthèse LLM en échec.
        "synthese_llm": synthese_llm,
        "erreur_llm": erreur_llm,
        # cf. ci-dessus : liste des flux RSS en échec pour ce run (source, catégorie, cause).
        # None si le pipeline n'a pas atteint l'étape de collecte (échec plus précoce).
        "sources_rss_en_erreur": sources_en_erreur,
    }
    _write_json(DATA_DIR / "status.json", entry)
    _append_status_history(entry)


# Nombre d'entrées conservées dans status_history.json -- cf. onglet "Erreurs" du site.
# ~120 jours ouvrés = plusieurs mois d'historique, largement suffisant pour repérer une
# panne récurrente sans faire grossir le fichier indéfiniment (cf. cahier §16 : ne pas
# supprimer les anciens BRIEFINGS -- cette limite ne concerne que le journal de statuts,
# pas les briefings eux-mêmes qui restent, eux, conservés indéfiniment dans YYYY-MM-DD.json).
MAX_STATUS_HISTORY = 120


def _append_status_history(entry: dict) -> None:
    """Ajoute `entry` à status_history.json (une entrée par date_visee -- un rerun le même
    jour remplace l'entrée existante plutôt que d'en ajouter une seconde, cf.
    day_briefing_exists qui évite déjà normalement les reruns). Liste triée du plus récent
    au plus ancien, plafonnée à MAX_STATUS_HISTORY entrées."""
    path = DATA_DIR / "status_history.json"
    data = _read_json(path) or {"entries": []}
    entries = [e for e in data.get("entries", []) if e.get("date_visee") != entry["date_visee"]]
    entries.append(entry)
    entries.sort(key=lambda e: (e.get("date_visee") or "", e.get("derniere_execution") or ""), reverse=True)
    _write_json(path, {"entries": entries[:MAX_STATUS_HISTORY]})


def record_failure(
    date_iso: str, last_update_iso: str, erreur: str, rss_diagnostics: list[dict] | None = None
) -> None:
    """Cf. cahier §21 : si tout échoue, on NE TOUCHE PAS à latest.json — le dernier
    briefing valide reste affiché. On journalise seulement l'échec dans status.json."""
    logger.error("Échec du run pour %s: %s — dernier briefing valide conservé.", date_iso, erreur)
    _write_status(
        succes=False, date_iso=date_iso, last_update_iso=last_update_iso, erreur=erreur,
        rss_diagnostics=rss_diagnostics,
    )


def get_last_successful_datetime() -> datetime | None:
    """Retourne la date/heure ('derniere_mise_a_jour') du dernier briefing sauvegardé avec
    succès, en lisant latest.json. Retourne None si aucun briefing n'existe encore ou si le
    fichier est illisible (l'appelant doit alors retomber sur un comportement par défaut,
    cf. utils.compute_window). Utilisé pour calculer dynamiquement la fenêtre de recherche
    des jours normaux (cf. cahier §3 : "depuis le briefing précédent")."""
    try:
        latest = _read_json(DATA_DIR / "latest.json")
        if not latest or "derniere_mise_a_jour" not in latest:
            return None
        return datetime.fromisoformat(latest["derniere_mise_a_jour"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("Impossible de lire la date du dernier briefing réussi: %s", exc)
        return None
