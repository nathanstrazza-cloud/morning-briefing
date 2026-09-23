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
from .llm_provider import LLMError, LLMProvider

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


# NB (corrigé le 2026-09-13, resserré le 2026-09-19) : garde-fou anti-413. Cf.
# rss_sources._clean_summary qui nettoie déjà les résumés à la collecte -- ceci est une
# DEUXIÈME barrière, indépendante de la source des données (cf. cahier §21 robustesse).
#
# Historique : la limite de 45 000 caractères posée le 13/09 n'a PAS empêché l'erreur 413
# de continuer à se produire (constaté dans les logs du 17/09 et vraisemblablement du 18/09,
# sans log committé ce jour-là). Un test avec une charge utile réaliste d'une journée normale
# (15 actus France + 15 Monde + sport + science) donne ~42-45 Ko, c'est-à-dire pile à
# l'ancienne limite : elle ne déclenchait donc quasiment jamais le rognage. Le vrai seuil
# accepté par Groq côté gratuit semble bien plus bas que la taille de contexte théorique du
# modèle (128k tokens) — probablement une limite de tokens/minute par organisation propre au
# tier gratuit (cf. Groq: "tokens per minute (TPM)" pouvant être aussi bas que quelques
# milliers selon le modèle). On ne connaissait pas la valeur exacte car `raise_for_status()`
# n'exposait jamais le corps de la réponse Groq (cf. llm_provider.LLMError, ajouté ce jour
# pour que la PROCHAINE erreur, s'il y en a une, indique enfin la vraie cause dans les logs
# et dans `_erreur_llm` au lieu de forcer une nouvelle devinette).
#
# En attendant d'avoir cette donnée réelle, on prend une marge large : 12 000 caractères
# (~3000 tokens), et on sérialise en JSON compact (sans indentation) qui réduit mécaniquement
# la taille de 20-30% par rapport à `indent=2` pour la même information, sans rien retirer.
# Cf. cahier §1 : mieux vaut une synthèse LLM fiable sur moins d'événements qu'une absence
# systématique de synthèse faute de budget de caractères correctement calibré.
MAX_PROMPT_CHARS = 12_000

# Cf. cahier §1/§21 : si même 12 000 caractères échouent (413/429), on retente UNE fois avec
# un budget très restreint plutôt que d'abandonner directement sur la synthèse rédigée --
# mieux vaut un briefing LLM sur les 5 informations les plus importantes qu'aucune synthèse
# rédigée du tout.
RETRY_PROMPT_CHARS = 4_000


def _build_user_prompt(analysed: dict, science_topic: dict, is_monday: bool, max_chars: int = MAX_PROMPT_CHARS) -> str:
    france = list(analysed["actualite_france"])
    monde = list(analysed["actualite_monde"])

    # Allégement : le LLM n'a besoin que des NOMS de sources pour respecter le schéma de
    # sortie ("sources": [str]) -- pas de leurs URLs, qui gonflent le payload sans utilité
    # pour la rédaction. On garde titre/resume/categorie/statut_verification tels quels.
    def _light_event(e: dict) -> dict:
        light = {k: v for k, v in e.items() if k != "sources"}
        light["sources"] = [s["nom"] if isinstance(s, dict) else s for s in e.get("sources", [])]
        return light

    france = [_light_event(e) for e in france]
    monde = [_light_event(e) for e in monde]

    # Allégement sport : le schéma de sortie n'attend qu'une liste de courtes phrases par
    # catégorie -- le LLM n'a besoin que du titre de chaque événement, pas du dict complet
    # (resume/sources/url/categorie/score) que produit le pipeline d'analyse.
    def _light_sport(sport_events: dict) -> dict:
        return {cat: [e["titre"] for e in evs] for cat, evs in sport_events.items()}

    def _payload(france_l, monde_l, sport_l, marches_l) -> dict:
        return {
            "jour_lundi_couvre_weekend": is_monday,
            "actualite_france": france_l,
            "actualite_monde": monde_l,
            "marches": marches_l,
            "sport": sport_l,
            "science_mode": science_topic["mode"],
            "science_source": science_topic["contenu_source"],
        }

    # JSON compact (pas d'indentation, séparateurs sans espace) : même information, 20-30%
    # de caractères en moins qu'avec indent=2 (cf. note ci-dessus). Le LLM n'a pas besoin
    # d'un JSON lisible par un humain pour le comprendre.
    def _serialize(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)

    sport = _light_sport(analysed["sport_events"])
    # cf. cahier §4 : actualité = priorité maximale. En cas de dépassement du budget, on
    # réduit d'abord le sport (moins prioritaire) avant de toucher à l'actualité, et jamais
    # les marchés (déjà réduits aux seuls mouvements significatifs en amont, cf. main.py).
    marches = analysed["marches_data"]
    serialized = _serialize(_payload(france, monde, sport, marches))

    trimmed_sport = False
    while len(serialized) > max_chars and any(sport.values()):
        # Retire un item de la catégorie sport la plus fournie, à tour de rôle.
        cat = max(sport, key=lambda c: len(sport[c]))
        if sport[cat]:
            sport[cat].pop()
        trimmed_sport = True
        serialized = _serialize(_payload(france, monde, sport, marches))

    # Plancher : ne jamais vider complètement l'actualité (priorité maximale, cf. cahier §4)
    # -- on retire en dernier recours, mais on garde toujours au moins 2 événements par zone
    # tant qu'il en reste, plutôt que de tout sacrifier pour gagner quelques centaines de
    # caractères. On alterne monde/france comme avant (listes triées par score décroissant).
    PLANCHER_ACTUALITE = 2
    trimmed_actualite = False
    while len(serialized) > max_chars and (
        len(france) > PLANCHER_ACTUALITE or len(monde) > PLANCHER_ACTUALITE
    ):
        if len(monde) > PLANCHER_ACTUALITE and (len(monde) >= len(france) or len(france) <= PLANCHER_ACTUALITE):
            monde.pop()
        elif len(france) > PLANCHER_ACTUALITE:
            france.pop()
        else:
            break
        trimmed_actualite = True
        serialized = _serialize(_payload(france, monde, sport, marches))

    if trimmed_sport or trimmed_actualite:
        logger.warning(
            "Prompt LLM trop volumineux (>%d caractères) -> sport réduit=%s, actualité réduite=%s "
            "(retenus après réduction : france=%d, monde=%d, sport=%d au total).",
            max_chars, trimmed_sport, trimmed_actualite, len(france), len(monde),
            sum(len(v) for v in sport.values()),
        )

    return "Voici les données collectées et analysées pour le briefing de ce matin.\n\n" + serialized


