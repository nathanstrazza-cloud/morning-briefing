"""Scoring d'actualité (révision du 05/10/2026) : cas réels du run du 05/10 (ANALYSE_RUN_2026-10-05.md)."""
from datetime import datetime, timedelta

from src.analyse.scoring import score_event, score_events


def ev(titre, resume="", n=1, date=None):
    return {"titre": titre, "resume": resume, "nb_sources": n, "date_publication": date}


def test_deces_ecrivain_nest_plus_majeur():
    assert score_event(ev("Cheikh Hamidou Kane, écrivain sénégalais, est mort à l’âge de 98 ans", n=2)) < 5


def test_sous_chaine_ne_compte_pas():
    # « Mortier » ne contient plus « mort », « emploi » ne contient plus « loi »
    assert score_event(ev("Le chef Mortier ouvre un restaurant à l'emploi")) < 5


def test_election_et_guerre_restent_majeures():
    assert score_event(ev("Présidentielle au Brésil : Flavio Bolsonaro frôle la victoire dès le premier tour")) >= 9
    assert score_event(ev("Guerre en Ukraine : la Russie va intensifier ses frappes", n=2)) >= 9


def test_fait_divers_et_guerre_figuree():
    assert score_event(ev("Quand le conflit de voisinage vire à la guerre ouverte", "un couple abattu par un voisin")) < 5


def test_tribune_collective_et_interview_penalisees():
    assert score_event(ev("La Palestine, un an après le cessez-le-feu : pourquoi aucune action de l’UE ? par 500 anciens ministres")) < 5
    assert score_event(ev("Michael I. Jordan sur l’IA : « la superintelligence relève de la science-fiction »", "entretien")) < 5


def test_un_malus_ne_sort_pas_un_theme_majeur():
    assert score_event(ev("Guerre en Ukraine : entretien avec un général")) >= 5


def test_resultat_devant_avant_scrutin_a_egalite_de_theme():
    resultat = ev("Présidentielle au Brésil : Lula largement devant au premier tour")
    avant = ev("Au Brésil, une élection présidentielle sous haute tension")
    assert score_event(resultat) > score_event(avant)


def test_tri_departage_par_sources_puis_fraicheur():
    t = datetime(2026, 10, 5, 6, 0)
    vieux = ev("Guerre au Soudan : combats à El-Facher", n=1, date=t - timedelta(hours=20))
    recent = ev("Guerre au Yémen : offensive sur Taëz", n=1, date=t)
    multi = ev("Guerre en Ukraine : frappes sur Kiev", n=3, date=t - timedelta(hours=30))
    out = score_events([vieux, recent, multi])
    assert [e["titre"] for e in out][0].startswith("Guerre en Ukraine")      # plus de sources
    assert out[1] is recent and out[2] is vieux                              # à égalité : le plus récent d'abord
