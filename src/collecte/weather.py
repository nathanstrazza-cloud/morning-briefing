"""Collecte météo via Open-Meteo (gratuit, sans clé API) pour Antibes/Cannes/Valbonne/Grasse
(cf. cahier §8). Un bulletin très court est attendu, pas un rapport détaillé.
"""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger("morning_briefing.collecte.weather")

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Codes météo Open-Meteo (WMO) -> description française courte.
WMO_CODES = {
    0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux", 3: "couvert",
    45: "brouillard", 48: "brouillard givrant",
    51: "bruine légère", 53: "bruine", 55: "bruine forte",
    61: "pluie légère", 63: "pluie", 65: "forte pluie",
    71: "neige légère", 73: "neige", 75: "forte neige",
    80: "averses légères", 81: "averses", 82: "fortes averses",
    95: "orage", 96: "orage avec grêle", 99: "orage violent avec grêle",
}


def fetch_city_weather(name: str, lat: float, lon: float, timeout: int = 10) -> dict | None:
    """Retourne None en cas d'échec (cf. cahier §21 : ne jamais inventer la météo)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,precipitation,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max",
        "timezone": "Europe/Paris",
        "forecast_days": 1,
    }
    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})
        daily = data.get("daily", {})

        code = current.get("weather_code")
        return {
            "ville": name,
            "temperature_actuelle": current.get("temperature_2m"),
            "temperature_max": (daily.get("temperature_2m_max") or [None])[0],
            "temperature_min": (daily.get("temperature_2m_min") or [None])[0],
            "precipitation_mm": current.get("precipitation"),
            "probabilite_pluie_pct": (daily.get("precipitation_probability_max") or [None])[0],
            "vent_kmh": current.get("wind_speed_10m"),
            "vent_max_kmh": (daily.get("wind_speed_10m_max") or [None])[0],
            "description": WMO_CODES.get(code, "conditions variables"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Échec récupération météo pour %s: %s", name, exc)
        return None


def fetch_all_weather(config: dict) -> list[dict]:
    villes = config.get("meteo", {}).get("villes", [])
    resultats = []
    for v in villes:
        w = fetch_city_weather(v["name"], v["lat"], v["lon"])
        if w:
            resultats.append(w)
    logger.info("Météo collectée pour %d/%d villes", len(resultats), len(villes))
    return resultats


def summarize_zone(weather_list: list[dict]) -> dict | None:
    """Agrège les 4 villes en un résumé rapide unique pour la zone (cf. cahier §8:
    'comprendre la météo de la journée en quelques secondes').

    Retourne None si aucune donnée n'est disponible (ne pas inventer, cf. cahier §21).
    """
    if not weather_list:
        return None

    temps_max = [w["temperature_max"] for w in weather_list if w["temperature_max"] is not None]
    temps_min = [w["temperature_min"] for w in weather_list if w["temperature_min"] is not None]
    pluies = [w["probabilite_pluie_pct"] for w in weather_list if w["probabilite_pluie_pct"] is not None]
    vents = [w["vent_max_kmh"] for w in weather_list if w["vent_max_kmh"] is not None]

    return {
        "villes_detail": weather_list,
        "temperature_max_zone": max(temps_max) if temps_max else None,
        "temperature_min_zone": min(temps_min) if temps_min else None,
        "probabilite_pluie_max_pct": max(pluies) if pluies else None,
        "vent_max_kmh": max(vents) if vents else None,
        "description_dominante": weather_list[0]["description"],
    }
