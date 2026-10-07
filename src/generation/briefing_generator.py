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
import os
import re
import time
from datetime import datetime

from ..analyse import verification
from .llm_provider import LLMError, LLMProvider
from .anglais_guard import score_apprentissage
from . import sport_format

logger = logging.getLogger("morning_briefing.generation")

# NB (2026-09-27, scission bloc/science) : jusqu'ici un SEUL appel LLM générait tout le
# briefing (actu+marchés+sport+science+citation) en une seule réponse JSON -- cf.
# llm_provider.py pour le diagnostic complet (limite TPM du tier gratuit Groq trop basse pour
# tenir prompt+sortie combinés dans une seule fenêtre d'une minute, confirmée par les runs
# réels des 26 et 27/09). Scindé en DEUX appels indépendants, chacun avec son propre schéma,
# son propre system prompt et son propre budget de sortie :
#   - "bloc" (SCHEMA_BLOC/SYSTEM_PROMPT_BLOC) : actualité+marchés+sport+citation+meta --
#     sortie majoritairement composée de phrases courtes, budget réduit.
#   - "science" (SCHEMA_SCIENCE/SYSTEM_PROMPT_SCIENCE) : uniquement l'article scientifique,
#     de loin le plus gourmand en tokens de SORTIE (~10 min de lecture) -- budget dédié.
# Avantage secondaire (pas seulement le quota) : un échec sur l'un des deux appels ne fait
# plus perdre l'autre. Avant, un seul échec LLM faisait tomber TOUT le briefing en mode
# fallback (aucune section rédigée) ; maintenant le bloc actu/marchés/sport (priorité
# maximale, cf. cahier §4) peut rester rédigé même si l'article science échoue, et
# inversement -- dégradation partielle plutôt que totale, cf. cahier §21.
SCHEMA_BLOC = """{
  "actualite": {
    "france": [{"titre": str, "resume": str, "pourquoi_important": str, "consequences": str|null, "statut": str, "sources": [str]}],
    "monde": [ ... même structure ... ]
  },
  "marches": {
    "resume_court": str,
    "mouvements_notables": [{"nom": str, "variation_pct": float, "explication": str|null}]
  },
  "sport": {"items": [{"sport": str, "texte": str}]},
  "citation": {"texte": str, "auteur": str}|null,
  "meta": {"resume_1_phrase": str}
}"""

SCHEMA_SCIENCE = """{
  "science": {
    "mode": "decouverte" | "approfondi",
    "titre": str,
    "contenu_markdown": str
  }
}"""

SYSTEM_PROMPT_BLOC = """Tu es le rédacteur d'un briefing matinal personnel en français.
Tu rédiges ICI uniquement la partie actualité/marchés/sport/citation (l'article scientifique
est généré séparément par un autre appel -- ne le mentionne pas, ne le résume pas ici).

RÈGLES ABSOLUES (à respecter strictement) :
1. Utilise UNIQUEMENT les informations fournies dans les données ci-dessous. N'invente jamais
   un fait, un chiffre, une explication que tu ne peux pas justifier avec les données fournies.
1bis. Marchés (cf. cahier §5) : pour chaque mouvement dans "marches.mouvements_notables",
   cherche une cause dans "actualite_economie_contexte" (et, si pertinent, dans
   actualite_france/monde) : un événement, une annonce, une donnée macro, un contexte
   géopolitique qui explique raisonnablement ce mouvement. Si tu en trouves une, résume-la
   en une courte phrase dans "explication". Si aucune donnée fournie ne permet de justifier
   la cause, mets "explication": null plutôt que d'inventer -- mais dans ce cas ne répète
   PAS la variation chiffrée en guise d'explication (elle est déjà dans "variation_pct"),
   laisse simplement null. "resume_court" doit être un ou deux phrases de CONTEXTE
   (ce qui se passe sur les marchés et pourquoi, si connu) -- jamais une simple énumération
   des indices et de leurs pourcentages : ces chiffres sont déjà affichés séparément par
   indice, les répéter dans resume_court n'apporte rien (cf. cahier §5, exemple "CAC 40:
   -2,1%" à toujours accompagner d'une explication, pas d'une redite).
2. Style : clair, concis pour l'actualité, factuel, sans sensationnalisme, sans opinion
   politique, sans exagération, en français.
3. Pour chaque actualité, réponds implicitement à Quoi/Où/Quand/Pourquoi important, et pour
   les sujets complexes ajoute les conséquences possibles SANS les présenter comme certaines.
4. Respecte le statut de vérification fourni pour chaque événement : si "information_rapportee",
   commence la phrase par "Selon [source], ...". Si "fait_confirme", formule-le normalement.
5. Ne remplis pas artificiellement une section : si peu d'événements sont réellement
   importants, n'en retiens que peu.
6. Citation du jour : uniquement si tu es certain de l'authenticité de l'attribution. Sinon,
   renvoie "citation": null.
7. Réponds STRICTEMENT en JSON valide conforme au schéma donné, sans texte avant/après, sans
   balises markdown autour du JSON.

SCHÉMA JSON ATTENDU :
""" + SCHEMA_BLOC

