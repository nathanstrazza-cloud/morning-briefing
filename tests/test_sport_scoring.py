"""Tests hors réseau du sport généraliste (05/10/2026) : aucune préférence utilisateur."""
from datetime import datetime, timezone

from src.analyse.sport_scoring import detecter_sport, score_sport_event, select_sport
from src.collecte import sports as collecte_sports
from src.generation import sport_format

CFG = {"sport": {"max_par_sport": 2}}


def ev(titre, resume="", n=1, sport=None, jour=5):
    e = {"titre": titre, "resume": resume, "nb_sources": n, "date_publication": datetime(2026, 10, jour, tzinfo=timezone.utc)}
    if sport:
        e["sport"] = sport
    return e


def test_detection_du_sport_par_indice_puis_par_mots_cles():
    assert detecter_sport("x", "", "Tennis") == "tennis"
    assert detecter_sport("Sinner s'impose à Wimbledon") == "tennis"
    assert detecter_sport("Les Lakers battent les Celtics en NBA") == "basketball"
    assert detecter_sport("Verstappen gagne le Grand Prix") == "formule 1"
    assert detecter_sport("Un sport inconnu du grand public") == "autres"


def test_aucune_preference_equipe_ni_pays():
    spurs = score_sport_event(ev("Les Spurs s'imposent face aux Rockets en NBA"))
    lakers = score_sport_event(ev("Les Lakers s'imposent face aux Rockets en NBA"))
    assert spurs == lakers
    fr = score_sport_event(ev("La France bat l'Italie en Six Nations"))
    it = score_sport_event(ev("L'Italie bat la France en Six Nations"))
    assert fr == it


def test_pas_de_penalite_feminine_ni_de_perimetre_fige():
    assert score_sport_event(ev("Les Valkyries se qualifient pour la finale de la WNBA")) >= 5
    assert score_sport_event(ev("Sinner remporte le titre à Wimbledon")) >= 7
    assert score_sport_event(ev("Verstappen remporte le Grand Prix, record battu")) >= 7


def test_anecdotes_ecartees():
    assert score_sport_event(ev("Une chanson saluant Zidane a cartonné sur YouTube")) < 5
    assert score_sport_event(ev("Interview : le portrait d'un nageur")) < 5


def test_selection_diversifiee_entre_sports():
    foot = [ev(f"Le club {i} bat l'équipe adverse en Ligue 1", n=2, sport="football") for i in range(5)]
    tennis = [ev("Alcaraz remporte le titre à Roland-Garros", sport="tennis")]
    out = select_sport(foot + tennis, 4, CFG)
    assert len(out["football"]) == 2                       # plafond par sport
    assert len(out["tennis"]) == 1
    assert sum(len(v) for v in out.values()) == 3


def test_ancien_format_dict_accepte_et_vide_si_rien_de_pertinent():
    out = select_sport({"football": [ev("Chanson sur Zidane YouTube")]}, 4, CFG)
    assert out == {}


def test_departage_par_sources_puis_fraicheur():
    a = ev("Victoire en finale de la Coupe du monde", sport="rugby", jour=3)
    b = ev("Victoire en finale de la Coupe du monde", sport="golf", jour=4)
    out = select_sport([a, b], 1, CFG)
    assert list(out) == ["golf"]


def test_collecte_taggue_chaque_article_sans_filtre_pays(monkeypatch):
    def fake_fetch(url, name, cat, diagnostics=None):
        return [ev("Sinner gagne à Wimbledon") | {"source": name, "url": "u"},
                ev("Le Japon bat le Brésil en volley") | {"source": name, "url": "u"}]
    monkeypatch.setattr(collecte_sports, "fetch_feed", fake_fetch)
    cfg = {"sport": {"sources": [{"name": "Gen", "url": "x"}, {"name": "Hand", "url": "y", "sport": "handball"}]}}
    items = collecte_sports.fetch_sport(cfg)
    assert [i["sport"] for i in items] == ["tennis", "volley-ball", "handball", "handball"]


def test_format_sport_repli_et_normalisation():
    events = {"tennis": [{"titre": "Alcaraz gagne"}], "golf": [{"titre": "McIlroy gagne"}]}
    assert sport_format.depuis_evenements(events) == {"items": [{"sport": "tennis", "texte": "Alcaraz gagne"},
                                                                {"sport": "golf", "texte": "McIlroy gagne"}]}
    llm = {"items": [{"sport": "Tennis", "texte": "Alcaraz s'impose."}, {"sport": "golf", "texte": ""}]}
    assert sport_format.normaliser(llm, events)["items"] == [{"sport": "tennis", "texte": "Alcaraz s'impose."}]
    ancien = {"football": ["Le PSG gagne"], "natation": None}
    assert sport_format.normaliser(ancien, events)["items"][0] == {"sport": "football", "texte": "Le PSG gagne"}
    assert sport_format.normaliser("n'importe quoi", events) == sport_format.depuis_evenements(events)
    trop = {"items": [{"sport": "a", "texte": str(i)} for i in range(9)]}
    assert len(sport_format.normaliser(trop, events)["items"]) == 2   # jamais plus que les événements retenus
