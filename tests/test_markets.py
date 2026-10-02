"""Tests hors réseau du calcul de variation de marché (correctif du 02/10/2026)."""
from datetime import datetime, timezone

from src.collecte.markets import compute_session_change


def _ts(y, m, d, h=16):
    return int(datetime(y, m, d, h, tzinfo=timezone.utc).timestamp())


def _result(closes, price, rmt, prev5=9999.0):
    days = [(2026, 9, 25), (2026, 9, 28), (2026, 9, 29), (2026, 9, 30), (2026, 10, 1)]
    return {
        "meta": {"regularMarketPrice": price, "regularMarketTime": rmt,
                 "exchangeTimezoneName": "Europe/Paris", "chartPreviousClose": prev5},
        "timestamp": [_ts(*d) for d in days[-len(closes):]],
        "indicators": {"quote": [{"close": closes}]},
    }


def test_variation_une_seance_pas_cinq_jours():
    # Séance du 01/10 terminée : 7900 -> 7800 = -1,27 %, et NON -3 % vs chartPreviousClose.
    r = _result([8100.0, 8050.0, 8000.0, 7900.0, 7800.0], 7800.0, _ts(2026, 10, 1))
    out = compute_session_change(r)
    assert out["variation_pct"] == -1.27
    assert out["date_reference"] == "2026-09-30"


def test_barre_du_jour_absente_utilise_derniere_cloture():
    # Cours courant du 02/10 (matière première 24h), dernière barre = 01/10.
    r = _result([8100.0, 8050.0, 8000.0, 7900.0, 7800.0], 7878.0, _ts(2026, 10, 2, 3))
    out = compute_session_change(r)
    assert out["cloture_veille"] == 7800.0 and out["variation_pct"] == 1.0


def test_valeurs_nulles_ignorees():
    r = _result([8100.0, None, 8000.0, 7900.0, 7800.0], 7800.0, _ts(2026, 10, 1))
    assert compute_session_change(r)["cloture_veille"] == 7900.0


def test_donnees_insuffisantes_retournent_none():
    assert compute_session_change(_result([7800.0], 7800.0, _ts(2026, 10, 1))) is None
    assert compute_session_change({"meta": {}, "timestamp": [], "indicators": {}}) is None