SYSTEM_PROMPT_SCIENCE = """Tu es le rédacteur de la section science/technologie d'un briefing
matinal personnel en français. Tu rédiges UNIQUEMENT cet article (l'actualité, les marchés et
le sport sont générés séparément par un autre appel).

RÈGLES ABSOLUES (à respecter strictement) :
1. Utilise UNIQUEMENT les informations fournies ci-dessous (titre/résumé/source du sujet).
   N'invente jamais un fait, un chiffre ou une donnée scientifique que tu ne peux pas justifier
   avec les données fournies ou des connaissances scientifiques largement établies et non
   controversées sur ce sujet précis.
2. Si "science_mode" est "decouverte", rédige un article court sur la découverte majeure
   fournie (vérifie que son importance n'est pas exagérée). Si "approfondi", rédige un article
   pédagogique approfondi (~10 minutes de lecture) sur le sujet fourni, structuré en :
   introduction, pourquoi c'est important, explication du phénomène, mécanismes, données
   scientifiques, ce qui est su, ce qui reste incertain, limites/controverses, conclusion.
3. Ton d'une bonne revue de vulgarisation scientifique : précis, pédagogique, sans
   sensationnalisme, sans déformer les connaissances pour simplifier.
4. Réponds STRICTEMENT en JSON valide conforme au schéma donné, sans texte avant/après, sans
   balises markdown autour du JSON.

SCHÉMA JSON ATTENDU :
""" + SCHEMA_SCIENCE

# Budgets de sortie dédiés par appel (cf. llm_provider.MAX_OUTPUT_TOKENS pour le diagnostic
# complet). Le bloc est majoritairement des phrases courtes -> 1800 tokens est confortable
# pour 5 actus France + 5 Monde + marchés + 4 items sport + citation. L'article science est le
# poste le plus gourmand en sortie (~10 min de lecture, souvent 1200-1800 mots) -> budget
# nettement supérieur, dédié à lui seul désormais (avant : un seul budget de 3500 partagé
# entre TOUT, cause du "Unterminated string" du 26/09 quand la science prenait toute la place).
SCHEMA_ANGLAIS = """{
  "traduction_titre": str,
  "traduction_resume": str,
  "mots_importants": [{"mot": str, "traduction": str, "exemple": str}],
  "niveau": str
}"""

