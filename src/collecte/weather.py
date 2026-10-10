"""Collecte météo via Open-Meteo (gratuit, sans clé API) pour Antibes/Cannes/Valbonne/Grasse
(cf. cahier §8). Un bulletin très court est attendu, pas un rapport détaillé.

Correctifs du 03/10/2026 (point 8 de ANALYSE_RUN_2026-10-01.md) :
- la description ne vient plus du code météo INSTANTANÉ de 06h10 (qui donnait « bruine forte »
  avec 0 mm de pluie) mais des prévisions HORAIRES de la journée ;
- évolution dans la journée (matin / après-midi / soir) exigée par le cahier §8 ;
- description de zone = agrégat des 4 villes (et plus Antibes seule) ;
- codes WMO manquants ajoutés (56/57, 66/67, 77, 85/86) ;
- un code « pluie/bruine » avec un cumul horaire quasi nul est ramené à « couvert » ;
- alertes déterministes (rafales, cumul de pluie, orage, chaleur, gel), jamais inventées.
Toute la logique de calcul est dans des fonctions pures testables sans réseau.

Correctifs du 10/10/2026 (point 3 de ANALYSE_RUN_2026-10-08.md) : « ciel dégagé » s'affichait avec 88-93 % de pluie
(maximum des probabilités horaires = un pic isolé) et Antibes affichait 10 mm (pluie tombée la NUIT, avant 6h) alors
que les périodes affichées donnaient 0-0,1 mm. Maintenant :
- la probabilité d'une période n'est le MAXIMUM horaire que si la pluie est étayée (cumul >= 0,2 mm ou code de
  précipitations effectif sur la période) ; sinon c'est la MÉDIANE des probabilités horaires ;
- la probabilité et le cumul de la JOURNÉE sont calculés sur la fenêtre affichée (6h-24h, mêmes heures que les
  périodes) avec la même règle : plus de somme/maximum quotidien incluant la nuit déjà passée ;
- l'alerte « pluie abondante » porte sur ce même cumul.
"""
from __future__ import annotations

import logging
import statistics
from collections import Counter

import requests

logger = logging.getLogger("morning_briefing.collecte.weather")

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Codes météo Open-Meteo (WMO) -> description française courte.
WMO_CODES = {
    0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux", 3: "couvert",
    45: "brouillard", 48: "brouillard givrant",
    51: "bruine légère", 53: "bruine", 55: "bruine forte",
    56: "bruine verglaçante légère", 57: "bruine verglaçante",
    61: "pluie légère", 63: "pluie", 65: "forte pluie",
    66: "pluie verglaçante légère", 67: "pluie verglaçante",
    71: "neige légère", 73: "neige", 75: "forte neige", 77: "grains de neige",
    80: "averses légères", 81: "averses", 82: "fortes averses",
    85: "averses de neige légères", 86: "fortes averses de neige",
    95: "orage", 96: "orage avec grêle", 99: "orage violent avec grêle",
}

# Codes avec précipitations ; ordre = gravité croissante (utilisé pour choisir le pire).
PRECIP_CODES = [51, 53, 56, 55, 57, 61, 80, 66, 63, 71, 77, 85, 81, 67, 73, 65, 82, 75, 86, 95, 96, 99]
SEVERITY = {c: i for i, c in enumerate(PRECIP_CODES)}
THUNDER_CODES = {95, 96, 99}

# Un code « précipitations » avec moins de ce cumul horaire (mm) est considéré comme ciel couvert.
MIN_HOURLY_PRECIP_MM = 0.2
# Cumul d'une période (mm) à partir duquel on retient le pire code de précipitations plutôt que le plus fréquent.
PERIOD_PRECIP_MM = 1.0

# Cumul (mm) à partir duquel une pluie est « étayée » pour afficher la probabilité maximale (sinon : médiane).
PLUIE_ETAYEE_MM = 0.2
FENETRE_AFFICHEE = (6, 24)   # heures couvertes par les périodes Matin / Après-midi / Soir

PERIODES = [("Matin", 6, 12), ("Après-midi", 12, 18), ("Soir", 18, 24)]

SEUIL_RAFALES_KMH = 60
SEUIL_PLUIE_JOUR_MM = 20
SEUIL_CHALEUR_C = 35
SEUIL_GEL_C = 0


