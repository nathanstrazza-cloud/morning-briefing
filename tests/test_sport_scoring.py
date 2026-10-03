"""Tests hors réseau du scoring/sélection sport (03/10/2026)."""
from src.analyse.sport_scoring import score_sport_event, select_sport

CFG = {"sport": {"equipes_prioritaires": {"basketball": ["San Antonio Spurs", "Spurs"]}}}


def ev(titre, resume="", n=1):
    return {"titre": titre, "resume": resume, "nb_sources": n}


def test_foot_feminin_et_anecdotes_ecartes():
    assert score_sport_event(ev("Le Paris FC tient tête à Arsenal en Ligue des champions"), "football", CFG) < 5
    assert score_sport_event(ev("Une chanson saluant Zidane a cartonné sur YouTube"), "football", CFG) < 5
    assert score_sport_event(ev("Démission de la cheffe de délégation de l'Italie aux JO"), "football", CFG) < 5


def test_match_masculin_ligue_des_champions_retenu():
    assert score_sport_event(ev("Le PSG bat Barcelone en Ligue des champions"), "football", CFG) >= 7


def test_spurs_ont_bonus_meme_sans_flag_equipe_prioritaire():
    assert score_sport_event(ev("Wembanyama brille, les Spurs s'imposent en pré-saison NBA"), "basketball", CFG) >= 8


def test_natation_hors_competition_ecartee():
    assert score_sport_event(ev("Un nageur raconte son quotidien"), "natation", CFG) < 5
    assert score_sport_event(ev("Mondiaux de natation : record du monde"), "natation", CFG) >= 5


def test_selection_garantit_basket_malgre_foot_abondant():
    foot = [ev(f"Le PSG bat l'équipe {i} en Ligue 1", n=2) for i in range(5)]
    basket = [ev("Les Spurs s'imposent face aux Lakers en NBA")]
    out = select_sport({"football": foot, "basketball": basket, "natation": [], "autres": []}, 4, CFG)
    assert len(out["basketball"]) == 1
    assert sum(len(v) for v in out.values()) == 4


def test_rien_de_pertinent_donne_listes_vides():
    out = select_sport({"football": [ev("Chanson sur Zidane YouTube")], "basketball": [], "natation": [], "autres": []}, 4, CFG)
    assert all(not v for v in out.values())