SYSTEM_PROMPT_ANGLAIS = """Tu es un professeur d'anglais qui aide un francophone à apprendre
l'anglais à partir d'un court extrait du New York Times fourni ci-dessous (titre + résumé,
en anglais). Tu rédiges UNIQUEMENT cette section (l'actualité, les marchés, le sport et la
science sont générés séparément par d'autres appels).

RÈGLES ABSOLUES (à respecter strictement) :
1. "traduction_titre" et "traduction_resume" : traduction française FIDÈLE du titre et du
   résumé fournis. N'ajoute, ne déduis et n'invente AUCUN fait qui ne soit pas déjà dans le
   texte anglais fourni -- une traduction reste une traduction, jamais un résumé enrichi ni
   une réécriture avec des détails supplémentaires (cf. cahier §1 : ne jamais inventer un
   fait).
2. "mots_importants" : choisis entre 5 et 8 mots ou expressions anglaises TIRÉS de ce titre
   et de ce résumé, utiles à apprendre (vocabulaire soutenu, faux-amis, expressions idiomatiques,
   termes d'actualité) -- pas des mots triviaux (the, is, a...). Pour chacun : "mot" (tel qu'il
   apparaît dans le texte), "traduction" (français), "exemple" (UNE phrase anglaise simple et
   courte utilisant ce mot dans un sens comparable -- cette phrase d'exemple pédagogique peut
   être une phrase originale que tu inventes pour illustrer l'usage du mot, ce n'est PAS
   soumis à la règle 1 puisqu'elle n'affirme aucun fait sur l'actualité elle-même, seulement
   un exemple de langue).
3. "niveau" : estimation simple et honnête du niveau (ex. "intermédiaire", "avancé") du
   texte fourni pour un apprenant francophone.
4. Réponds STRICTEMENT en JSON valide conforme au schéma donné, sans texte avant/après, sans
   balises markdown autour du JSON.

SCHÉMA JSON ATTENDU :
""" + SCHEMA_ANGLAIS

# Tout petit appel (un titre + un court résumé RSS à traduire, 5-8 mots de vocabulaire) --
# budget de sortie réduit en conséquence.
MAX_OUTPUT_TOKENS_ANGLAIS = 900

# NB (2026-09-28) : pause entre deux appels LLM consécutifs (run réel du 28/09 : le bloc passait
# sur Groq puis science/anglais tombaient en 429 -- fenêtre TPM d'une minute encore saturée).
# 60 s = la fenêtre de rate-limit par minute des providers gratuits. Ajustable sans code via
# la variable d'environnement LLM_CALL_SPACING_SECONDS (mettre 0 pour les tests/le debug).
# La pause n'a lieu qu'entre deux appels réellement lancés (pas de pause pour rien).
def _spacing_seconds() -> int:
    try:
        return max(0, int(os.environ.get("LLM_CALL_SPACING_SECONDS", "60")))
    except ValueError:
        return 60


def _pause_between_calls(label_suivant: str) -> None:
    delay = _spacing_seconds()
    if delay:
        logger.info("Pause de %d s avant l'appel LLM '%s' (espacement anti rate-limit)", delay, label_suivant)
        time.sleep(delay)

MAX_OUTPUT_TOKENS_BLOC = 1800
MAX_OUTPUT_TOKENS_SCIENCE = 3000


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


def _light_event(e: dict) -> dict:
    """Allégement commun : le LLM n'a besoin que des NOMS de sources (schéma "sources": [str]),
    pas de leurs URLs, qui gonflent le payload sans utilité pour la rédaction."""
    light = {k: v for k, v in e.items() if k != "sources"}
    light["sources"] = [s["nom"] if isinstance(s, dict) else s for s in e.get("sources", [])]
    return light


