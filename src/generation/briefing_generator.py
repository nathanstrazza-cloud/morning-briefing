"""Étape GÉNÉRATION : transforme les événements analysés (scorés, dédupliqués, vérifiés)
en un objet Briefing prêt à être stocké et affiché.

Deux modes :
- Mode normal : un LLM rédige la synthèse en respectant le style du cahier des charges (§14)
  et structure la réponse en JSON strict (schéma ci-dessous), à partir UNIQUEMENT des données
  collectées (aucune information externe n'est autorisée -> consigne explicite dans le prompt).
- Mode fallback (`fallback_briefing`) : si le LLM est indisponible/échoue, on construit un
  briefing minimal directement à partir des données structurées, sans texte rédigé de
  synthèse. Toujours factuel, jamais inventé (cf. cahier §21).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from ..analyse import verification
from .llm_provider import LLMProvider

logger = logging.getLogger("morning_briefing.generation")

SCHEMA_ATTENDU = """{
  "actualite": {
    "france": [{"titre": str, "resume": str, "pourquoi_important": str, "consequences": str|null, "statut": str, "sources": [str]}],
    "monde": [ ... même structure ... ]
  },
  "marches": {
    "resume_court": str,
    "mouvements_notables": [{"nom": str, "variation_pct": float, "explication": str|null}]
  },
  "sport": {
    "football": [str],
    "basketball": [str],
    "natation": [str]|null,
    "autres": [str]|null
  },
  "science": {
    "mode": "decouverte" | "approfondi",
    "titre": str,
    "contenu_markdown": str
  },
  "citation": {"texte": str, "auteur": str},
  "meta": {"resume_1_phrase": str}
}"""

SYSTEM_PROMPT = """Tu es le rédacteur d'un briefing matinal personnel en français.

RÈGLES ABSOLUES (à respecter strictement) :
1. Utilise UNIQUEMENT les informations fournies dans les données ci-dessous. N'invente jamais
   un fait, un chiffre, une citation ou une explication que tu ne peux pas justifier avec les
   données fournies. Si tu ne sais pas expliquer pourquoi un marché a bougé à partir des
   données fournies, mets "explication": null plutôt que d'inventer une cause.
2. Style : clair, concis pour l'actualité, factuel, sans sensationnalisme, sans opinion
   politique, sans exagération, en français.
3. Pour chaque actualité, réponds implicitement à Quoi/Où/Quand/Pourquoi important, et pour
   les sujets complexes ajoute les conséquences possibles SANS les présenter comme certaines.
4. Respecte le statut de vérification fourni pour chaque événement : si "information_rapportee",
   commence la phrase par "Selon [source], ...". Si "fait_confirme", formule-le normalement.
5. Ne remplis pas artificiellement une section : si peu d'événements sont réellement
   importants, n'en retiens que peu.
6. Section science : si "mode_science" fourni est "decouverte", rédige un article court sur la
   découverte majeure fournie. Si "approfondi", rédige un article pédagogique approfondi
   (~10 minutes de lecture) sur le sujet fourni, structuré en : introduction, pourquoi c'est
   important, explication du phénomène, mécanismes, données scientifiques, ce qui est su, ce
   qui reste incertain, limites/controverses, conclusion. Ton d'une bonne revue de
   vulgarisation scientifique, précis, sans déformer les connaissances.
7. Citation du jour : uniquement si tu es certain de l'authenticité de l'attribution. Sinon,
   renvoie "citation": null.
8. Réponds STRICTEMENT en JSON valide conforme au schéma donné, sans texte avant/après, sans
   balises markdown autour du JSON.

