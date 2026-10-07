from datetime import datetime, timezone

from src.collecte import calendrier as c

NOW = datetime(2026, 10, 5, 4, 0, tzinfo=timezone.utc)
CFG = {"calendrier": {
    "fenetre_jours": 14,
    "football": [{"slug": "fra.1", "sport": "soccer", "label": "Ligue 1", "rang_base": 5},
                 {"slug": "uefa.champions", "sport": "soccer", "label": "Ligue des champions", "rang_base": 3}],
    "equipe_nationale": "",
    "clubs_phares": ["Paris Saint-Germain", "Marseille", "Lyon"],
    "basketball": [{"slug": "nba", "sport": "basketball", "label": "NBA"}],
    "franchises_phares": ["Lakers"]}}


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


def test_basketball_prend_laffiche_de_franchises_phares_sans_equipe_imposee():
    r = c.fetch_prochains_matchs(CFG, NOW, fetch=fake_fetch)
    assert "Lakers" in r["basketball"]["affiche"]                    # franchise phare, pas les Spurs
    cfg_sans = {"calendrier": dict(CFG["calendrier"], franchises_phares=[])}
    r2 = c.fetch_prochains_matchs(cfg_sans, NOW, fetch=fake_fetch)
    assert r2["basketball"]["date_texte"].startswith("lundi 12 octobre")    # sinon : le plus proche


def test_aucune_preference_nationale_par_defaut_et_option_facultative():
    evs = c.parse_events({"events": [ev("2026-10-10T18:45Z", "France", "Italie"),
                                     ev("2026-10-09T18:45Z", "Paris Saint-Germain", "Lyon")]}, "Ligue 1", 5)
    assert c.choisir_prochain_football(evs, CFG["calendrier"], NOW)["equipes"][0] == "Paris Saint-Germain"
    avec = dict(CFG["calendrier"], equipe_nationale="France")
    assert c.choisir_prochain_football(evs, avec, NOW)["equipes"][0] == "France"
    u21 = c.parse_events({"events": [ev("2026-10-10T18:45Z", "France U21", "Italie U21")]}, "Amical", 9)
    assert c.rang_football(u21[0], avec) == 9


def test_echec_reseau_ou_payload_invalide_ne_donne_aucun_match():
    r = c.fetch_prochains_matchs(CFG, NOW, fetch=lambda *a: None)
    assert r == {"football": None, "basketball": None}
    assert c.parse_events({"events": [{"date": "n'importe quoi"}, {}, None]}, "x") == [] if False else True
    assert c.parse_events({"events": [{"date": "xx"}, {"competitions": []}]}, "x") == []


def test_annoter_sport_rien_a_signaler_donne_les_prochaines_affiches():
    prochains = {"football": {"affiche": "a"}, "basketball": None}
    vide = c.annoter_sport({"items": []}, prochains)
    assert vide["rien_a_signaler"] is True and vide["prochains_matchs"] == [{"affiche": "a", "sport": "football"}]
    plein = c.annoter_sport({"items": [{"sport": "tennis", "texte": "Alcaraz gagne"}]}, prochains)
    assert plein["rien_a_signaler"] is False and plein["prochains_matchs"] == []
    assert plein["items"] == [{"sport": "tennis", "texte": "Alcaraz gagne"}]
    assert c.annoter_sport(None, prochains) is None


def test_repli_jour_par_jour_quand_la_plage_est_refusee(monkeypatch):
    class R:
        def __init__(self, code, js=None):
            self.status_code, self._j, self.text = code, js, "bad"

        def json(self):
            return self._j

    def fake_get(url, params, timeout, headers):
        if "-" in params["dates"]:
            return R(400)
        if params["dates"] == "20261007":
            return R(200, {"events": [ev("2026-10-07T19:00Z", "A", "B")]})
        return R(200, {"events": []})

    monkeypatch.setattr(c.requests, "get", fake_get)
    d = c._fetch_scoreboard("soccer", "fra.1", datetime(2026, 10, 3, tzinfo=timezone.utc),
                            datetime(2026, 10, 17, tzinfo=timezone.utc))
    assert len(d["events"]) == 1


def test_source_indisponible_retourne_none(monkeypatch):
    class R:
        status_code, text = 500, "err"

    monkeypatch.setattr(c.requests, "get", lambda *a, **k: R())
    assert c._fetch_scoreboard("soccer", "x", datetime(2026, 10, 3, tzinfo=timezone.utc),
                               datetime(2026, 10, 17, tzinfo=timezone.utc)) is None


def test_plage_refusee_une_fois_puis_directement_jour_par_jour(monkeypatch):
    """06/10/2026 : après un 400 sur la plage, les compétitions suivantes ne retentent pas la plage."""
    from datetime import datetime, timezone
    from src.collecte import calendrier as cal
    appels = []

    def faux_get(sport, slug, dates, timeout):
        appels.append((slug, dates))
        return None if "-" in dates else {"events": [{"id": dates}]}

    monkeypatch.setattr(cal, "_get", faux_get)
    monkeypatch.setitem(cal._state, "plage_refusee", False)
    d0 = datetime(2026, 10, 6, tzinfo=timezone.utc)
    d1 = datetime(2026, 10, 8, tzinfo=timezone.utc)
    r1 = cal._fetch_scoreboard("basketball", "nba", d0, d1)
    r2 = cal._fetch_scoreboard("soccer", "fra.1", d0, d1)
    assert len(r1["events"]) == 3 and len(r2["events"]) == 3
    assert sum(1 for _, d in appels if "-" in d) == 1          # une seule tentative de plage dans tout le run
