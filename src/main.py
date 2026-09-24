"""Point d'entrée du pipeline complet (cf. cahier §17-18).

Usage :
    python -m src.main                     # run normal, aujourd'hui, heure Paris
    python -m src.main --date 2026-09-07    # force la date traitée (tests)
    python -m src.main --no-llm             # force le mode fallback (test rapide sans clé)

Le pipeline ne lève jamais d'exception non gérée vers l'extérieur : toute erreur est
capturée, journalisée, et si elle est fatale, `stockage.record_failure` est appelé pour
préserver le dernier briefing valide (cf. cahier §21).
"""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime

import pytz

from .analyse import dedup, scoring, verification
from .collecte import collector, markets as markets_collect, weather as weather_collect
from .generation import briefing_generator, llm_provider
from .stockage import storage
from .utils import compute_window, load_config, paris_now, setup_logging


def run(date_override: str | None = None, force_no_llm: bool = False) -> int:
    tz = pytz.timezone("Europe/Paris")
    if date_override:
        reference = tz.localize(datetime.strptime(date_override, "%Y-%m-%d").replace(hour=6, minute=30))
    else:
        reference = paris_now()

    date_iso = reference.strftime("%Y-%m-%d")
    run_id = reference.strftime("%Y-%m-%d_%H%M%S")
    logger = setup_logging(run_id)
    logger.info("=== Démarrage du run Morning Briefing pour le %s ===", date_iso)

    # Le workflow GitHub Actions programme deux cron (été/hiver, cf. briefing.yml) car GH
    # Actions ne gère pas le changement d'heure : à une saison donnée, l'un des deux cron
    # correspond à 06:30 Paris, l'autre à 07:30 (mauvaise saison). Sans garde-fou, le
    # pipeline tournerait deux fois par jour.
    #
    # NB (corrigé le 2026-09-09) : une fenêtre horaire stricte (06:00-07:29) avait été
    # utilisée initialement pour filtrer le cron "hors saison", mais GitHub Actions retarde
    # fréquemment l'exécution des cron de plusieurs heures (limite connue du plan gratuit,
    # cf. logs des 2026-09-08 et 2026-09-09 : déclenchements réels à 18:59, 11:02 et 11:56
    # Paris au lieu de 06:30/07:30). Cette fenêtre trop stricte faisait que le pipeline ne
    # tournait plus jamais. On la remplace par une garde d'IDEMPOTENCE : le premier
    # déclenchement de la journée (quelle que soit l'heure réelle) génère le briefing ;
    # tout déclenchement suivant pour la même date (le second cron, ou un retry) est ignoré
    # car un fichier docs/data/briefings/{date}.json existe déjà pour aujourd'hui.
    if not date_override:
        if reference.hour < 6:
            logger.info(
                "Heure Paris actuelle (%02d:%02d) avant 06:00 -> run ignoré "
                "(démarrage anormalement matinal, ne devrait pas arriver en usage normal).",
                reference.hour, reference.minute,
            )
            return 0
        if storage.day_briefing_exists(date_iso):
            logger.info(
                "Un briefing a déjà été généré avec succès aujourd'hui (%s) -> run ignoré "
                "(second déclenchement cron été/hiver, comportement attendu).",
                date_iso,
            )
            return 0

    rss_diagnostics: list[dict] = []  # rempli par collect_all si on l'atteint (cf. except ci-dessous)
    market_diagnostics: list[dict] = []
    try:
        config = load_config()
        last_success = storage.get_last_successful_datetime()
        depuis, jusqu_a, is_monday = compute_window(reference, last_success=last_success)
        logger.info(
            "Fenêtre de recherche: %s -> %s (lundi=%s, dernier_succes=%s)",
            depuis, jusqu_a, is_monday, last_success,
        )

        # 1. COLLECTE
        raw = collector.collect_all(config, depuis, is_monday)
        rss_diagnostics = raw.get("rss_diagnostics", [])
        market_diagnostics = raw.get("market_diagnostics", [])

        # 2. ANALYSE — actualité France/Monde
        seuil = config["seuils"]["score_min_affichage"]

        # cf. docstring ci-dessus : entonnoir de filtrage tracé à chaque étape pour pouvoir
        # diagnostiquer une section vide sans deviner (remonté jusqu'à status.json plus bas).
        funnel_actualite = {}

        events_france = dedup.deduplicate(raw["news"]["france"])
        n_france_bruts, n_france_dedup = len(raw["news"]["france"]), len(events_france)
        events_france = scoring.score_events(events_france)
        events_france = verification.classify_events(events_france)
        events_france = scoring.filter_by_threshold(events_france, seuil)
        funnel_actualite["france"] = {
            "bruts": n_france_bruts, "evenements_uniques": n_france_dedup,
            "retenus_apres_seuil": len(events_france),
        }

        events_monde = dedup.deduplicate(raw["news"]["monde"])
        n_monde_bruts, n_monde_dedup = len(raw["news"]["monde"]), len(events_monde)
        events_monde = scoring.score_events(events_monde)
        events_monde = verification.classify_events(events_monde)
        events_monde = scoring.filter_by_threshold(events_monde, seuil)
        funnel_actualite["monde"] = {
            "bruts": n_monde_bruts, "evenements_uniques": n_monde_dedup,
            "retenus_apres_seuil": len(events_monde),
        }
        logger.info(
            "Entonnoir actualité (seuil=%d): france %s | monde %s",
            seuil, funnel_actualite["france"], funnel_actualite["monde"],
        )

        # cf. cahier §1 + demande explicite (2026-09-19) : 5 infos France + 5 Monde suffisent
        # -- les listes sont déjà triées par score décroissant (cf. scoring.score_events),
        # on garde donc les meilleures. Réduit aussi la taille du prompt LLM en amont plutôt
        # que de compter uniquement sur le rognage de secours dans briefing_generator.py.
        max_par_zone = config["seuils"].get("max_actualites_par_zone", 5)
        events_france = events_france[:max_par_zone]
        events_monde = events_monde[:max_par_zone]

        events_economie = dedup.deduplicate(raw["news"]["economie"])
        events_economie = scoring.score_events(events_economie)

        events_sciences = dedup.deduplicate(raw["news"]["sciences"])
        events_sciences = scoring.score_events(events_sciences)
        events_sciences = verification.classify_events(events_sciences)

        # Sport : dédup + score par catégorie (le cahier veut peu d'items mais toujours au
        # moins les résultats marquants, cf. §6). Le "score plancher" (4/10, cf. scoring.py)
        # est neutre : il ne distingue pas les Spurs (priorité explicite du cahier §6) des
        # autres clubs. On applique donc un bonus dédié avant la sélection finale, sinon un
        # simple tri par score risquerait d'évincer les Spurs au profit d'une actu basket
        # quelconque au même score.
        BONUS_EQUIPE_PRIORITAIRE = 2
        sport_events = {}
        for cat, items in raw["sport"].items():
            evs = dedup.deduplicate(items)
            evs = scoring.score_events(evs)
            for e in evs:
                if e.get("equipe_prioritaire"):
                    e["score"] = min(10, e["score"] + BONUS_EQUIPE_PRIORITAIRE)
            evs.sort(key=lambda e: e["score"], reverse=True)
            sport_events[cat] = evs[:5]  # plafond large par catégorie, la réduction globale suit

        # Réduction globale demandée par l'utilisateur le 24/09 (remplace le seul plafond par
        # catégorie ci-dessus, qui pouvait laisser jusqu'à 20 items au total) : on regroupe
        # toutes les catégories, on trie par score décroissant (bonus Spurs déjà appliqué), et
        # on ne garde que les meilleures au total, réparties ensuite par catégorie. cf. cahier
        # §6 : pas de compte-rendu exhaustif, seulement les résultats/événements marquants.
        max_sport_total = config["seuils"].get("max_sport_total", 4)
        tous_sport = [
            {**e, "_categorie": cat} for cat, evs in sport_events.items() for e in evs
        ]
        tous_sport.sort(key=lambda e: e["score"], reverse=True)
        retenus = tous_sport[:max_sport_total]
        sport_events = {cat: [] for cat in sport_events}
        for e in retenus:
            sport_events[e["_categorie"]].append(e)
        logger.info(
            "Sport réduit à %d item(s) au total (max_sport_total=%d): %s",
            len(retenus), max_sport_total,
            {cat: len(evs) for cat, evs in sport_events.items()},
        )

        # Marchés : mouvements significatifs seulement
        seuil_marche = config["seuils"]["score_min_marche_pct"]
        mouvements = markets_collect.significant_moves(raw["marches"], seuil_marche)
        marches_data = {**raw["marches"], "mouvements_significatifs": mouvements}

        # cf. bug signalé le 24/09 : les articles économie étaient collectés et scorés
        # (ligne 125-126 ci-dessus) mais jamais transmis au LLM -> "explication" restait
        # systématiquement null et resume_court se contentait de reformuler les chiffres bruts
        # (aucune donnée pour justifier une cause, cf. cahier §5 "chercher pourquoi le marché a
        # bougé"). On transmet maintenant les meilleurs articles économie au générateur.
        actualite_economie = events_economie[:8]

        # Météo
        weather_summary = weather_collect.summarize_zone(raw["meteo"])

        science_topic = briefing_generator.select_science_topic(events_sciences)

        analysed = {
            "actualite_france": events_france,
            "actualite_monde": events_monde,
            "actualite_economie": actualite_economie,
            "marches_data": marches_data,
            "sport_events": sport_events,
        }

        # 3. GÉNÉRATION
        providers = [] if force_no_llm else llm_provider.get_providers()
        briefing = briefing_generator.generate(providers, analysed, science_topic, weather_summary, is_monday)

        # 4. STOCKAGE
        storage.save_briefing(
            briefing, date_iso, reference.isoformat(),
            rss_diagnostics=rss_diagnostics, market_diagnostics=market_diagnostics,
            funnel_actualite=funnel_actualite,
        )

        logger.info("=== Run terminé avec succès pour le %s ===", date_iso)
        return 0

    except Exception as exc:  # noqa: BLE001
        logger.error("Échec fatal du pipeline: %s\n%s", exc, traceback.format_exc())
        try:
            storage.record_failure(
                date_iso, reference.isoformat(), str(exc),
                rss_diagnostics=rss_diagnostics, market_diagnostics=market_diagnostics,
            )
        except Exception:  # noqa: BLE001
            logger.error("Impossible même d'écrire status.json — vérifier les permissions disque.")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Génère le Morning Briefing du jour.")
    parser.add_argument("--date", help="Force la date traitée, format YYYY-MM-DD (tests)", default=None)
    parser.add_argument("--no-llm", action="store_true", help="Force le mode fallback sans LLM")
    args = parser.parse_args()

    exit_code = run(date_override=args.date, force_no_llm=args.no_llm)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