def describe(code) -> str:
    return WMO_CODES.get(code, "conditions variables")


def _num(v):
    return v if isinstance(v, (int, float)) else None


def _hour(ts: str) -> int | None:
    try:
        return int(ts[11:13])
    except (ValueError, TypeError, IndexError):
        return None


def effective_code(code, precip_mm) -> int | None:
    """Ramène à « couvert » (3) un code de précipitations sans pluie mesurable (hors orage)."""
    if code is None:
        return None
    if code in SEVERITY and code not in THUNDER_CODES:
        p = _num(precip_mm)
        if p is not None and p < MIN_HOURLY_PRECIP_MM:
            return 3
    return code


def dominant_code(codes: list[int], precip_total_mm: float) -> int | None:
    """Code représentatif d'une période : le plus fréquent ; si la période est vraiment arrosée
    (cumul >= PERIOD_PRECIP_MM) ou orageuse, le plus grave des codes de précipitations."""
    codes = [c for c in codes if c is not None]
    if not codes:
        return None
    precip = [c for c in codes if c in SEVERITY]
    if precip and (precip_total_mm >= PERIOD_PRECIP_MM or any(c in THUNDER_CODES for c in precip)):
        return max(precip, key=lambda c: SEVERITY[c])
    return Counter(codes).most_common(1)[0][0]


def rain_probability(probs: list[float], codes_eff: list, precip_total_mm: float) -> int | None:
    """Probabilité de pluie à AFFICHER pour une plage horaire, cohérente avec les mm et le ciel.
    Pluie étayée (cumul >= PLUIE_ETAYEE_MM ou code de précipitations effectif) -> maximum horaire ;
    sinon -> médiane (un pic isolé de probabilité sans eau prévue ne doit pas apparaître comme « 93 % »)."""
    probs = [p for p in probs if _num(p) is not None]
    if not probs:
        return None
    etayee = precip_total_mm >= PLUIE_ETAYEE_MM or any(c in SEVERITY for c in codes_eff if c is not None)
    return round(max(probs)) if etayee else round(statistics.median(probs))


def build_periods(hourly: dict) -> list[dict]:
    """Découpe les prévisions horaires en matin / après-midi / soir. Liste vide si pas de données."""
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    probs = hourly.get("precipitation_probability") or []
    precs = hourly.get("precipitation") or []
    codes = hourly.get("weather_code") or []
    winds = hourly.get("wind_speed_10m") or []
    out = []
    for label, h0, h1 in PERIODES:
        idx = [i for i, t in enumerate(times) if (h := _hour(t)) is not None and h0 <= h < h1]
        if not idx:
            continue

        def col(arr):
            return [arr[i] for i in idx if i < len(arr) and _num(arr[i]) is not None]

        t, p, pr, w = col(temps), col(probs), col(precs), col(winds)
        eff = [effective_code(codes[i], precs[i] if i < len(precs) else None)
               for i in idx if i < len(codes)]
        code = dominant_code(eff, sum(pr))
        out.append({
            "label": label,
            "temperature_min": round(min(t), 1) if t else None,
            "temperature_max": round(max(t), 1) if t else None,
            "probabilite_pluie_pct": rain_probability(p, eff, sum(pr)),
            "precipitation_mm": round(sum(pr), 1) if pr else None,
            "vent_max_kmh": round(max(w)) if w else None,
            "weather_code": code,
            "description": describe(code) if code is not None else None,
        })
    return out


def window_rain(hourly: dict) -> tuple[float | None, int | None]:
    """(cumul mm, probabilité à afficher) sur la fenêtre affichée 6h-24h. (None, None) sans horaire exploitable."""
    h0, h1 = FENETRE_AFFICHEE
    times = hourly.get("time") or []
    precs, probs, codes = (hourly.get(k) or [] for k in ("precipitation", "precipitation_probability", "weather_code"))
    idx = [i for i, t in enumerate(times) if (h := _hour(t)) is not None and h0 <= h < h1]
    pr = [precs[i] for i in idx if i < len(precs) and _num(precs[i]) is not None]
    if not pr:
        return None, None
    pb = [probs[i] for i in idx if i < len(probs)]
    eff = [effective_code(codes[i], precs[i] if i < len(precs) else None) for i in idx if i < len(codes)]
    total = sum(pr)
    return round(total, 1), rain_probability(pb, eff, total)


