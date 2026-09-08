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
DATA_DIR = ROOT / "data" / "briefings"


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


def compute_window(reference_date: datetime | None = None) -> tuple[datetime, datetime, bool]:
    """Calcule la fenêtre de recherche selon le jour (cf. cahier §3).

    Retourne (depuis, jusqu'à, est_lundi).
    Le lundi : couvre samedi + dimanche + lundi matin -> fenêtre large (~60h).
    Les autres jours : fenêtre depuis le dernier briefing (~24h, avec marge).
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
    else:
        # Depuis le dernier briefing = veille à la même heure, avec marge de 6h.
        depuis = now - timedelta(hours=30)

    return depuis, now, is_monday


def today_iso(reference_date: datetime | None = None) -> str:
    now = reference_date or paris_now()
    return now.strftime("%Y-%m-%d")
