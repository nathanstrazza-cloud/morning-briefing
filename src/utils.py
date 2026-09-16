"""Utilitaires partagés : chargement de la config, logging, fenêtre temporelle."""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytz
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "config.yaml"
LOGS_DIR = ROOT / "logs"
# NB (nettoyé le 2026-09-13) : un ancien DATA_DIR = ROOT / "data" / "briefings" existait ici,
# jamais utilisé et incohérent avec le vrai chemin de stockage (docs/data/briefings, défini
# dans stockage/storage.py pour être servi par GitHub Pages). Supprimé pour éviter toute
# confusion future — le seul DATA_DIR qui compte est celui de storage.py.


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(run_id: str) -> logging.Logger:
    """Un fichier de log par run (cf. cahier §22 journalisation), + sortie console."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"{run_id}.log"

    logger = logging.getLogger("morning_briefing")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    return logger


def paris_now() -> datetime:
    tz = pytz.timezone("Europe/Paris")
    return datetime.now(tz)


MARGE_SECURITE = timedelta(hours=6)
FENETRE_DEFAUT = timedelta(hours=30)
# Si le dernier briefing réussi remonte à plus de 4 jours (panne prolongée, pipeline resté
# cassé plusieurs jours...), on plafonne la fenêtre plutôt que de partir chercher des
# semaines d'actualité d'un coup (cf. cahier §4 : ne pas remplir artificiellement, et
# risque de payload/latence disproportionnés pour une fenêtre non bornée).
FENETRE_MAX = timedelta(days=4)


def compute_window(
    reference_date: datetime | None = None,
    last_success: datetime | None = None,
) -> tuple[datetime, datetime, bool]:
    """Calcule la fenêtre de recherche selon le jour (cf. cahier §3).

    Retourne (depuis, jusqu'à, est_lundi).
    Le lundi : couvre samedi + dimanche + lundi matin -> fenêtre large (~60h).
    Les autres jours : fenêtre depuis le dernier briefing réellement réussi (cf. cahier
    §3 : "la recherche porte principalement sur la période depuis le briefing précédent"),
    avec une marge de sécurité de 6h pour ne pas perdre d'articles publiés juste avant.

    NB (corrigé le 2026-09-13) : la fenêtre des jours normaux était figée à 30h fixes,
    indépendamment de la date du dernier run réussi. Si le pipeline manquait un jour (ce qui
    s'est déjà produit, cf. logs), un trou de couverture apparaissait silencieusement. On lit
    maintenant la date du dernier succès (transmise par l'appelant via `last_success`, lu
    depuis docs/data/briefings/latest.json par stockage.get_last_successful_datetime) et on
    calcule la fenêtre depuis cette date, plafonnée à FENETRE_MAX pour rester raisonnable.
    Si `last_success` n'est pas fourni (premier run, ou lecture impossible), on retombe sur
    l'ancien comportement (30h fixes) par sécurité.
    """
    tz = pytz.timezone("Europe/Paris")
    now = reference_date or paris_now()
    if now.tzinfo is None:
        now = tz.localize(now)

    is_monday = now.weekday() == 0  # 0 = lundi

    if is_monday:
        # Remonte jusqu'au vendredi 18h (fin de semaine précédente) pour être large,
        # ce qui couvre largement samedi + dimanche + lundi matin (cf. cahier §3).
        depuis = now - timedelta(days=3, hours=now.hour, minutes=now.minute)
        depuis = depuis.replace(hour=18, minute=0, second=0, microsecond=0)
    elif last_success is not None:
        if last_success.tzinfo is None:
            last_success = tz.localize(last_success)
        depuis = last_success - MARGE_SECURITE
        if now - depuis > FENETRE_MAX:
            depuis = now - FENETRE_MAX
    else:
        # Pas de dernier succès connu (premier run, ou lecture impossible) -> comportement
        # de repli historique.
        depuis = now - FENETRE_DEFAUT

    return depuis, now, is_monday


def today_iso(reference_date: datetime | None = None) -> str:
    now = reference_date or paris_now()
    return now.strftime("%Y-%m-%d")