def build_alerts(daily: dict, pluie_fenetre_mm: float | None = None) -> list[str]:
    """Alertes déterministes à partir des valeurs mesurées/prévues du jour.
    `pluie_fenetre_mm` : cumul sur la fenêtre affichée (6h-24h) ; à défaut, somme quotidienne (nuit incluse)."""
    alertes = []

    def first(key):
        return _num((daily.get(key) or [None])[0])

    rafales, pluie, tmax, tmin = first("wind_gusts_10m_max"), first("precipitation_sum"), \
        first("temperature_2m_max"), first("temperature_2m_min")
    if rafales is not None and rafales >= SEUIL_RAFALES_KMH:
        alertes.append(f"Rafales jusqu'à {round(rafales)} km/h")
    if pluie_fenetre_mm is not None:
        pluie = pluie_fenetre_mm
    if pluie is not None and pluie >= SEUIL_PLUIE_JOUR_MM:
        alertes.append(f"Pluie abondante ({round(pluie)} mm sur la journée)")
    if tmax is not None and tmax >= SEUIL_CHALEUR_C:
        alertes.append(f"Forte chaleur ({round(tmax)} °C)")
    if tmin is not None and tmin <= SEUIL_GEL_C:
        alertes.append(f"Gel ({round(tmin)} °C)")
    return alertes


def parse_city(name: str, data: dict) -> dict:
    """Transforme la réponse Open-Meteo d'une ville en dict de bulletin (fonction pure)."""
    current = data.get("current", {}) or {}
    daily = data.get("daily", {}) or {}
    hourly = data.get("hourly", {}) or {}

    def d0(key):
        return (daily.get(key) or [None])[0]

    periodes = build_periods(hourly)
    # Description du jour : sur les heures 7h-22h, avec les mêmes règles que les périodes.
    codes_jour, pluie_jour = [], 0.0
    for i, ts in enumerate(hourly.get("time") or []):
        h = _hour(ts)
        if h is None or not (7 <= h < 22):
            continue
        prec = (hourly.get("precipitation") or [None] * (i + 1))[i] if i < len(hourly.get("precipitation") or []) else None
        code = (hourly.get("weather_code") or [None] * (i + 1))[i] if i < len(hourly.get("weather_code") or []) else None
        codes_jour.append(effective_code(code, prec))
        pluie_jour += _num(prec) or 0.0
    code_jour = dominant_code(codes_jour, pluie_jour)
    if code_jour is None:  # pas d'horaire : repli sur le code quotidien (pire cas de la journée)
        code_jour = effective_code(d0("weather_code"), d0("precipitation_sum"))

    mm_fenetre, prob_fenetre = window_rain(hourly)
    return {
        "ville": name,
        "temperature_actuelle": current.get("temperature_2m"),
        "temperature_max": d0("temperature_2m_max"),
        "temperature_min": d0("temperature_2m_min"),
        "precipitation_mm": mm_fenetre if mm_fenetre is not None else d0("precipitation_sum"),
        "probabilite_pluie_pct": prob_fenetre if prob_fenetre is not None else d0("precipitation_probability_max"),
        "vent_kmh": current.get("wind_speed_10m"),
        "vent_max_kmh": d0("wind_speed_10m_max"),
        "rafales_max_kmh": d0("wind_gusts_10m_max"),
        "weather_code": code_jour,
        "description": describe(code_jour) if code_jour is not None else "conditions variables",
        "periodes": periodes,
        "alertes": build_alerts(daily, mm_fenetre),
    }