def _serialize(payload: dict) -> str:
    # JSON compact (pas d'indentation, séparateurs sans espace) : même information, 20-30% de
    # caractères en moins qu'avec indent=2. Le LLM n'a pas besoin d'un JSON lisible par un
    # humain pour le comprendre.
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def _build_user_prompt_bloc(analysed: dict, is_monday: bool, max_chars: int = MAX_PROMPT_CHARS) -> str:
    """Payload pour l'appel LLM "bloc" (actualité+marchés+sport). Ne contient PLUS
    science_mode/science_source (cf. _build_user_prompt_science, appel séparé depuis le
    2026-09-27)."""
    france = list(analysed["actualite_france"])
    monde = list(analysed["actualite_monde"])

    # cf. bug corrigé le 24/09 : les articles économie étaient collectés puis jetés avant
    # d'atteindre le LLM (main.py) -- résultat, "explication" restait toujours null et
    # resume_court n'avait que les chiffres bruts à reformuler (aucune cause disponible).
    # On les transmet maintenant, allégés comme france/monde.
    economie = [_light_event(e) for e in analysed.get("actualite_economie", [])]

    france = [_light_event(e) for e in france]
    monde = [_light_event(e) for e in monde]

    # Allégement sport : le schéma de sortie n'attend qu'une liste de courtes phrases par
    # catégorie -- le LLM n'a besoin que du titre de chaque événement, pas du dict complet
    # (resume/sources/url/categorie/score) que produit le pipeline d'analyse.
    def _light_sport(sport_events: dict) -> dict:
        return {cat: [e["titre"] for e in evs] for cat, evs in sport_events.items()}

    def _payload(france_l, monde_l, economie_l, sport_l, marches_l) -> dict:
        return {
            "jour_lundi_couvre_weekend": is_monday,
            "actualite_france": france_l,
            "actualite_monde": monde_l,
            # Fournie UNIQUEMENT comme contexte pour expliquer les mouvements de marchés
            # (cf. "marches" ci-dessous) -- ne doit pas devenir une 3e liste d'actualités
            # affichée telle quelle (cf. SYSTEM_PROMPT, règle dédiée).
            "actualite_economie_contexte": economie_l,
            "marches": marches_l,
            "sport": sport_l,
        }

    sport = _light_sport(analysed["sport_events"])
    # cf. cahier §4 : actualité = priorité maximale. En cas de dépassement du budget, on
    # réduit d'abord le sport (moins prioritaire, et déjà plafonné à 3-4 au total par
    # main.py donc rarement nécessaire), puis le contexte économie (utile mais pas
    # indispensable au cœur du briefing), et jamais les marchés eux-mêmes (déjà réduits aux
    # seuls mouvements significatifs en amont).
    marches = analysed["marches_data"]
    serialized = _serialize(_payload(france, monde, economie, sport, marches))

    trimmed_sport = False
    while len(serialized) > max_chars and any(sport.values()):
        # Retire un item de la catégorie sport la plus fournie, à tour de rôle.
        cat = max(sport, key=lambda c: len(sport[c]))
        if sport[cat]:
            sport[cat].pop()
        trimmed_sport = True
        serialized = _serialize(_payload(france, monde, economie, sport, marches))

    trimmed_economie = False
    while len(serialized) > max_chars and economie:
        economie.pop()
        trimmed_economie = True
        serialized = _serialize(_payload(france, monde, economie, sport, marches))

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
        serialized = _serialize(_payload(france, monde, economie, sport, marches))

    if trimmed_sport or trimmed_economie or trimmed_actualite:
        logger.warning(
            "Prompt LLM trop volumineux (>%d caractères) -> sport réduit=%s, économie réduite=%s, "
            "actualité réduite=%s (retenus après réduction : france=%d, monde=%d, économie=%d, "
            "sport=%d au total).",
            max_chars, trimmed_sport, trimmed_economie, trimmed_actualite, len(france), len(monde),
            len(economie), sum(len(v) for v in sport.values()),
        )

    return "Voici les données collectées et analysées pour le briefing de ce matin.\n\n" + serialized


def _build_user_prompt_science(science_topic: dict) -> str:
    """Payload pour l'appel LLM "science" (séparé du bloc depuis le 2026-09-27). Toujours très
    petit (un seul sujet : titre/résumé/url/sources) -- pas de logique de réduction nécessaire,
    contrairement au bloc dont la taille dépend du nombre d'actualités du jour."""
    payload = {
        "science_mode": science_topic["mode"],
        "science_source": science_topic["contenu_source"],
    }
    return (
        "Voici le sujet scientifique sélectionné pour le briefing de ce matin.\n\n"
        + _serialize(payload)
    )