def generate(
    providers: list[LLMProvider],
    analysed: dict,
    science_topic: dict,
    weather_summary: dict | None,
    is_monday: bool,
) -> dict:
    """Retourne l'objet Briefing complet (dict), prêt pour le stockage.

    `analysed` doit contenir : actualite_france, actualite_monde, marches_data, sport_events
    (toutes des listes/dicts déjà scorés+filtrés+vérifiés en amont, cf. main.py).

    `providers` est une LISTE ordonnée (cf. llm_provider.get_providers()) : on essaie chaque
    provider dans l'ordre, et pour chacun deux budgets de prompt (cf. MAX_PROMPT_CHARS /
    RETRY_PROMPT_CHARS), avant de renoncer à la synthèse rédigée et de retomber sur
    fallback_briefing(). Ne renonce donc que si TOUS les providers configurés ont échoué.
    """
    if not providers:
        logger.warning("Aucun LLM disponible -> génération en mode fallback (sans synthèse rédigée)")
        return fallback_briefing(analysed, science_topic, weather_summary, is_monday, erreur_llm=None)

    def _try(provider: LLMProvider, max_chars: int) -> dict:
        user_prompt = _build_user_prompt(analysed, science_topic, is_monday, max_chars=max_chars)
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
        body["_erreur_llm"] = None
        return body

    dernier_exc: Exception | None = None
    dernier_provider_name: str | None = None
    # NB (2026-09-19) : pour CHAQUE provider disponible (préféré, puis repli(s) -- cf.
    # llm_provider.get_providers()), deux tentatives avec un budget de caractères décroissant
    # (cf. RETRY_PROMPT_CHARS). On ne bascule au provider suivant qu'après avoir épuisé les
    # deux tentatives du provider courant. Cf. cahier §1/§21 : mieux vaut une synthèse rédigée
    # via un second fournisseur gratuit (ex: Gemini) qu'aucune synthèse du tout parce que le
    # premier (ex: Groq) a atteint sa limite.
    for provider in providers:
        for tentative, max_chars in enumerate((MAX_PROMPT_CHARS, RETRY_PROMPT_CHARS), start=1):
            try:
                return _try(provider, max_chars)
            except Exception as exc:  # noqa: BLE001
                dernier_exc = exc
                dernier_provider_name = provider.name
                detail = getattr(exc, "body_excerpt", None)
                logger.error(
                    "Échec de la génération LLM (%s, tentative %d/2, budget=%d caractères): %s%s",
                    provider.name, tentative, max_chars, exc,
                    f" | corps de la réponse: {detail}" if detail else "",
                )
        logger.warning("Provider '%s' épuisé (2/2 tentatives échouées) -> passage au suivant s'il existe.", provider.name)

    erreur_resumee = f"{dernier_provider_name}: {dernier_exc}" if dernier_exc else None
    return fallback_briefing(analysed, science_topic, weather_summary, is_monday, erreur_llm=erreur_resumee)


def fallback_briefing(
    analysed: dict,
    science_topic: dict,
    weather_summary: dict | None,
    is_monday: bool,
    erreur_llm: str | None = None,
) -> dict:
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
        # NB (2026-09-19) : cause réelle de l'échec LLM (tronquée), pour diagnostic sans
        # devoir rouvrir les logs du run -- cf. storage.save_briefing qui la reprend aussi
        # dans status.json.
        "_erreur_llm": (erreur_llm[:500] if erreur_llm else None),
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
