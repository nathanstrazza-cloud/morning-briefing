"""18/10/2026 (défaut n°9) : pas de run le week-end sauf FORCE_RUN=true ; la date forcée/TEST_MODE passent."""
from datetime import datetime

import pytz

from src import main

TZ = pytz.timezone("Europe/Paris")


def _sunday(monkeypatch):
    monkeypatch.setattr(main, "paris_now", lambda: TZ.localize(datetime(2026, 10, 18, 7, 0)))
    monkeypatch.setattr(main, "setup_logging", lambda run_id: __import__("logging").getLogger("t"))
    monkeypatch.delenv("TEST_MODE", raising=False)
    monkeypatch.delenv("FORCE_RUN", raising=False)


def test_dimanche_run_ignore(monkeypatch):
    _sunday(monkeypatch)
    monkeypatch.setattr(main, "load_config", lambda: (_ for _ in ()).throw(AssertionError("ne doit pas démarrer")))
    assert main.run() == 0


def test_dimanche_force_run_demarre(monkeypatch):
    _sunday(monkeypatch)
    monkeypatch.setenv("FORCE_RUN", "true")
    monkeypatch.setattr(main.storage, "day_briefing_exists", lambda d: True)  # s'arrête sur l'idempotence, après le garde-fou
    assert main.run() == 0