def _build_user_prompt_anglais(nyt_article: dict) -> str:
    """Payload pour l'appel LLM "anglais" (nouvelle section, 2026-09-27). `nyt_article` vient
    de select_nyt_article() -- titre+résumé ORIGINAUX en anglais tels que fournis par le flux
    RSS NYT, jamais réécrits avant ce point."""
    payload = {"titre_anglais": nyt_article["titre"], "resume_anglais": nyt_article["resume"]}
    return (
        "Voici l'extrait du New York Times à traduire et dont il faut extraire le "
        "vocabulaire important pour ce matin.\n\n" + _serialize(payload)
    )


def _clean_json_text(raw: str) -> str:
    """Retire l'éventuel balisage markdown (```json ... ```) qu'un modèle ajoute parfois
    malgré la consigne JSON strict, avant json.loads()."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    return cleaned


def _run_chain(
    providers: list[LLMProvider],
    system_prompt: str,
    build_user_prompt,
    output_tokens: int,
    prompt_char_budgets: tuple[int, ...],
) -> tuple[dict | None, str | None, str | None]:
    """Essaie chaque provider de `providers` dans l'ordre ; pour chacun, jusqu'à
    len(prompt_char_budgets) tentatives avec un budget de caractères décroissant (utile
    seulement pour le bloc, dont la taille du prompt varie selon le nombre d'actualités --
    pour la science, passer un tuple à un seul élément puisque le payload est déjà minimal).

    Retourne (corps_json_parsé, nom_du_provider_qui_a_réussi, résumé_des_erreurs) : le 1er et
    le 2e sont None si tous les providers ont échoué, auquel cas le 3e contient la chaîne
    "provider: erreur | provider: erreur | ..." pour diagnostic (cf. _erreur_llm)."""
    erreurs_par_provider: dict[str, str] = {}
    for provider in providers:
        derniere_erreur: str | None = None
        for tentative, max_chars in enumerate(prompt_char_budgets, start=1):
            try:
                user_prompt = build_user_prompt(max_chars)
                raw = provider.complete(system_prompt, user_prompt, max_tokens=output_tokens)
                return json.loads(_clean_json_text(raw)), provider.name, None
            except Exception as exc:  # noqa: BLE001
                derniere_erreur = str(exc)
                detail = getattr(exc, "body_excerpt", None)
                logger.error(
                    "Échec de la génération LLM (%s, tentative %d/%d, budget=%d caractères): %s%s",
                    provider.name, tentative, len(prompt_char_budgets), max_chars, exc,
                    f" | corps de la réponse: {detail}" if detail else "",
                )
                # cf. NB 2026-09-26 : un 429 "rate limit" signifie que le quota de la fenêtre
                # en cours est épuisé -- retenter IMMÉDIATEMENT le MÊME provider avec un
                # prompt plus petit ne peut pas réussir, le budget consommé ne se régénère
                # pas en quelques millisecondes. On passe directement au provider suivant.
                if getattr(exc, "status_code", None) == 429:
                    logger.warning(
                        "Provider '%s' en rate limit (429) -> passage direct au provider "
                        "suivant sans nouvelle tentative.", provider.name,
                    )
                    break
        logger.warning("Provider '%s' épuisé -> passage au suivant s'il existe.", provider.name)
        if derniere_erreur:
            erreurs_par_provider[provider.name] = derniere_erreur[:200]

    erreur_resumee = (
        " | ".join(f"{name}: {msg}" for name, msg in erreurs_par_provider.items())
        if erreurs_par_provider else None
    )
    return None, None, erreur_resumee


def generate(
    pool: dict[str, LLMProvider],
    analysed: dict,
    science_topic: dict,
    nyt_article: dict | None,
    weather_summary: dict | None,
    is_monday: bool,
    plan: dict | None = None,
) -> dict:
    """Retourne l'objet Briefing complet (dict), prêt pour le stockage.

    NB (2026-09-30, refonte de la répartition, décidée avec l'utilisateur) : le briefing est
    rédigé en HUIT parties confiées à quatre fournisseurs, en DEUX appels espacés -- cf.
    config/llm_plan.yaml (le plan), llm_orchestrator.py (moteur : parallélisme + secours en
    chaîne) et parts.py (prompts, schémas, fusion). `pool` = {nom: provider} des fournisseurs
    dont la clé API est disponible (llm_provider.get_provider_pool()).

    `analysed` doit contenir : actualite_france, actualite_monde, marches_data, sport_events
    (déjà scorés+filtrés+vérifiés en amont, cf. main.py).

    Le résultat part TOUJOURS d'un fallback_briefing() complet (jamais de section manquante),
    puis chaque partie rédigée avec succès remplace son contenu brut -- une partie qui échoue
    chez tous ses fournisseurs ne fait perdre que cette partie (cf. cahier §21). Les anciennes
    fonctions _run_chain / _build_user_prompt_* ci-dessus ne sont plus utilisées par ce chemin
    (conservées pour référence, à supprimer une fois la nouvelle répartition validée en réel).
    """
    from . import llm_orchestrator, parts as parts_mod  # import local : évite un import circulaire

    resultat = fallback_briefing(
        analysed, science_topic, nyt_article, weather_summary, is_monday, erreur_llm=None,
    )
    if not pool:
        logger.warning("Aucun LLM disponible -> génération en mode fallback (sans synthèse rédigée)")
        return resultat

    parts = parts_mod.build_parts(analysed, science_topic, nyt_article, is_monday)
    results = llm_orchestrator.run_plan(plan or llm_orchestrator.load_plan(), parts, pool)
    parts_mod.merge_results(resultat, results, nyt_article, science_source=science_topic["contenu_source"], analysed=analysed)

    diag = parts_mod.diagnostics(results)
    resultat.update(diag)
    ok = [r for r in results.values() if r.ok]
    resultat["_genere_par_llm"] = bool(ok)
    resultat["_provider"] = "+".join(sorted({r.provider for r in ok})) or None
    erreurs = [f"{r.name}[{r.error}]" for r in results.values() if r.error]
    resultat["_erreur_llm"] = (" | ".join(erreurs)[:900] if erreurs else None)
    logger.info("Parties rédigées par LLM : %d/%d (%s)", len(ok), len(results),
                ", ".join(f"{r.name}={r.provider or 'ECHEC'}" for r in results.values()))
    return resultat


def fallback_briefing(
    analysed: dict,
    science_topic: dict,
    nyt_article: dict | None,
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
        "sport": sport_format.depuis_evenements(analysed["sport_events"]),
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
        # NB (2026-09-27) : section "Anglais du jour" -- fallback = article NYT brut (titre +
        # résumé en anglais, non traduit) si un article a été trouvé ce jour-là, sinon None
        # (jamais de section vide/fabriquée -- cf. cahier §21, même logique que "citation").
        "anglais": (
            {
                "titre_anglais": nyt_article["titre"],
                "resume_anglais": nyt_article["resume"],
                "url": nyt_article["url"],
                "source": nyt_article["source"],
                "traduction_titre": None,
                "traduction_resume": "Traduction indisponible pour le moment (LLM hors service).",
                "mots_importants": [],
                "niveau": None,
            }
            if nyt_article else None
        ),
        "meta": {"resume_1_phrase": "Briefing minimal généré sans synthèse LLM."},
        "_genere_par_llm": False,
        "_provider": None,
        # NB (2026-09-19, chaîne complète depuis 2026-09-25) : cause réelle de l'échec LLM
        # pour CHAQUE provider de repli tenté ("provider: message | provider: message | ..."),
        # pour diagnostic sans devoir rouvrir les logs du run -- cf. storage.save_briefing qui
        # la reprend aussi dans status.json. Troncature portée à 900 (au lieu de 500) car la
        # chaîne agrège désormais plusieurs providers au lieu d'un seul message.
        "_erreur_llm": (erreur_llm[:900] if erreur_llm else None),
    }


def select_nyt_article(raw_monde_items: list[dict]) -> dict | None:
    """Sélectionne UN article du NYT (flux 'New York Times World', cf. config.yaml
    rss.monde -- déjà collecté quotidiennement, ajouté le 25/09 pour l'actu Monde) pour la
    nouvelle section 'Anglais du jour' (demande explicite du 27/09). Choisi dans le flux BRUT
    (avant dédup/scoring/plafond de la section actualité Monde) pour ne jamais dépendre du
    hasard du scoring -- ces 2 usages du même flux RSS sont indépendants l'un de l'autre.

    Heuristique de choix (V1 volontairement simple, cf. cahier §1 fiabilité > sophistication) :
    parmi les items dont la source est le NYT, celui au résumé RSS le plus long -- un résumé
    court/vide donne peu de matière pour un exercice de traduction + vocabulaire. Retourne
    None si le flux n'a rien produit ce jour-là (flux vide/en erreur, cf. sources_rss_en_erreur)
    -- dans ce cas la section "Anglais du jour" est absente plutôt que fabriquée."""
    candidats = [
        item for item in raw_monde_items
        if "new york times" in item.get("source", "").lower()
    ]
    if not candidats:
        return None
    top = max(candidats, key=lambda item: (score_apprentissage(item.get("titre", ""), item.get("resume", "")),
                                           len(item.get("resume", ""))))
    return {
        "titre": top["titre"],
        "resume": top.get("resume", ""),
        "url": top.get("url", ""),
        "source": top.get("source", "The New York Times"),
    }


# --- Mode science (05/10/2026, point 3 de ANALYSE_RUN_2026-10-05.md) ------------------------------
# Constat : le mode « découverte » s'est déclenché sur un simple résumé RSS du Monde (« Et si la Floride arrêtait de
# vacciner… », sujet de politique de santé, aucune étude identifiée, aucun chiffre) ; l'article écrit était pauvre et
# se contredisait. Un mode « découverte » exige désormais : (1) un vocabulaire de RECHERCHE (étude, chercheurs,
# essai, revue, télescope…), (2) pas de vocabulaire politique/société, (3) un résumé substantiel, (4) deux sources
# indépendantes OU une source primaire (organisme de recherche / revue). Sinon : mode « approfondi », où l'article
# pédagogique est de toute façon contrôlé par science_guard.
SOURCES_PRIMAIRES_SCIENCE = ("cnrs", "nature", "inserm", "nasa", "esa", "cea", "pasteur", "lancet", "nejm",
                             "pnas", "arxiv", "cern", "cnes", "inria", "ifremer", "noaa")
# Noms EXACTS (mot entier) : « Le Monde Sciences » (journal généraliste) n'est PAS une source primaire.
_RE_PRIMAIRE = re.compile(r"(?<![\w])(?:" + "|".join(SOURCES_PRIMAIRES_SCIENCE) + r"|science)(?![\w])", re.I)
_RE_RECHERCHE = re.compile(
    r"\b(étude|études|chercheurs?|chercheuses?|scientifiques?|découverte|découvert|publi[ée]e? dans|revue|essai clinique|"
    r"expérience|télescope|satellite|sonde|mission spatiale|exoplanète|génome|protéine|neurones?|cellules?|fossile|"
    r"laboratoire|simulation|modélisation|molécule|particule|espèce|mutation|algorithme|modèle d'ia|supraconduct\w+)\b",
    re.I)
_RE_POLITIQUE = re.compile(
    r"\b(gouvernement|ministre|président|présidentielle|élection|élections|budget|parlement|sénat|assemblée|"
    r"loi|trump|macron|polémique|grève|manifestation|procès|tribunal|politique de santé|arrêter de vacciner)\b", re.I)
RESUME_MIN_DECOUVERTE = 200


def decouverte_qualifiee(event: dict) -> tuple[bool, str]:
    """(qualifiée ?, raison du refus) — fonction pure, sans réseau ni LLM."""
    texte = f"{event.get('titre', '')} {event.get('resume', '')}"
    if not _RE_RECHERCHE.search(texte):
        return False, "aucun vocabulaire de recherche (étude, chercheurs…)"
    if _RE_POLITIQUE.search(f"{event.get('titre', '')}"):
        return False, "sujet de politique/société dans le titre"
    # 06/10/2026 : pour un événement fusionné (plusieurs sources FR/EN), on compte la matière RÉELLEMENT disponible =
    # somme des résumés distincts de toutes les sources, pas seulement celui d'un article.
    resumes = {str(t.get("resume", "") or "").strip() for t in (event.get("textes_sources") or [])}
    resumes.add(str(event.get("resume", "") or "").strip())
    if sum(len(r) for r in resumes) < RESUME_MIN_DECOUVERTE:
        return False, f"résumé trop court (< {RESUME_MIN_DECOUVERTE} caractères)"
    noms = [str(x.get("nom", "")).lower() for x in event.get("sources", [])]
    primaire = any(_RE_PRIMAIRE.search(n) and "monde" not in n for n in noms)
    if event.get("nb_sources", 1) < 2 and not primaire:
        return False, "une seule source non primaire"
    return True, ""


def _sujet(top: dict, mode: str) -> dict:
    return {
        "mode": mode,
        "contenu_source": {
            "titre": top["titre"],
            "resume": top.get("resume", ""),
            "url": top.get("url_principale", ""),
            "sources": [s["nom"] for s in top.get("sources", [])],
            "liens_sources": [{"nom": s["nom"], "url": s.get("url", "")} for s in top.get("sources", [])][:6],
            # 06/10/2026 : plusieurs sources d'un même événement (fusion FR/EN) = plusieurs résumés réels à donner au
            # rédacteur (au lieu d'un seul), plafonnés pour rester dans le budget du prompt.
            "textes_sources": [
                {"source": t.get("source", ""), "titre": str(t.get("titre", ""))[:200],
                 "resume": str(t.get("resume", ""))[:700]}
                for t in (top.get("textes_sources") or [])[:4]
                if t.get("resume") or t.get("titre")
            ],
        },
    }


def select_science_topic(analysed_sciences: list[dict]) -> dict:
    """Choisit le mode science (§7) : « découverte » seulement si un événement QUALIFIÉ existe
    (cf. `decouverte_qualifiee`), sinon mode « approfondi » avec le meilleur candidat de recherche
    (vocabulaire scientifique, hors politique/société), à défaut le premier disponible."""
    for e in analysed_sciences or []:
        ok, raison = decouverte_qualifiee(e)
        if ok:
            logger.info("Science: mode découverte retenu — %s", str(e.get("titre", ""))[:90])
            return _sujet(e, "decouverte")
        logger.info("Science: découverte refusée (%s) — %s", raison, str(e.get("titre", ""))[:90])

    if analysed_sciences:
        recherche = [e for e in analysed_sciences
                     if _RE_RECHERCHE.search(f"{e.get('titre', '')} {e.get('resume', '')}")
                     and not _RE_POLITIQUE.search(str(e.get("titre", "")))]
        top = max(recherche, key=lambda e: len(str(e.get("resume", "")))) if recherche else analysed_sciences[0]
        return _sujet(top, "approfondi")

    return {
        "mode": "approfondi",
        "contenu_source": {
            "titre": "Aucun sujet scientifique récent disponible",
            "resume": "",
            "url": "",
            "sources": [],
        },
    }
