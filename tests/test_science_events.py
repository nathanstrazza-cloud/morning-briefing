"""Tests hors réseau du regroupement FR/EN des articles sciences (06/10/2026)."""
from src.analyse.science_events import fusionner_evenements_science, racines


def ev(t, r, src):
    return {"titre": t, "resume": r, "sources": [{"nom": src, "url": f"https://{src}.org"}], "nb_sources": 1,
            "date_publication": None, "categorie": "sciences", "url_principale": ""}


NOBEL = [
    ev("Prix Nobel de médecine 2026 : technique d'activation des neurones par la lumière",
       "Les chercheurs ont inséré des protéines photosensibles dans les neurones pour contrôler leur activité par la lumière (optogénétique).", "Le Monde Sciences"),
    ev("Le Nobel de médecine 2026 récompense Karl Deisseroth, Peter Hegemann et Georg Nagel", "Optogénétique.", "Le Monde"),
    ev("Medicine Nobel awarded for brain switch that controls neurons with light",
       "Karl Deisseroth, Peter Hegemann and Georg Nagel win the 2026 Nobel prize in medicine for optogenetics.", "Nature"),
]
AUTRES = [
    ev("Dépendante de SpaceX, l'Europe est confrontée à sa pénurie de fusées", "Ariane 6 et Vega peinent à répondre à la demande.", "Le Monde"),
    ev("The top cancer success stories of the past 50 years", "Survival rates improved for many cancers.", "Nature"),
]


def test_articles_fr_en_du_meme_evenement_fusionnes_et_sources_cumulees():
    out = fusionner_evenements_science(NOBEL + AUTRES)
    assert len(out) == 3
    nobel = out[0]
    assert nobel["nb_sources"] == 3 and {s["nom"] for s in nobel["sources"]} == {"Le Monde Sciences", "Le Monde", "Nature"}
    assert len(nobel["textes_sources"]) == 3
    assert len(nobel["resume"]) >= max(len(e["resume"]) for e in NOBEL) - 1      # résumé le plus long conservé


def test_sujets_differents_non_fusionnes():
    out = fusionner_evenements_science(AUTRES)
    assert len(out) == 2 and all(e["nb_sources"] == 1 for e in out)


def test_entree_non_modifiee_et_racines_cognates():
    entree = [dict(e) for e in NOBEL]
    fusionner_evenements_science(entree)
    assert all(e["nb_sources"] == 1 for e in entree)
    assert "neuro" in racines(NOBEL[0]) and "neuro" in racines(NOBEL[2])


def test_evenement_fusionne_devient_decouverte_qualifiee():
    from src.generation.briefing_generator import decouverte_qualifiee
    nobel = fusionner_evenements_science(NOBEL)[0]
    ok, raison = decouverte_qualifiee(nobel)
    assert ok, raison           # >= 2 sources dont Nature (primaire), vocabulaire de recherche, résumé assez long
