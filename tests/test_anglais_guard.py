from src.generation.anglais_guard import filtrer_mots, score_apprentissage
from src.generation.briefing_generator import select_nyt_article

TITRE = "Centrist Lawmakers Push Back on Budget Stalemate"
RESUME = "The prime minister faces a backlash as a lawyer warns the crackdown could prolong the stalemate."


def test_mots_faciles_et_absents_retires_glossaire_applique():
    mots = [
        {"mot": "prime minister", "traduction": "premier ministre", "exemple": "x"},
        {"mot": "lawyer", "traduction": "avocat", "exemple": "x"},
        {"mot": "Centrist", "traduction": "centré", "exemple": "He is a centrist."},
        {"mot": "backlash", "traduction": "réaction hostile", "exemple": "x"},
        {"mot": "filibuster", "traduction": "obstruction", "exemple": "x"},   # absent du texte
        {"mot": "backlash", "traduction": "réaction hostile", "exemple": "x"},  # doublon
        {"mot": "stalemate", "traduction": "", "exemple": "x"},               # sans traduction
    ]
    out, stats = filtrer_mots(mots, TITRE, RESUME)
    assert [m["mot"] for m in out] == ["Centrist", "backlash"]
    assert out[0]["traduction"] == "centriste"
    assert stats["faciles"] == 2 and stats["absents_source"] == 1 and stats["doublons"] == 1
    assert stats["sans_traduction"] == 1


def test_entree_invalide_ne_leve_pas():
    assert filtrer_mots(None, TITRE, RESUME)[0] == []
    assert filtrer_mots(["str", 3, {}], TITRE, RESUME)[0] == []


def test_selection_prefere_le_vocabulaire_soutenu():
    items = [
        {"source": "The New York Times", "titre": "Man buys a car", "resume": "He went to the shop and bought a car for his wife today " * 3},
        {"source": "The New York Times", "titre": TITRE, "resume": RESUME},
        {"source": "Libération", "titre": "x", "resume": "autre source " * 50},
    ]
    assert select_nyt_article(items)["titre"] == TITRE
    assert score_apprentissage(TITRE, RESUME) > score_apprentissage("Man buys a car", "He went to the shop.")


def test_mots_courants_du_06_10_exclus_mais_vocabulaire_b2_conserve():
    from src.generation.anglais_guard import MOTS_FACILES
    for mot in ("documents", "action", "goalkeeper", "team", "season"):
        assert mot in MOTS_FACILES
    for mot in ("ineligible", "governance", "paperwork", "crackdown"):
        assert mot not in MOTS_FACILES
