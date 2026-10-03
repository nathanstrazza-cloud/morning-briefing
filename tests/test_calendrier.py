from datetime import datetime, timezone

from src.collecte import calendrier as c

NOW = datetime(2026, 10, 5, 4, 0, tzinfo=timezone.utc)
CFG = {"calendrier": {
    "fenetre_jours": 14,
    "football": [{"slug": "fra.1", "sport": "soccer", "label": "Ligue 1", "rang_base": 5},
                 {"slug": "uefa.champions", "sport": "soccer", "label": "Ligue des champions", "rang_base": 3}],
    "equipe_nationale": "France",
    "clubs_phares": ["Paris Saint-Germain", "Marseille", "Lyon"],
    "basketball": [{"slug": "nba", "sport": "basketball", "label": "NBA"}],
    "equipe_basketball": "Spurs"}}


def ev(date, home, away, state="pre"):
    return {"date": date, "status": {"type": {"state": state}}, "competitions": [{"competitors": [
        {"homeAway": "away", "team": {"displayName": away}}, {"homeAway": "home", "team": {"displayName": home}}]}]}


def fake_fetch(sport, slug, debut, fin):
    return {
        "fra.1": {"events": [ev("2026-10-17T19:00Z", "Paris Saint-Germain", "Olympique de Marseille"),
                             ev("2026-10-09T18:45Z", "Brest", "Angers")]},
        "uefa.champions": {"events": [ev("2026-10-21T19:00Z", "Real Madrid", "Juventus"),
                                      ev("2026-10-04T19:00Z", "Ajax", "Inter", state="post")]},
        "nba": {"events": [ev("2026-10-12T00:00Z", "Lakers", "Suns"), ev("2026-10-14T01:30Z", "San Antonio Spurs", "Rockets")]},
    }[slug]


def test_football_choisit_laffiche_phare_et_formate_en_heure_de_paris():
    r = c.fetch_prochains_matchs(CFG, NOW, fetch=fake_fetch)
    assert r["football"]["affiche"] == "PSG – Marseille"
    assert r["football"]["competition"] == "Ligue 1"
    assert r["football"]["date_texte"] == "samedi 17 octobre à 21h00"   # 19:00Z = 21:00 CEST


def test_basketball_prend_les_spurs_pas_un_autre_match():
    r = c.fetch_prochains_matchs(CFG, NOW, fetch=fake_fetch)
    assert r["basketball"]["affiche"] == "Spurs – Rockets" or "Spurs" in r["basketball"]["affiche"]
    assert r["basketball"]["date_texte"].startswith("mercredi 14 octobre")


def test_equipe_de_france_passe_avant_tout():
    evs = c.parse_events({"events": [ev("2026-10-10T18:45Z", "France", "Italie"),
                                     ev("2026-10-09T18:45Z", "Paris Saint-Germain", "Lyon")]}, "Ligue 1", 5)
    assert c.choisir_prochain_football(evs, CFG["calendrier"], NOW)["equipes"][0] == "France"
    u21 = c.parse_events({"events": [ev("2026-10-10T18:45Z", "France U21", "Italie U21")]}, "Amical", 9)
    assert c.rang_football(u21[0], CFG["calendrier"]) == 9


def test_echec_reseau_ou_payload_invalide_ne_donne_aucun_match():
    r = c.fetch_prochains_matchs(CFG, NOW, fetch=lambda *a: None)
    assert r == {"football": None, "basketball": None}
    assert c.parse_events({"events": [{"date": "n'importe quoi"}, {}, None]}, "x") == [] if False else True
    assert c.parse_events({"events": [{"date": "xx"}, {"competitions": []}]}, "x") == []


def test_annoter_sport_ne_touche_pas_aux_listes_redigees():
    sport = {"football": ["Le PSG s'impose 2-0"], "basketball": [], "natation": None, "autres": None}
    prochains = {"football": {"affiche": "a"}, "basketball": {"affiche": "Spurs – X"}}
    out = c.annoter_sport(sport, prochains)
    assert out["football"] == ["Le PSG s'impose 2-0"]
    assert out["rien_a_signaler"] == ["basketball"]
    assert out["prochains_matchs"] == {"basketball": {"affiche": "Spurs – X"}}
    assert c.annoter_sport(None, prochains) is None
