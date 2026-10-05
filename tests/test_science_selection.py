"""Sélection du mode science (05/10/2026) : cas réel « Floride / vaccination » du Monde Sciences."""
from src.generation.briefing_generator import decouverte_qualifiee, select_science_topic


def ev(titre, resume, sources=("Le Monde Sciences",)):
    return {"titre": titre, "resume": resume, "url_principale": "u", "score": 9,
            "sources": [{"nom": s, "url": "u"} for s in sources], "nb_sources": len(sources)}


FLORIDE = ev("Et si la Floride arrêtait de vacciner les enfants contre la rougeole ?",
             "Un modèle de simulation estime les conséquences d'un arrêt de la vaccination obligatoire dans cet État américain, "
             "au moment où les autorités locales envisagent de supprimer cette obligation pour les écoles. " * 1)
ETUDE_SOLIDE = ev("Des chercheurs identifient une protéine clé de la résistance aux antibiotiques",
                  "Une étude publiée dans Nature par des chercheurs de l'Institut Pasteur décrit comment une protéine permet à des bactéries "
                  "de survivre aux antibiotiques ; l'équipe a utilisé des expériences sur cellules et une simulation de la structure.",
                  sources=("Nature News", "CNRS Actualités"))


def test_floride_refusee_titre_politique_de_sante():
    ok, raison = decouverte_qualifiee(FLORIDE)
    # vocabulaire de recherche présent (« modèle de simulation » via « simulation ») mais source unique non primaire
    assert not ok and ("source" in raison or "politique" in raison)


def test_une_seule_source_non_primaire_refusee():
    e = ev("Des chercheurs observent une nouvelle espèce de poisson",
           "Des chercheurs ont décrit une nouvelle espèce de poisson des grands fonds lors d'une mission, selon une étude. " * 3)
    ok, raison = decouverte_qualifiee(e)
    assert not ok and "source" in raison


def test_resume_court_refuse():
    ok, raison = decouverte_qualifiee(ev("Des chercheurs découvrent un fossile", "Une étude.", sources=("Nature News",)))
    assert not ok and "court" in raison


def test_etude_solide_deux_sources_acceptee():
    assert decouverte_qualifiee(ETUDE_SOLIDE) == (True, "")


def test_floride_bascule_en_mode_approfondi():
    topic = select_science_topic([FLORIDE])
    assert topic["mode"] == "approfondi"


def test_decouverte_retenue_meme_si_pas_en_premier():
    topic = select_science_topic([FLORIDE, ETUDE_SOLIDE])
    assert topic["mode"] == "decouverte" and topic["contenu_source"]["titre"].startswith("Des chercheurs identifient")


def test_approfondi_prefere_un_candidat_de_recherche_non_politique():
    politique = ev("Le gouvernement annonce un budget pour la recherche", "x" * 300)
    recherche = ev("Des chercheurs étudient le sommeil", "Une étude de chercheurs sur le sommeil.", sources=("Autre",))
    assert select_science_topic([politique, recherche])["contenu_source"]["titre"].startswith("Des chercheurs étudient")


def test_aucun_candidat():
    assert select_science_topic([])["contenu_source"]["sources"] == []
