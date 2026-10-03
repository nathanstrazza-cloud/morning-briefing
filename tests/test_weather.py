"""Météo : tests sans réseau (payloads Open-Meteo simulés)."""
from src.collecte import weather as w


def _payload(codes, precs, temps=None, probs=None, daily=None):
    times = [f"2026-10-05T{h:02d}:00" for h in range(24)]
    return {
        "current": {"temperature_2m": 15.0, "weather_code": 55, "wind_speed_10m": 5},
        "daily": daily or {"temperature_2m_max": [21], "temperature_2m_min": [14],
                           "precipitation_probability_max": [20], "wind_speed_10m_max": [18],
                           "wind_gusts_10m_max": [30], "precipitation_sum": [0.2], "weather_code": [55]},
        "hourly": {"time": times, "weather_code": codes, "precipitation": precs,
                   "temperature_2m": temps or [14 + h / 3 for h in range(24)],
                   "precipitation_probability": probs or [10] * 24, "wind_speed_10m": [10] * 24},
    }


def test_instant_drizzle_without_rain_becomes_overcast():
    # Cas réel du 01/10 : code instantané « bruine forte » mais 0 mm -> ne doit pas être affiché.
    p = _payload([55] * 24, [0.0] * 24)
    r = w.parse_city("Antibes", p)
    assert r["description"] == "couvert"
    assert all(per["description"] == "couvert" for per in r["periodes"])


def test_evolution_rain_in_evening():
    codes = [1] * 18 + [63] * 6
    precs = [0.0] * 18 + [2.0] * 6
    r = w.parse_city("Cannes", _payload(codes, precs))
    by = {p["label"]: p for p in r["periodes"]}
    assert by["Matin"]["description"] == "plutôt dégagé"
    assert by["Soir"]["description"] == "pluie"
    z = w.summarize_zone([r])
    assert "le soir" in z["resume"] and "pluie" in z["resume"]


def test_unknown_codes_are_described():
    for c in (56, 57, 66, 67, 77, 85, 86):
        assert w.describe(c) != "conditions variables"


def test_alerts_are_deterministic():
    d = {"wind_gusts_10m_max": [85], "precipitation_sum": [40], "temperature_2m_max": [36],
         "temperature_2m_min": [-1]}
    a = w.build_alerts(d)
    assert len(a) == 4 and "Rafales jusqu'à 85 km/h" in a


def test_zone_uses_all_cities_not_only_first():
    a = w.parse_city("Antibes", _payload([3] * 24, [0.0] * 24))
    b = w.parse_city("Grasse", _payload([63] * 24, [1.5] * 24))
    c = w.parse_city("Cannes", _payload([63] * 24, [1.5] * 24))
    z = w.summarize_zone([a, b, c])
    assert z["description_dominante"] == "pluie"


def test_no_data_returns_none_and_missing_hourly_falls_back():
    assert w.summarize_zone([]) is None
    p = _payload([0] * 24, [0.0] * 24)
    p["hourly"] = {}
    p["daily"]["precipitation_sum"] = [0.0]
    r = w.parse_city("Valbonne", p)
    assert r["periodes"] == [] and r["description"] == "couvert"  # repli code quotidien, 0 mm -> couvert