SCHÉMA JSON ATTENDU :
""" + SCHEMA_ATTENDU


def _build_user_prompt(analysed: dict, science_topic: dict, is_monday: bool) -> str:
    payload = {
        "jour_lundi_couvre_weekend": is_monday,
        "actualite_france": analysed["actualite_france"],
        "actualite_monde": analysed["actualite_monde"],
        "marches": analysed["marches_data"],
        "sport": analysed["sport_events"],
        "science_mode": science_topic["mode"],
        "science_source": science_topic["contenu_source"],
    }
    return (
        "Voici les données collectées et analysées pour le briefing de ce matin.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    )


def generate(
    provider: LLMProvider | None,
    analysed: dict,
    science_topic: dict,
    weather_summary: dict | None,
    is_monday: bool,
) -> dict:
    """Retourne l'objet Briefing complet (dict), prêt pour le stockage.

    `analysed` doit contenir : actualite_france, actualite_monde, marches_data, sport_events
    (toutes des listes/dicts déjà scorés+filtrés+vérifiés en amont, cf. main.py).
    """
    if provider is None:
        logger.warning("Aucun LLM disponible -> génération en mode fallback (sans synthèse rédigée)")
        return fallback_briefing(analysed, science_topic, weather_summary, is_monday)

    try:
        user_prompt = _build_user_prompt(analysed, science_topic, is_monday)
        raw = provider.complete(SYSTEM_PROMPT, user_prompt)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
        body = json.loads(cleaned)
        body["meteo"] = weather_summary
        body["_genere_par_llm"] = True
        body["_provider"] = provider.name
        return body
    except Exception as exc:  # noqa: BLE001
        logger.error("Échec de la génération LLM (%s) -> repli sur fallback: %s", provider.name, exc)
        return fallback_briefing(analysed, science_topic, weather_summary, is_monday)


def fallback_briefing(analysed: dict, science_topic: dict, weather_summary: dict | None, is_monday: bool) -> dict:
    """Briefing minimal sans rédaction LLM : liste factuelle brute des événements retenus.
    Toujours disponible, ne dépend d'aucune clé API (cf. cahier §21 robustesse)."""

    def _format_event(e: dict) -> dict:
        prefix = verification.format_prefix(e)
        return {
            "titre": prefix + e["titre"],
            "resume": e.get("resume", ""),
            "pourquoi_important": None,
            "consequences": None,
            "statut": e["statut_verification"],
            "sources": [s["nom"] for s in e.get("sources", [])],
        }

    return {
        "actualite": {
            "france": [_format_event(e) for e in analysed["actualite_france"]],
            "monde": [_format_event(e) for e in analysed["actualite_monde"]],
        },
        "marches": {
            "resume_court": "Synthèse rédigée indisponible (LLM hors service) — voir chiffres bruts.",
            "mouvements_notables": [
                {"nom": q["name"], "variation_pct": q["variation_pct"], "explication": None}
                for q in analysed["marches_data"].get("mouvements_significatifs", [])
            ],
        },
        "sport": {
            "football": [e["titre"] for e in analysed["sport_events"].get("football", [])],
            "basketball": [e["titre"] for e in analysed["sport_events"].get("basketball", [])],
            "natation": [e["titre"] for e in analysed["sport_events"].get("natation", [])] or None,
            "autres": [e["titre"] for e in analysed["sport_events"].get("autres", [])] or None,
        },
        "science": {
            "mode": science_topic["mode"],
            "titre": science_topic["contenu_source"].get("titre", "Sujet scientifique"),
            "contenu_markdown": (
                "Synthèse rédigée indisponible pour le moment (LLM hors service). "
                "Article source : " + science_topic["contenu_source"].get("url", "")
            ),
        },
        "citation": None,
        "meteo": weather_summary,
        "meta": {"resume_1_phrase": "Briefing minimal généré sans synthèse LLM."},
        "_genere_par_llm": False,
        "_provider": None,
    }


def select_science_topic(analysed_sciences: list[dict]) -> dict:
    """Choisit le mode science (§7) : découverte majeure si un événement scoré haut existe
    dans la catégorie sciences, sinon mode approfondi avec le meilleur candidat disponible."""
    if analysed_sciences and analysed_sciences[0]["score"] >= 8:
        top = analysed_sciences[0]
        return {
            "mode": "decouverte",
            "contenu_source": {
                "titre": top["titre"],
                "resume": top.get("resume", ""),
                "url": top.get("url_principale", ""),
                "sources": [s["nom"] for s in top.get("sources", [])],
            },
        }

    if analysed_sciences:
        top = analysed_sciences[0]
        return {
            "mode": "approfondi",
            "contenu_source": {
                "titre": top["titre"],
                "resume": top.get("resume", ""),
                "url": top.get("url_principale", ""),
                "sources": [s["nom"] for s in top.get("sources", [])],
            },
        }

    return {
        "mode": "approfondi",
        "contenu_source": {
            "titre": "Aucun sujet scientifique récent disponible",
            "resume": "",
            "url": "",
            "sources": [],
        },
    }