def fetch_city_weather(name: str, lat: float, lon: float, timeout: int = 10) -> dict | None:
    """Retourne None en cas d'échec (cf. cahier §21 : ne jamais inventer la météo)."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,precipitation,weather_code,wind_speed_10m",
        "daily": ("weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,"
                  "precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max"),
        "hourly": "temperature_2m,precipitation_probability,precipitation,weather_code,wind_speed_10m",
        "timezone": "Europe/Paris",
        "forecast_days": 1,
    }
    try:
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        return parse_city(name, resp.json())
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


def _zone_code(codes: list[int]) -> int | None:
    codes = [c for c in codes if c is not None]
    if not codes:
        return None
    precip = [c for c in codes if c in SEVERITY]
    # Si au moins la moitié des villes ont des précipitations, on retient le pire de ces codes.
    if precip and len(precip) * 2 >= len(codes):
        return max(precip, key=lambda c: SEVERITY[c])
    non_precip = [c for c in codes if c not in SEVERITY]
    return Counter(non_precip or codes).most_common(1)[0][0]


def _zone_periods(weather_list: list[dict]) -> list[dict]:
    out = []
    for label, _, _ in PERIODES:
        ps = [p for w in weather_list for p in (w.get("periodes") or []) if p["label"] == label]
        if not ps:
            continue
        tmins = [p["temperature_min"] for p in ps if p["temperature_min"] is not None]
        tmaxs = [p["temperature_max"] for p in ps if p["temperature_max"] is not None]
        probs = [p["probabilite_pluie_pct"] for p in ps if p["probabilite_pluie_pct"] is not None]
        mms = [p["precipitation_mm"] for p in ps if p["precipitation_mm"] is not None]
        winds = [p["vent_max_kmh"] for p in ps if p["vent_max_kmh"] is not None]
        code = _zone_code([p["weather_code"] for p in ps])
        out.append({
            "label": label,
            "temperature_min": min(tmins) if tmins else None,
            "temperature_max": max(tmaxs) if tmaxs else None,
            "probabilite_pluie_pct": max(probs) if probs else None,
            "precipitation_mm": max(mms) if mms else None,
            "vent_max_kmh": max(winds) if winds else None,
            "weather_code": code,
            "description": describe(code) if code is not None else None,
        })
    return out


def _resume(periodes: list[dict], tmin, tmax, pluie_pct) -> str | None:
    """Phrase courte et factuelle construite par le code (aucun LLM)."""
    descs = [(p["label"].lower(), p["description"]) for p in periodes if p.get("description")]
    if not descs:
        return None
    # Regroupe les périodes consécutives identiques : « Couvert toute la journée » / « Couvert le matin, pluie le soir ».
    if len({d for _, d in descs}) == 1:
        texte = f"{descs[0][1].capitalize()} toute la journée"
    else:
        morceaux = []
        for label, d in descs:
            prep = {"matin": "le matin", "après-midi": "l'après-midi", "soir": "le soir"}[label]
            morceaux.append(f"{d} {prep}")
        texte = ", ".join(morceaux)
        texte = texte[0].upper() + texte[1:]
    if tmin is not None and tmax is not None:
        texte += f", de {round(tmin)}° à {round(tmax)}°"
    return texte + "."


def summarize_zone(weather_list: list[dict]) -> dict | None:
    """Agrège les 4 villes en un résumé rapide unique pour la zone (cf. cahier §8:
    'comprendre la météo de la journée en quelques secondes').

    Retourne None si aucune donnée n'est disponible (ne pas inventer, cf. cahier §21).
    Champs historiques conservés (compatibilité frontend) ; ajoutés : `periodes`, `alertes`, `resume`.
    """
    if not weather_list:
        return None

    temps_max = [w["temperature_max"] for w in weather_list if w.get("temperature_max") is not None]
    temps_min = [w["temperature_min"] for w in weather_list if w.get("temperature_min") is not None]
    pluies = [w["probabilite_pluie_pct"] for w in weather_list if w.get("probabilite_pluie_pct") is not None]
    vents = [w["vent_max_kmh"] for w in weather_list if w.get("vent_max_kmh") is not None]
    codes = [w.get("weather_code") for w in weather_list]
    code_zone = _zone_code(codes)
    periodes = _zone_periods(weather_list)

    alertes = []
    for w in weather_list:
        for a in w.get("alertes") or []:
            if a not in alertes:
                alertes.append(a)

    tmin = min(temps_min) if temps_min else None
    tmax = max(temps_max) if temps_max else None
    pluie_max = max(pluies) if pluies else None
    return {
        "villes_detail": weather_list,
        "temperature_max_zone": tmax,
        "temperature_min_zone": tmin,
        "probabilite_pluie_max_pct": pluie_max,
        "vent_max_kmh": max(vents) if vents else None,
        "description_dominante": describe(code_zone) if code_zone is not None else weather_list[0]["description"],
        "periodes": periodes,
        "alertes": alertes,
        "resume": _resume(periodes, tmin, tmax, pluie_max),
    }
