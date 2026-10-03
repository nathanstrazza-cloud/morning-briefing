"""Calendrier sportif : « prochain match intéressant » (décision de l'utilisateur du 01/10/2026).

Quand le football ou le basketball n'ont rien de notable, le briefing le dit et indique le prochain
match à suivre. Source : API publique ESPN (gratuite, sans clé). Toute la logique (analyse de la
réponse, choix du match, formatage de la date) est dans des fonctions pures testées sans réseau ;
seul `_fetch_scoreboard` fait de l'I/O. En cas d'échec -> aucune donnée, JAMAIS un match inventé.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger("morning_briefing.collecte.calendrier")

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/{sport}/{slug}/scoreboard"
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]

# Noms d'équipes ESPN -> forme courte française pour l'affichage.
NOMS_COURTS = {
    "paris saint-germain": "PSG", "paris saint germain": "PSG", "olympique de marseille": "Marseille",
    "olympique lyonnais": "Lyon", "as monaco": "Monaco", "lille osc": "Lille", "ogc nice": "Nice",
    "rc lens": "Lens", "stade rennais": "Rennes", "san antonio spurs": "Spurs",
}


def _nom_court(nom: str) -> str:
    return NOMS_COURTS.get(nom.strip().lower(), nom.strip())


def parse_events(data: dict, label: str, rang_base: int = 9) -> list[dict]:
    """Extrait les matchs À VENIR d'une réponse ESPN. Tolérant : une entrée mal formée est ignorée."""
    out = []
    for ev in (data or {}).get("events") or []:
        try:
            comp = (ev.get("competitions") or [{}])[0]
            state = (((ev.get("status") or comp.get("status") or {}).get("type") or {}).get("state") or "")
            if state and state != "pre":
                continue
            date = datetime.fromisoformat(str(ev["date"]).replace("Z", "+00:00"))
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            equipes = []
            for c in comp.get("competitors") or []:
                nom = ((c.get("team") or {}).get("displayName") or (c.get("team") or {}).get("name") or "").strip()
                if nom:
                    equipes.append((c.get("homeAway") or "", nom))
            if len(equipes) != 2:
                continue
            equipes.sort(key=lambda t: 0 if t[0] == "home" else 1)  # domicile en premier
            out.append({"date_utc": date.astimezone(timezone.utc), "equipes": [n for _, n in equipes],
                        "competition": label, "rang_base": rang_base})
        except Exception:  # noqa: BLE001
            continue
    return out


def date_en_francais(date_utc: datetime) -> str:
    """« samedi 17 octobre à 21h00 » en heure de Paris."""
    try:
        from zoneinfo import ZoneInfo
        d = date_utc.astimezone(ZoneInfo("Europe/Paris"))
    except Exception:  # noqa: BLE001
        d = date_utc
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} à {d.hour}h{d.minute:02d}"


def _contient(equipes: list[str], mot: str) -> bool:
    return any(mot.lower() in e.lower() for e in equipes)


def rang_football(match: dict, cfg: dict) -> int:
    """Plus petit = plus intéressant. 0 équipe de France ; 1 affiche entre deux clubs phares ;
    sinon rang de la compétition, amélioré d'un cran si un club phare joue."""
    equipes = match["equipes"]
    nationale = cfg.get("equipe_nationale", "France").lower()
    if any(e.strip().lower() == nationale for e in equipes):  # sélection A uniquement (pas « France U21 »)
        return 0
    phares = cfg.get("clubs_phares") or []
    nb = sum(1 for e in equipes if any(p.lower() in e.lower() for p in phares))
    if nb >= 2:
        return 1
    rang = match.get("rang_base", 9)
    return max(2, rang - 1) if nb == 1 else rang


def choisir_prochain_football(matchs: list[dict], cfg: dict, maintenant: datetime) -> dict | None:
    futurs = [m for m in matchs if m["date_utc"] > maintenant]
    if not futurs:
        return None
    return min(futurs, key=lambda m: (rang_football(m, cfg), m["date_utc"]))


def choisir_prochain_basketball(matchs: list[dict], cfg: dict, maintenant: datetime) -> dict | None:
    mot = cfg.get("equipe_basketball", "Spurs")
    futurs = [m for m in matchs if m["date_utc"] > maintenant and _contient(m["equipes"], mot)]
    return min(futurs, key=lambda m: m["date_utc"]) if futurs else None


def formater(match: dict | None) -> dict | None:
    if not match:
        return None
    a, b = (_nom_court(e) for e in match["equipes"])
    return {"affiche": f"{a} – {b}", "competition": match["competition"],
            "date_iso": match["date_utc"].isoformat(), "date_texte": date_en_francais(match["date_utc"])}


HEADERS = {"User-Agent": "Mozilla/5.0 (morning-briefing)"}
MAX_EVENEMENTS_SCAN = 12   # le repli jour par jour s'arrête dès que ce nombre de matchs est réuni


def _get(sport: str, slug: str, dates: str, timeout: int) -> dict | None:
    try:
        r = requests.get(ESPN_URL.format(sport=sport, slug=slug), params={"dates": dates}, timeout=timeout,
                         headers=HEADERS)
        if r.status_code >= 400:
            logger.warning("Calendrier: HTTP %s pour %s/%s dates=%s : %s", r.status_code, sport, slug, dates,
                           r.text[:150].replace("\n", " "))
            return None
        return r.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Calendrier: échec %s/%s dates=%s : %s", sport, slug, dates, exc)
        return None


def _fetch_scoreboard(sport: str, slug: str, debut: datetime, fin: datetime, timeout: int = 10) -> dict | None:
    """1) une requête pour toute la plage (AAAAMMJJ-AAAAMMJJ) ; 2) si elle échoue, repli jour par jour
    (une date unique est le format le plus répandu). Retourne {"events": [...]} ou None."""
    data = _get(sport, slug, f"{debut:%Y%m%d}-{fin:%Y%m%d}", timeout)
    if data is not None:
        return data
    events, jour = [], debut
    echecs = 0
    plafond = MAX_EVENEMENTS_SCAN if sport == "soccer" else 10_000   # basket : il faut tout parcourir pour trouver les Spurs
    while jour.date() <= fin.date() and len(events) < plafond:
        d = _get(sport, slug, f"{jour:%Y%m%d}", timeout)
        if d is None:
            echecs += 1
            if echecs >= 3 and not events:       # source manifestement indisponible : on arrête
                return None
        else:
            events += d.get("events") or []
        jour += timedelta(days=1)
    return {"events": events} if events or echecs < 3 else None


def fetch_prochains_matchs(config: dict, maintenant: datetime | None = None, fetch=_fetch_scoreboard) -> dict:
    """{"football": {...}|None, "basketball": {...}|None}. `fetch` injectable pour les tests."""
    cfg = config.get("calendrier") or {}
    maintenant = maintenant or datetime.now(timezone.utc)
    fin = maintenant + timedelta(days=int(cfg.get("fenetre_jours", 14)))
    resultat = {"football": None, "basketball": None}

    foot, basket = [], []
    for comp in cfg.get("football") or []:
        data = fetch(comp["sport"], comp["slug"], maintenant, fin)
        evs = parse_events(data, comp["label"], comp.get("rang_base", 9)) if data else []
        logger.info("Calendrier football %s: %d match(s) à venir", comp["slug"], len(evs))
        foot += evs
    for comp in cfg.get("basketball") or []:
        data = fetch(comp["sport"], comp["slug"], maintenant, fin)
        evs = parse_events(data, comp["label"]) if data else []
        logger.info("Calendrier basketball %s: %d match(s) à venir", comp["slug"], len(evs))
        basket += evs

    resultat["football"] = formater(choisir_prochain_football(foot, cfg, maintenant))
    resultat["basketball"] = formater(choisir_prochain_basketball(basket, cfg, maintenant))
    logger.info("Calendrier: prochain football=%s | prochain basketball=%s",
                (resultat["football"] or {}).get("affiche"), (resultat["basketball"] or {}).get("affiche"))
    return resultat


def annoter_sport(sport: dict | None, prochains: dict) -> dict | None:
    """Ajoute à la section sport `rien_a_signaler` (football/basketball sans contenu) et, pour ceux-là,
    `prochains_matchs`. Ne touche jamais aux listes déjà rédigées. Fonction pure."""
    if sport is None:
        return None
    rien = [c for c in ("football", "basketball") if not sport.get(c)]
    sport["rien_a_signaler"] = rien
    sport["prochains_matchs"] = {c: prochains.get(c) for c in rien}
    return sport
